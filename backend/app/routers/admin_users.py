"""
Phase 3B, sections 1 / 4 / 6 / 7 — the administrator console.

Every endpoint here is guarded by `require_admin`, which resolves the caller
from a signed token and re-reads their role from the database. Hiding the menu
item in React is not what protects these: a STUDENT token calling any of these
URLs directly gets a 403.

Three safety rules apply to every status change:
  1. An admin cannot change their own account status (no locking yourself out,
     no self-suspension mistakes).
  2. An admin cannot change another ADMIN's status. Administrator accounts are
     managed internally, matching the Phase 3A rule that nobody can make
     themselves an admin.
  3. Every change writes an audit entry in the SAME transaction as the change,
     so the log can never disagree with reality.
"""
import datetime
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import audit, models, notifications, schemas
from ..database import get_db
from ..deps import ROLE_ADMIN, require_admin
from ..pdf_export import PDF_UNAVAILABLE_MESSAGE, build_users_pdf, reportlab_available

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_admin_out(db: Session, user: models.User) -> schemas.AdminUserOut:
    changed_by = None
    if user.status_changed_by_id:
        row = db.query(models.User).filter(models.User.id == user.status_changed_by_id).first()
        changed_by = row.name if row else None

    incident_count = (
        db.query(models.Incident).filter(models.Incident.reporter_user_id == user.id).count()
    )

    return schemas.AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        status=user.status or models.STATUS_PENDING,
        created_at=user.created_at,
        status_reason=user.status_reason,
        status_changed_at=user.status_changed_at,
        status_changed_by_name=changed_by,
        is_emergency_access=bool(user.is_emergency_access),
        access_expires_at=user.access_expires_at,
        incident_count=incident_count,
    )


def _load_target(db: Session, user_id: int, admin: models.User) -> models.User:
    """Fetch the user being acted on, applying the three safety rules above."""
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.id == admin.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change the status of your own account.",
        )
    if target.role == ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Administrator accounts cannot be modified from this console.",
        )
    return target


def _apply_status(
    db: Session,
    admin: models.User,
    target: models.User,
    new_status: str,
    action: str,
    reason: Optional[str],
) -> schemas.AdminUserOut:
    """Change a status, notify the user, and audit it — all in one transaction."""
    old_status = target.status or models.STATUS_PENDING

    if old_status == new_status:
        raise HTTPException(
            status_code=400,
            detail=f"This account is already {new_status}.",
        )

    target.status = new_status
    target.status_reason = reason
    target.status_changed_at = datetime.datetime.utcnow()
    target.status_changed_by_id = admin.id

    # Reactivating or approving a previously time-limited emergency account
    # clears the expiry, turning it into a normal account.
    if new_status == models.STATUS_APPROVED and target.is_emergency_access:
        target.is_emergency_access = 0
        target.access_expires_at = None

    notifications.notify_account_status_change(db, target, new_status, reason)

    audit.record(
        db,
        action=action,
        actor=admin,
        target_type="USER",
        target_id=target.id,
        target_label=target.email,
        details=audit.describe_status_change(old_status, new_status, reason),
    )

    db.commit()
    db.refresh(target)
    return _to_admin_out(db, target)


# ---------------------------------------------------------------------------
# 1. Viewing users
# ---------------------------------------------------------------------------
@router.get("/users", response_model=schemas.UserListOut)
def list_users(
    q: Optional[str] = Query(None, description="Search name or email"),
    status: Optional[str] = Query(None, description="PENDING | APPROVED | REJECTED | SUSPENDED"),
    role: Optional[str] = Query(None, description="STUDENT | FACULTY | ADMIN"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """All users, with search and filters (section 1)."""
    query = db.query(models.User)

    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(models.User.name.ilike(needle), models.User.email.ilike(needle))
        )
    if status:
        query = query.filter(models.User.status == status.strip().upper())
    if role:
        query = query.filter(models.User.role == role.strip().upper())

    rows = query.order_by(models.User.created_at.desc(), models.User.id.desc()).limit(limit).all()

    pending_count = (
        db.query(models.User).filter(models.User.status == models.STATUS_PENDING).count()
    )

    return schemas.UserListOut(
        total=len(rows),
        pending_count=pending_count,
        users=[_to_admin_out(db, u) for u in rows],
    )


@router.get("/users/pending", response_model=schemas.UserListOut)
def list_pending_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """The review queue — registrations waiting for a decision."""
    rows = (
        db.query(models.User)
        .filter(models.User.status == models.STATUS_PENDING)
        .order_by(models.User.created_at.asc())
        .all()
    )
    return schemas.UserListOut(
        total=len(rows),
        pending_count=len(rows),
        users=[_to_admin_out(db, u) for u in rows],
    )


@router.get("/users/{user_id}", response_model=schemas.AdminUserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return _to_admin_out(db, user)


# ---------------------------------------------------------------------------
# 2. Acting on users
# ---------------------------------------------------------------------------
@router.post("/users/{user_id}/approve", response_model=schemas.AdminUserOut)
def approve_user(
    user_id: int,
    payload: schemas.StatusChangeRequest = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    target = _load_target(db, user_id, admin)
    return _apply_status(
        db, admin, target, models.STATUS_APPROVED, "USER_APPROVED",
        (payload.reason if payload else None),
    )


@router.post("/users/{user_id}/reject", response_model=schemas.AdminUserOut)
def reject_user(
    user_id: int,
    payload: schemas.StatusChangeRequest = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    target = _load_target(db, user_id, admin)
    return _apply_status(
        db, admin, target, models.STATUS_REJECTED, "USER_REJECTED",
        (payload.reason if payload else None),
    )


@router.post("/users/{user_id}/suspend", response_model=schemas.AdminUserOut)
def suspend_user(
    user_id: int,
    payload: schemas.StatusChangeRequest = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    target = _load_target(db, user_id, admin)
    return _apply_status(
        db, admin, target, models.STATUS_SUSPENDED, "USER_SUSPENDED",
        (payload.reason if payload else None),
    )


@router.post("/users/{user_id}/reactivate", response_model=schemas.AdminUserOut)
def reactivate_user(
    user_id: int,
    payload: schemas.StatusChangeRequest = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Bring a suspended or rejected account back to APPROVED."""
    target = _load_target(db, user_id, admin)
    if (target.status or "").upper() not in (models.STATUS_SUSPENDED, models.STATUS_REJECTED):
        raise HTTPException(
            status_code=400,
            detail="Only suspended or rejected accounts can be reactivated.",
        )
    return _apply_status(
        db, admin, target, models.STATUS_APPROVED, "USER_REACTIVATED",
        (payload.reason if payload else None),
    )


# ---------------------------------------------------------------------------
# 3. Audit log (section 6)
# ---------------------------------------------------------------------------
@router.get("/audit-logs", response_model=schemas.AuditLogListOut)
def list_audit_logs(
    action: Optional[str] = None,
    actor_id: Optional[int] = None,
    target_type: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Read the audit trail. There is deliberately no endpoint to edit or delete
    entries — the log is append-only.
    """
    query = db.query(models.AuditLog)
    if action:
        query = query.filter(models.AuditLog.action == action.strip().upper())
    if actor_id:
        query = query.filter(models.AuditLog.actor_id == actor_id)
    if target_type:
        query = query.filter(models.AuditLog.target_type == target_type.strip().upper())

    total = query.count()
    rows = (
        query.order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc())
        .limit(limit)
        .all()
    )
    return schemas.AuditLogListOut(
        total=total,
        entries=[schemas.AuditLogOut.model_validate(r) for r in rows],
    )


# ---------------------------------------------------------------------------
# 4. users.pdf (section 7)
# ---------------------------------------------------------------------------
@router.get("/users/export/pdf")
def export_users_pdf(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Download `users.pdf`: Name, Role, Email, Status.

    The query selects exactly those four columns. `password_hash` is never read
    here, so there is no path by which password material could reach the file —
    and of course no plaintext password exists anywhere to leak in the first
    place.
    """
    if not reportlab_available():
        raise HTTPException(status_code=503, detail=PDF_UNAVAILABLE_MESSAGE)

    rows = (
        db.query(models.User.name, models.User.email, models.User.role, models.User.status)
        .order_by(models.User.role, models.User.name)
        .all()
    )
    users = [
        {"name": r[0], "email": r[1], "role": r[2], "status": r[3] or models.STATUS_PENDING}
        for r in rows
    ]

    pdf_bytes = build_users_pdf(users, generated_by=admin.name)

    audit.record(
        db,
        action="USERS_EXPORTED",
        actor=admin,
        target_type="USER",
        target_label="all users",
        details=f"Exported users.pdf containing {len(users)} account(s).",
    )
    db.commit()

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="users.pdf"'},
    )
