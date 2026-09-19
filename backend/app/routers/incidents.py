import datetime
import os
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import case
from sqlalchemy.orm import Session

from .. import models, schemas, notifications, audit
from ..database import get_db
from ..ai_classifier import classify_incident
from ..action_plan import generate_action_plan, fallback_action_plan
from ..team_recommender import recommend_team
from ..deps import get_current_user, require_admin, can_view_incident

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

VALID_STATUSES = ["REPORTED", "ANALYZED", "ASSIGNED", "RESPONDING", "RESOLVED"]

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Phase 2: an action plan goes through Groq for incidents that are genuinely
# serious; everything else uses the instant deterministic plan so that reporting
# a minor issue stays fast.
SERIOUS_SEVERITIES = ("HIGH", "CRITICAL")
SERIOUS_RISK_THRESHOLD = 60


def _to_out(incident: models.Incident) -> schemas.IncidentOut:
    data = schemas.IncidentOut.model_validate(incident).model_dump()
    data["assigned_team_name"] = incident.assigned_team.name if incident.assigned_team else None
    data["recommended_team_name"] = (
        incident.recommended_team.name if incident.recommended_team else None
    )
    return schemas.IncidentOut(**data)


def _to_detail_out(incident: models.Incident) -> schemas.IncidentDetailOut:
    data = schemas.IncidentOut.model_validate(incident).model_dump()
    data["assigned_team_name"] = incident.assigned_team.name if incident.assigned_team else None
    data["recommended_team_name"] = (
        incident.recommended_team.name if incident.recommended_team else None
    )
    data["status_history"] = [
        schemas.StatusHistoryOut.model_validate(h) for h in
        sorted(incident.status_history, key=lambda h: h.timestamp)
    ]
    return schemas.IncidentDetailOut(**data)


def _log(db: Session, incident_id: int, status: str, note: str,
         actor_name: str = "System", actor_role: str = "SYSTEM", event_type: str = "STATUS"):
    """Write one row to the existing status-history table, now with actor info."""
    db.add(models.IncidentStatusHistory(
        incident_id=incident_id,
        status=status,
        note=note,
        actor_name=actor_name,
        actor_role=actor_role,
        event_type=event_type,
    ))


def _generate_recommendation(db: Session, incident: models.Incident, log_event: bool = True):
    """Phase 2, Feature 2 — pick and store the recommended response team."""
    teams = db.query(models.ResponseTeam).all()
    team, reason = recommend_team(
        teams,
        incident.incident_type,
        incident.severity,
        incident.risk_score,
        incident.priority,
        incident.location,
    )
    incident.recommended_team_id = team.id if team else None
    incident.recommendation_reason = reason
    if team and log_event:
        _log(db, incident.id, "ANALYZED", f"AI recommended {team.name}. {reason}",
             actor_name="AI Engine", actor_role="SYSTEM", event_type="RECOMMENDATION")
    return team, reason


@router.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Optional image upload for a report. Stored locally on disk (no paid cloud storage)."""
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, filename)
    contents = await file.read()
    with open(dest_path, "wb") as f:
        f.write(contents)
    return {"filename": filename}


@router.post("", response_model=schemas.IncidentDetailOut, status_code=201)
def create_incident(
    payload: schemas.IncidentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Report an emergency. Any signed-in role may do this.
    Existing Phase 1 behaviour (create -> AI classify -> ANALYZED) is unchanged;
    Phase 2 adds the team recommendation, the action plan and notifications.
    """
    incident = models.Incident(
        reporter_name=payload.reporter_name,
        reporter_role=payload.reporter_role,
        contact_number=payload.contact_number,
        description=payload.description,
        category=payload.category,
        location=payload.location,
        image_filename=payload.image_filename,
        status="REPORTED",
        reporter_user_id=user.id,  # Phase 2: lets students see their own incidents
    )
    db.add(incident)
    db.flush()  # get incident.id
    _log(db, incident.id, "REPORTED", "Incident reported by " + payload.reporter_name,
         actor_name=payload.reporter_name, actor_role=user.role, event_type="STATUS")
    db.commit()
    db.refresh(incident)

    # Run AI classification (never throws — always returns a valid result)
    result = classify_incident(payload.description, payload.category, payload.location)

    incident.incident_type = result.incidentType
    incident.severity = result.severity
    incident.risk_score = result.riskScore
    incident.priority = result.priority
    incident.ai_reason = result.reason
    incident.recommended_action = result.recommendedAction
    incident.analysis_source = result.source
    incident.status = "ANALYZED"
    incident.analyzed_at = datetime.datetime.utcnow()
    incident.updated_at = datetime.datetime.utcnow()

    _log(db, incident.id, "ANALYZED",
         f"{result.source}: {result.incidentType} / {result.severity} / risk {result.riskScore}",
         actor_name="AI Engine", actor_role="SYSTEM", event_type="AI")

    # Phase 2, Feature 5 — emergency action plan
    is_serious = (
        (result.severity or "").upper() in SERIOUS_SEVERITIES
        or (result.riskScore or 0) >= SERIOUS_RISK_THRESHOLD
    )
    if is_serious:
        steps, plan_source = generate_action_plan(
            payload.description, result.incidentType, result.severity, payload.location
        )
    else:
        steps = fallback_action_plan(result.incidentType, result.severity)
        plan_source = "Fallback Analysis"
    incident.set_action_plan(steps)
    incident.action_plan_source = plan_source

    # Phase 2, Feature 2 — recommend a response team
    team, reason = _generate_recommendation(db, incident)

    db.commit()
    db.refresh(incident)

    # Phase 2, Feature 7 — notifications
    notifications.notify_new_incident(db, incident)
    if team:
        notifications.notify_recommendation(db, incident, team.name)
    db.commit()
    db.refresh(incident)

    return _to_detail_out(incident)


# Smart priority queue ordering (Feature 4): P1 first, then P2/P3/P4, unknown last.
PRIORITY_RANK = case(
    (models.Incident.priority == "P1", 1),
    (models.Incident.priority == "P2", 2),
    (models.Incident.priority == "P3", 3),
    (models.Incident.priority == "P4", 4),
    else_=5,
)

# Resolved incidents drop to the bottom of the smart queue.
STATUS_RANK = case(
    (models.Incident.status == "RESOLVED", 2),
    else_=1,
)


@router.get("", response_model=List[schemas.IncidentOut])
def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    incident_type: Optional[str] = None,
    priority: Optional[str] = None,
    sort_by_risk: bool = False,
    smart_queue: bool = False,
    mine: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    All existing Phase 1 filters and sort-by-risk behave exactly as before.

    Phase 2 adds:
      * `smart_queue=true` — priority-first ordering (Feature 4)
      * `mine=true` — only incidents I reported
      * role enforcement — a STUDENT always gets their own incidents only,
        no matter what parameters they send.
    """
    query = db.query(models.Incident)
    if status:
        query = query.filter(models.Incident.status == status)
    if severity:
        query = query.filter(models.Incident.severity == severity)
    if incident_type:
        query = query.filter(models.Incident.incident_type == incident_type)
    if priority:
        query = query.filter(models.Incident.priority == priority)

    # ---- Role-based visibility, enforced server-side ----
    if user.role == "STUDENT":
        query = query.filter(
            (models.Incident.reporter_user_id == user.id)
            | (
                (models.Incident.reporter_user_id.is_(None))
                & (models.Incident.reporter_name == user.name)
            )
        )
    elif mine:
        query = query.filter(models.Incident.reporter_user_id == user.id)

    if smart_queue:
        query = query.order_by(
            STATUS_RANK.asc(),
            PRIORITY_RANK.asc(),
            models.Incident.risk_score.desc(),
            models.Incident.created_at.asc(),
        )
    elif sort_by_risk:
        query = query.order_by(models.Incident.risk_score.desc())
    else:
        query = query.order_by(models.Incident.created_at.desc())

    return [_to_out(i) for i in query.all()]


@router.get("/{incident_id}", response_model=schemas.IncidentDetailOut)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if not can_view_incident(user, incident):
        raise HTTPException(
            status_code=403,
            detail="You can only view incidents that you reported.",
        )
    return _to_detail_out(incident)


@router.post("/{incident_id}/recommend-team", response_model=schemas.TeamRecommendationOut)
def recommend_team_for_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Phase 2, Feature 2 — (re)generate the AI team recommendation for an incident.
    Useful for incidents created before Phase 2, and for re-running the
    recommendation after team availability has changed.
    """
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    team, reason = _generate_recommendation(db, incident)
    incident.updated_at = datetime.datetime.utcnow()
    if team:
        notifications.notify_recommendation(db, incident, team.name)
    db.commit()

    return schemas.TeamRecommendationOut(
        team_id=team.id if team else None,
        team_name=team.name if team else None,
        capability=team.capability if team else None,
        availability=team.availability if team else None,
        reason=reason,
    )


@router.post("/{incident_id}/action-plan", response_model=schemas.IncidentDetailOut)
def build_action_plan(
    incident_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Phase 2, Feature 5 — (re)generate the emergency action plan for an incident."""
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    steps, source = generate_action_plan(
        incident.description, incident.incident_type or "OTHER",
        incident.severity or "MEDIUM", incident.location,
    )
    incident.set_action_plan(steps)
    incident.action_plan_source = source
    incident.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(incident)
    return _to_detail_out(incident)


@router.put("/{incident_id}/status", response_model=schemas.IncidentDetailOut)
def update_status(
    incident_id: int,
    payload: schemas.StatusUpdateRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),  # Phase 2: ADMIN only, enforced here
):
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    new_status = payload.status.upper()
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {VALID_STATUSES}")

    now = datetime.datetime.utcnow()
    incident.status = new_status
    incident.updated_at = now

    # Phase 2, Feature 6 — record the real timestamp for each stage
    if new_status == "ANALYZED" and not incident.analyzed_at:
        incident.analyzed_at = now
    if new_status == "ASSIGNED" and not incident.assigned_at:
        incident.assigned_at = now
    if new_status == "RESPONDING" and not incident.responding_at:
        incident.responding_at = now

    if new_status == "RESOLVED":
        incident.resolved_at = now
        # Free up the assigned team once the incident is resolved
        if incident.assigned_team_id:
            team = db.query(models.ResponseTeam).filter(models.ResponseTeam.id == incident.assigned_team_id).first()
            if team:
                team.availability = "AVAILABLE"

    _log(db, incident.id, new_status, payload.note,
         actor_name=admin.name, actor_role=admin.role, event_type="STATUS")
    notifications.notify_status_change(db, incident, new_status, admin.name)
    db.commit()
    db.refresh(incident)
    return _to_detail_out(incident)


@router.put("/{incident_id}/assign-team", response_model=schemas.IncidentDetailOut)
def assign_team(
    incident_id: int,
    payload: schemas.AssignTeamRequestV2,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),  # ADMIN only, enforced here
):
    """
    Assign — or reassign — a response team to an incident.

    Phase 2, Feature 3: the AI recommendation is never binding — if the admin
    picks a different team, that is recorded as an explicit override.

    Phase I (Team Assignment + Reassignment): if the incident already has an
    active team, calling this again with a *different* team is a reassignment,
    not a silent overwrite. The old team is freed up, the change is preserved
    forever in `incident_assignments`, and both a TEAM_REASSIGNED audit entry
    and a notification are written. `override_reason` doubles as the optional
    reassignment reason (e.g. "Fire team unavailable").
    """
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status == "RESOLVED":
        raise HTTPException(
            status_code=400,
            detail="Cannot assign a team to a resolved incident.",
        )

    team = db.query(models.ResponseTeam).filter(models.ResponseTeam.id == payload.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Response team not found")

    previous_team_id = incident.assigned_team_id

    if previous_team_id == team.id:
        raise HTTPException(
            status_code=400,
            detail=f"{team.name} is already assigned to this incident.",
        )

    if team.availability != "AVAILABLE":
        raise HTTPException(status_code=400, detail=f"{team.name} is not currently available")

    now = datetime.datetime.utcnow()
    is_reassignment = previous_team_id is not None

    # Did the admin go against the AI recommendation?
    overridden = bool(
        incident.recommended_team_id and incident.recommended_team_id != team.id
    )
    recommended_name = incident.recommended_team.name if incident.recommended_team else None

    previous_assignment = None
    previous_team = None
    if is_reassignment:
        previous_team = db.query(models.ResponseTeam).filter(
            models.ResponseTeam.id == previous_team_id
        ).first()
        previous_assignment = (
            db.query(models.IncidentAssignment)
            .filter(
                models.IncidentAssignment.incident_id == incident.id,
                models.IncidentAssignment.is_active == 1,
            )
            .first()
        )
        if previous_assignment:
            previous_assignment.is_active = 0
            previous_assignment.deactivated_at = now
        # Free the outgoing team — Phase 1/2 never did this, so a reassigned
        # team stayed BUSY forever. This is the bug Phase I fixes.
        if previous_team and previous_team.availability != "AVAILABLE":
            previous_team.availability = "AVAILABLE"

    # New/current assignment row — the single source of truth for history.
    db.add(models.IncidentAssignment(
        incident_id=incident.id,
        team_id=team.id,
        team_name=team.name,
        assigned_by_id=admin.id,
        assigned_by_name=admin.name,
        is_override=1 if overridden else 0,
        reason=payload.override_reason,
        assigned_at=now,
        is_active=1,
    ))

    incident.assigned_team_id = team.id
    incident.assigned_by_name = admin.name
    incident.assignment_overridden = 1 if overridden else 0
    if not incident.assigned_at:
        incident.assigned_at = now
    if incident.status in ("REPORTED", "ANALYZED"):
        incident.status = "ASSIGNED"
    incident.updated_at = now

    team.availability = "BUSY"

    if is_reassignment:
        note = f"Reassigned from {previous_team.name if previous_team else 'a previous team'} to {team.name} by {admin.name}"
        if payload.override_reason:
            note += f" — reason: {payload.override_reason}"
        _log(db, incident.id, incident.status, note,
             actor_name=admin.name, actor_role=admin.role, event_type="REASSIGNMENT")
        audit.record(
            db, "TEAM_REASSIGNED", actor=admin,
            target_type="INCIDENT", target_id=incident.id, target_label=f"Incident #{incident.id}",
            details=(
                f"From {previous_team.name if previous_team else 'unknown'} to {team.name}."
                + (f" Reason: {payload.override_reason}" if payload.override_reason else "")
            ),
        )
        notifications.notify_reassignment(
            db, incident, previous_team.name if previous_team else "a previous team",
            team.name, payload.override_reason or "", admin.name,
        )
    else:
        note = f"Assigned to {team.name} by {admin.name}"
        if overridden:
            note = (
                f"ADMIN OVERRIDE: {team.name} assigned by {admin.name} "
                f"instead of the AI-recommended {recommended_name}"
            )
            if payload.override_reason:
                note += f" — reason: {payload.override_reason}"

        _log(db, incident.id, "ASSIGNED", note,
             actor_name=admin.name, actor_role=admin.role,
             event_type="OVERRIDE" if overridden else "ASSIGNMENT")
        audit.record(
            db, "TEAM_ASSIGNED", actor=admin,
            target_type="INCIDENT", target_id=incident.id, target_label=f"Incident #{incident.id}",
            details=f"{team.name} assigned." + (f" Reason: {payload.override_reason}" if payload.override_reason else ""),
        )
        notifications.notify_assignment(db, incident, team.name, overridden, admin.name)

    db.commit()
    db.refresh(incident)
    return _to_detail_out(incident)


@router.get("/{incident_id}/assignment-history", response_model=List[schemas.AssignmentHistoryOut])
def get_assignment_history(
    incident_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),  # ADMIN only, per Phase I spec
):
    """Phase I — full team-assignment history for one incident, oldest first."""
    incident = db.query(models.Incident).filter(models.Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    rows = (
        db.query(models.IncidentAssignment)
        .filter(models.IncidentAssignment.incident_id == incident_id)
        .order_by(models.IncidentAssignment.assigned_at.asc())
        .all()
    )
    return [
        schemas.AssignmentHistoryOut(
            id=r.id, team_id=r.team_id, team_name=r.team_name,
            assigned_by_name=r.assigned_by_name, is_override=bool(r.is_override),
            reason=r.reason, assigned_at=r.assigned_at,
            is_active=bool(r.is_active), deactivated_at=r.deactivated_at,
        )
        for r in rows
    ]
