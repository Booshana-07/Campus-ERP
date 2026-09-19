"""
Phase 2, Feature 7 — notification centre endpoints.

Plain REST over the existing SQLite database. The frontend polls
GET /api/notifications every few seconds (Feature 8). No extra infrastructure.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from ..notifications import visible_notifications_query

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=schemas.NotificationSummary)
def list_notifications(
    limit: int = 20,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Latest notifications this user is allowed to see, newest first."""
    q = visible_notifications_query(db, user)
    unread = q.filter(models.Notification.is_read == 0).count()
    rows = q.order_by(models.Notification.created_at.desc(), models.Notification.id.desc()).limit(limit).all()
    return schemas.NotificationSummary(
        unread_count=unread,
        notifications=[schemas.NotificationOut.model_validate(r) for r in rows],
    )


@router.put("/{notification_id}/read", response_model=schemas.NotificationOut)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    note = visible_notifications_query(db, user).filter(
        models.Notification.id == notification_id
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.is_read = 1
    db.commit()
    db.refresh(note)
    return schemas.NotificationOut.model_validate(note)


@router.put("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    rows = visible_notifications_query(db, user).filter(models.Notification.is_read == 0).all()
    for r in rows:
        r.is_read = 1
    db.commit()
    return {"marked_read": len(rows)}
