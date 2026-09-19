"""
Phase 3B, section 5 — controlled emergency access.

The problem this solves: someone whose registration hasn't been approved yet
witnesses a real emergency. Making them wait for approval is unacceptable;
letting them in automatically would destroy the whole approval model.

The route taken here is a request-and-review flow:

    1. Anyone can SUBMIT a request from the login page. Submitting grants
       nothing whatsoever — no token, no account, no access. It creates a row
       and an admin notification.
    2. An ADMIN explicitly approves or rejects it.
    3. Only on approval is a grant created, and it is deliberately minimal:
         * role STUDENT — the lowest privilege level
         * flagged `is_emergency_access`, which `require_permanent_account`
           uses to keep these accounts out of operational data
         * time-limited via `access_expires_at`, enforced on every request
         * no password is set, so the account cannot be used to log in
           normally; the grant is collected once, with the reference code
    4. Every step is written to the audit log.

This is explicitly NOT an authentication bypass, which section 5 requires.
"""
import datetime
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import audit, models, notifications, schemas, security
from ..database import get_db
from ..deps import ROLE_STUDENT, require_admin

router = APIRouter(prefix="/api/emergency-access", tags=["emergency-access"])

# Bounds on how long a temporary grant may last.
MIN_DURATION_MINUTES = 15
MAX_DURATION_MINUTES = 24 * 60
DEFAULT_DURATION_MINUTES = 120

# Unambiguous alphabet — no O/0 or I/1, since people read these codes aloud.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_reference_code(db: Session) -> str:
    """A short, unguessable code. Retried in the vanishingly rare collision case."""
    for _ in range(10):
        code = "EA-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        exists = (
            db.query(models.EmergencyAccessRequest)
            .filter(models.EmergencyAccessRequest.reference_code == code)
            .first()
        )
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="Could not allocate a reference code.")


def _normalise_email(raw: str) -> str:
    return (raw or "").strip().lower()


# ---------------------------------------------------------------------------
# PUBLIC — submit a request
# ---------------------------------------------------------------------------
@router.post("/request", response_model=schemas.EmergencyAccessSubmitted, status_code=201)
def submit_request(payload: schemas.EmergencyAccessCreate, db: Session = Depends(get_db)):
    """
    Submit an emergency-access request. No authentication required — and no
    access is granted. The response contains a reference code and nothing else.
    """
    email = _normalise_email(payload.email)
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")

    full_name = (payload.full_name or "").strip()
    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="Please enter your full name.")
    if len((payload.reason or "").strip()) < 5:
        raise HTTPException(status_code=422, detail="Please explain why you need access.")
    if len((payload.emergency_description or "").strip()) < 10:
        raise HTTPException(
            status_code=422,
            detail="Please describe the emergency so responders know what is happening.",
        )

    # If this person already has a request awaiting review, hand back the same
    # reference instead of piling up duplicates for the admin to wade through
    # during an actual emergency.
    existing = (
        db.query(models.EmergencyAccessRequest)
        .filter(
            models.EmergencyAccessRequest.email == email,
            models.EmergencyAccessRequest.status == models.EA_PENDING,
        )
        .order_by(models.EmergencyAccessRequest.created_at.desc())
        .first()
    )
    if existing:
        return schemas.EmergencyAccessSubmitted(
            reference_code=existing.reference_code,
            status=existing.status,
            message=(
                "You already have a request awaiting review. Keep this reference "
                "code — an administrator is being notified."
            ),
        )

    request = models.EmergencyAccessRequest(
        full_name=full_name,
        email=email,
        contact_number=(payload.contact_number or "").strip() or None,
        reason=payload.reason.strip(),
        emergency_description=payload.emergency_description.strip(),
        location=(payload.location or "").strip() or None,
        incident_details=(payload.incident_details or "").strip() or None,
        reference_code=_generate_reference_code(db),
        status=models.EA_PENDING,
    )
    db.add(request)
    db.flush()  # assign the id before auditing

    notifications.notify_emergency_access_request(db, request)

    audit.record(
        db,
        action="EMERGENCY_ACCESS_REQUESTED",
        actor=None,
        actor_name=f"{full_name} ({email})",
        actor_role="ANONYMOUS",
        target_type="EMERGENCY_ACCESS",
        target_id=request.id,
        target_label=email,
        details=f"Reason: {request.reason} | Emergency: {request.emergency_description[:200]}",
    )
    db.commit()
    db.refresh(request)

    return schemas.EmergencyAccessSubmitted(
        reference_code=request.reference_code,
        status=request.status,
        message=(
            "Your request has been sent to the campus administrator. Save this "
            "reference code — you will need it to check the decision. "
            "If this is a life-threatening emergency, call campus security now."
        ),
    )


# ---------------------------------------------------------------------------
# PUBLIC — check the decision / collect the grant
# ---------------------------------------------------------------------------
@router.get("/status/{reference_code}", response_model=schemas.EmergencyAccessStatusOut)
def check_request(
    reference_code: str,
    email: str = Query(..., description="The email address used on the request"),
    db: Session = Depends(get_db),
):
    """
    Check a request by reference code. Both the code AND the email must match,
    so knowing (or guessing) one of them alone is not enough to collect a grant.

    A token is returned only when the request was approved and the grant is
    still within its window.
    """
    code = (reference_code or "").strip().upper()
    request = (
        db.query(models.EmergencyAccessRequest)
        .filter(
            models.EmergencyAccessRequest.reference_code == code,
            models.EmergencyAccessRequest.email == _normalise_email(email),
        )
        .first()
    )
    # Deliberately the same 404 whether the code is wrong or the email doesn't
    # match, so this endpoint can't be used to probe for valid codes.
    if not request:
        raise HTTPException(
            status_code=404,
            detail="No request found for that reference code and email address.",
        )

    if request.status == models.EA_PENDING:
        return schemas.EmergencyAccessStatusOut(
            status=models.EA_PENDING,
            message="Your request is still awaiting administrator review.",
        )

    if request.status == models.EA_REJECTED:
        message = "Your emergency access request was not approved."
        if request.review_note:
            message += f" Note: {request.review_note}"
        return schemas.EmergencyAccessStatusOut(status=models.EA_REJECTED, message=message)

    # ---- APPROVED ----
    granted_user = (
        db.query(models.User).filter(models.User.id == request.granted_user_id).first()
        if request.granted_user_id
        else None
    )
    if not granted_user:
        raise HTTPException(
            status_code=500,
            detail="This request was approved but the grant is missing. Contact the administrator.",
        )

    now = datetime.datetime.utcnow()
    if request.access_expires_at and now > request.access_expires_at:
        return schemas.EmergencyAccessStatusOut(
            status="EXPIRED",
            message="Your temporary emergency access has expired. Please submit a new request.",
            access_expires_at=request.access_expires_at,
        )

    token, _ = security.create_access_token(
        granted_user.id, granted_user.email, granted_user.role
    )
    # The token must not outlive the grant, so cap the reported lifetime at the
    # grant window. The backend re-checks `access_expires_at` on every request
    # regardless, so this is belt and braces.
    expires_in = int(max((request.access_expires_at - now).total_seconds(), 0))

    first_collection = request.collected_at is None
    if first_collection:
        request.collected_at = now
        audit.record(
            db,
            action="EMERGENCY_ACCESS_USED",
            actor=granted_user,
            target_type="EMERGENCY_ACCESS",
            target_id=request.id,
            target_label=request.email,
            details=f"Temporary access collected. Expires {request.access_expires_at} UTC.",
        )
        db.commit()

    return schemas.EmergencyAccessStatusOut(
        status=models.EA_APPROVED,
        message=(
            "Emergency access granted. You can report the emergency and follow your "
            "own report until this access expires."
        ),
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        access_expires_at=request.access_expires_at,
        user=schemas.UserOut.model_validate(granted_user),
    )


# ---------------------------------------------------------------------------
# ADMIN — review queue
# ---------------------------------------------------------------------------
@router.get("", response_model=schemas.EmergencyAccessListOut)
def list_requests(
    status: Optional[str] = Query(None, description="PENDING | APPROVED | REJECTED"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    query = db.query(models.EmergencyAccessRequest)
    if status:
        query = query.filter(models.EmergencyAccessRequest.status == status.strip().upper())

    rows = (
        query.order_by(models.EmergencyAccessRequest.created_at.desc()).limit(limit).all()
    )
    pending_count = (
        db.query(models.EmergencyAccessRequest)
        .filter(models.EmergencyAccessRequest.status == models.EA_PENDING)
        .count()
    )
    return schemas.EmergencyAccessListOut(
        total=len(rows),
        pending_count=pending_count,
        requests=[schemas.EmergencyAccessOut.model_validate(r) for r in rows],
    )


def _load_pending(db: Session, request_id: int) -> models.EmergencyAccessRequest:
    request = (
        db.query(models.EmergencyAccessRequest)
        .filter(models.EmergencyAccessRequest.id == request_id)
        .first()
    )
    if not request:
        raise HTTPException(status_code=404, detail="Request not found.")
    if request.status != models.EA_PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"This request has already been {request.status.lower()}.",
        )
    return request


@router.post("/{request_id}/approve", response_model=schemas.EmergencyAccessOut)
def approve_request(
    request_id: int,
    payload: schemas.EmergencyAccessDecision = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Grant minimum necessary, time-limited access.

    If the requester already has an account it is reused; otherwise a minimal
    STUDENT account is created with NO password, so the only way to use it is
    by collecting the grant with the reference code before it expires.
    """
    request = _load_pending(db, request_id)

    minutes = (payload.duration_minutes if payload else DEFAULT_DURATION_MINUTES)
    minutes = max(MIN_DURATION_MINUTES, min(int(minutes or DEFAULT_DURATION_MINUTES), MAX_DURATION_MINUTES))
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)

    user = db.query(models.User).filter(models.User.email == request.email).first()

    if user is None:
        user = models.User(
            name=request.full_name,
            email=request.email,
            role=ROLE_STUDENT,  # minimum privilege
            password_hash=None,  # cannot be used for a normal password login
            status=models.STATUS_APPROVED,
            is_emergency_access=1,
            access_expires_at=expires_at,
            created_at=datetime.datetime.utcnow(),
            status_reason=f"Temporary emergency access ({request.reference_code}).",
            status_changed_at=datetime.datetime.utcnow(),
            status_changed_by_id=admin.id,
        )
        db.add(user)
        db.flush()
        created = True
    else:
        created = False
        # An already-approved permanent account keeps its standing — emergency
        # access must never downgrade or time-limit a real account.
        if (user.status or "").upper() != models.STATUS_APPROVED:
            user.status = models.STATUS_APPROVED
            user.is_emergency_access = 1
            user.access_expires_at = expires_at
            user.status_reason = f"Temporary emergency access ({request.reference_code})."
            user.status_changed_at = datetime.datetime.utcnow()
            user.status_changed_by_id = admin.id

    request.status = models.EA_APPROVED
    request.reviewed_by_id = admin.id
    request.reviewed_by_name = admin.name
    request.reviewed_at = datetime.datetime.utcnow()
    request.review_note = (payload.note if payload else None)
    request.granted_user_id = user.id
    request.access_expires_at = expires_at

    notifications.notify_emergency_access_decision(db, request, approved=True)

    audit.record(
        db,
        action="EMERGENCY_ACCESS_APPROVED",
        actor=admin,
        target_type="EMERGENCY_ACCESS",
        target_id=request.id,
        target_label=request.email,
        details=(
            f"Granted {'new' if created else 'existing'} account id={user.id} "
            f"role={user.role} for {minutes} minutes (until {expires_at} UTC)."
            + (f" Note: {request.review_note}" if request.review_note else "")
        ),
    )
    db.commit()
    db.refresh(request)
    return schemas.EmergencyAccessOut.model_validate(request)


@router.post("/{request_id}/reject", response_model=schemas.EmergencyAccessOut)
def reject_request(
    request_id: int,
    payload: schemas.EmergencyAccessDecision = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Decline the request. No account is created and no access is granted."""
    request = _load_pending(db, request_id)

    request.status = models.EA_REJECTED
    request.reviewed_by_id = admin.id
    request.reviewed_by_name = admin.name
    request.reviewed_at = datetime.datetime.utcnow()
    request.review_note = (payload.note if payload else None)

    notifications.notify_emergency_access_decision(db, request, approved=False)

    audit.record(
        db,
        action="EMERGENCY_ACCESS_REJECTED",
        actor=admin,
        target_type="EMERGENCY_ACCESS",
        target_id=request.id,
        target_label=request.email,
        details=(request.review_note or "No reason given."),
    )
    db.commit()
    db.refresh(request)
    return schemas.EmergencyAccessOut.model_validate(request)
