"""
Phase 3B, section 6 — the audit log.

One function, `record()`, is the only way anything writes to `audit_logs`.
Nothing in the application ever updates or deletes a row: the table is
append-only by convention, and there is deliberately no endpoint that edits or
removes entries.

Every event answers four questions: WHO did it, WHAT they did, to WHOM, and
WHEN — plus free-text details for the "why".
"""
from typing import Optional

from sqlalchemy.orm import Session

from . import models


def record(
    db: Session,
    action: str,
    actor: Optional[models.User] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    target_label: Optional[str] = None,
    details: Optional[str] = None,
    actor_name: Optional[str] = None,
    actor_role: Optional[str] = None,
) -> models.AuditLog:
    """
    Append one audit entry. The caller is responsible for `db.commit()`, so the
    audit row lands in the same transaction as the change it describes — either
    both are saved or neither is, and the log can never drift from reality.

    `actor` is None for anonymous or system events (e.g. someone submitting an
    emergency-access request before they have an account); pass `actor_name`
    explicitly in that case so the entry still says who it was.
    """
    entry = models.AuditLog(
        actor_id=actor.id if actor else None,
        actor_name=actor_name or (actor.name if actor else "System"),
        actor_role=actor_role or (actor.role if actor else "SYSTEM"),
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
    )
    db.add(entry)
    return entry


def describe_status_change(old_status: str, new_status: str, reason: Optional[str]) -> str:
    """Consistent wording for the account-status entries."""
    text = f"Status changed from {old_status or 'UNKNOWN'} to {new_status}."
    if reason:
        text += f" Reason: {reason}"
    return text
