"""
Phase 2, Feature 7 — in-app notification centre.

Deliberately boring: notifications are just rows in the existing SQLite database,
created by the same request that changes an incident. The frontend polls a normal
REST endpoint every few seconds. No Kafka, no Redis, no Firebase, no websockets.

`audience_role` decides who sees a notification:
  * "ADMIN" — shows up in the admin notification bell
  * "ALL"   — everyone
and `target_user_id` optionally pins it to one person (e.g. the student who
reported the incident gets told when their own incident is resolved).
"""
from sqlalchemy.orm import Session

from . import models


def add_notification(
    db: Session,
    title: str,
    message: str,
    kind: str,
    incident_id: int = None,
    audience_role: str = "ADMIN",
    target_user_id: int = None,
):
    """Create a notification row. Caller is responsible for db.commit()."""
    note = models.Notification(
        incident_id=incident_id,
        title=title,
        message=message,
        kind=kind,
        audience_role=audience_role,
        target_user_id=target_user_id,
    )
    db.add(note)
    return note


def notify_new_incident(db: Session, incident: models.Incident):
    """Fired when an incident is reported + analyzed."""
    is_critical = (incident.severity or "").upper() == "CRITICAL"
    title = "🚨 Critical emergency reported" if is_critical else "New incident reported"
    add_notification(
        db,
        title=title,
        message=(
            f"Incident #{incident.id}: {incident.incident_type} at {incident.location} "
            f"({incident.severity}, risk {incident.risk_score}, {incident.priority})."
        ),
        kind="CRITICAL" if is_critical else "STATUS",
        incident_id=incident.id,
        audience_role="ADMIN",
    )
    # Let the reporter know their report went through and was analyzed.
    if incident.reporter_user_id:
        add_notification(
            db,
            title="Your report was analyzed",
            message=(
                f"Incident #{incident.id} was classified as {incident.incident_type} "
                f"({incident.severity}, priority {incident.priority})."
            ),
            kind="AI",
            incident_id=incident.id,
            audience_role="ALL",
            target_user_id=incident.reporter_user_id,
        )


def notify_recommendation(db: Session, incident: models.Incident, team_name: str):
    add_notification(
        db,
        title="AI recommendation generated",
        message=f"{team_name} recommended for incident #{incident.id} at {incident.location}.",
        kind="AI",
        incident_id=incident.id,
        audience_role="ADMIN",
    )


def notify_assignment(db: Session, incident: models.Incident, team_name: str, overridden: bool, actor: str):
    suffix = " (admin override of the AI recommendation)" if overridden else ""
    add_notification(
        db,
        title="Team assigned",
        message=f"{team_name} assigned to incident #{incident.id} at {incident.location} by {actor}{suffix}.",
        kind="ASSIGNED",
        incident_id=incident.id,
        audience_role="ADMIN",
    )
    if incident.reporter_user_id:
        add_notification(
            db,
            title="A team is on the way",
            message=f"{team_name} has been assigned to your incident #{incident.id}.",
            kind="ASSIGNED",
            incident_id=incident.id,
            audience_role="ALL",
            target_user_id=incident.reporter_user_id,
        )


def notify_status_change(db: Session, incident: models.Incident, new_status: str, actor: str):
    resolved = new_status == "RESOLVED"
    add_notification(
        db,
        title="Incident resolved" if resolved else "Incident status changed",
        message=f"Incident #{incident.id} is now {new_status} (updated by {actor}).",
        kind="RESOLVED" if resolved else "STATUS",
        incident_id=incident.id,
        audience_role="ADMIN",
    )
    if incident.reporter_user_id:
        add_notification(
            db,
            title="Update on your incident",
            message=f"Your incident #{incident.id} is now {new_status}.",
            kind="RESOLVED" if resolved else "STATUS",
            incident_id=incident.id,
            audience_role="ALL",
            target_user_id=incident.reporter_user_id,
        )


def notify_reassignment(
    db: Session, incident: models.Incident, old_team_name: str, new_team_name: str,
    reason: str, actor: str,
):
    """Phase I — a team assignment was changed after the fact (reassignment)."""
    reason_suffix = f" Reason: {reason}" if reason else ""
    add_notification(
        db,
        title="Incident reassigned",
        message=(
            f"Incident #{incident.id} reassigned from {old_team_name} to {new_team_name} "
            f"by {actor}.{reason_suffix}"
        ),
        kind="ASSIGNED",
        incident_id=incident.id,
        audience_role="ADMIN",
    )
    if incident.reporter_user_id:
        add_notification(
            db,
            title="Your incident's team changed",
            message=f"{new_team_name} is now responding to your incident #{incident.id} (previously {old_team_name}).",
            kind="ASSIGNED",
            incident_id=incident.id,
            audience_role="ALL",
            target_user_id=incident.reporter_user_id,
        )


def visible_notifications_query(db: Session, user: models.User):
    """Notifications this user is allowed to see."""
    q = db.query(models.Notification)
    if user.role == "ADMIN":
        # Admins see the admin feed plus anything explicitly addressed to them.
        return q.filter(
            (models.Notification.audience_role == "ADMIN")
            | (models.Notification.target_user_id == user.id)
        )
    # Students/faculty see broadcast items addressed to them (or to nobody in particular).
    return q.filter(
        models.Notification.audience_role == "ALL",
        (models.Notification.target_user_id == user.id)
        | (models.Notification.target_user_id.is_(None)),
    )


# ===========================================================================
# Phase 3B — user-management notifications
#
# These reuse the Phase 2 notification table and the same add_notification()
# helper. No second notification system is introduced: the admin bell and the
# /api/notifications endpoint pick these up exactly like incident events.
# ===========================================================================
def notify_new_registration(db: Session, user: models.User):
    """Admin is told when somebody registers and needs review."""
    add_notification(
        db,
        title="New registration awaiting approval",
        message=f"{user.name} ({user.email}) registered as {user.role} and is pending approval.",
        kind="STATUS",
        audience_role="ADMIN",
    )


def notify_account_status_change(db: Session, user: models.User, new_status: str, reason: str = None):
    """The affected user is told when an admin changes their account status."""
    wording = {
        "APPROVED": ("Your account has been approved", "You can now sign in and use the platform."),
        "REJECTED": ("Your account was rejected", "Your registration was not approved."),
        "SUSPENDED": ("Your account has been suspended", "Access has been temporarily withdrawn."),
    }
    title, message = wording.get(
        new_status, ("Your account status changed", f"Your account is now {new_status}.")
    )
    if reason:
        message += f" Reason: {reason}"

    add_notification(
        db,
        title=title,
        message=message,
        kind="STATUS",
        audience_role="ALL",
        target_user_id=user.id,
    )


def notify_emergency_access_request(db: Session, request: models.EmergencyAccessRequest):
    """Admin is told about an emergency-access request — these are time-critical."""
    add_notification(
        db,
        title="🚨 Emergency access requested",
        message=(
            f"{request.full_name} ({request.email}) requested emergency access: "
            f"{(request.emergency_description or '')[:120]}"
        ),
        kind="CRITICAL",
        audience_role="ADMIN",
    )


def notify_emergency_access_decision(db: Session, request: models.EmergencyAccessRequest, approved: bool):
    """
    Told to the granted account, where one exists. The requester also sees the
    decision by checking their reference code, since a rejected requester has
    no account to receive an in-app notification.
    """
    if not request.granted_user_id:
        return
    add_notification(
        db,
        title="Emergency access granted" if approved else "Emergency access denied",
        message=(
            f"Temporary access granted until {request.access_expires_at:%d %b %Y, %H:%M} UTC."
            if approved
            else "Your emergency access request was not approved."
        ),
        kind="CRITICAL",
        audience_role="ALL",
        target_user_id=request.granted_user_id,
    )
