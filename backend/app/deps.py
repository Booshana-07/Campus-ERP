"""
Role-based access control and authentication, enforced on the BACKEND.

Phase 2 identified the caller from an `X-User-Email` header. That was fine for a
demo but it was not authentication: anyone could send
`X-User-Email: admin@campus.edu` with curl and get full administrator access.

Phase 3A replaces it with a signed bearer token that only `/api/auth/login`
can issue, and only after verifying a password hash. The header is no longer
trusted, so hiding a button in React was never — and still is not — the thing
protecting an admin action.

Account status is re-read from the database on every single request rather than
being trusted from inside the token. Suspending an account therefore takes
effect on the user's very next request, not whenever their token expires.
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_access_token

ROLE_STUDENT = "STUDENT"
ROLE_FACULTY = "FACULTY"
ROLE_ADMIN = "ADMIN"

# Phase 3A: the message shown for each blocked account state.
STATUS_MESSAGES = {
    models.STATUS_PENDING: "Your account is pending administrator approval.",
    models.STATUS_REJECTED: "Your account has been rejected.",
    models.STATUS_SUSPENDED: "Your account is currently suspended.",
}

_NOT_AUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not signed in. Please log in again.",
    headers={"WWW-Authenticate": "Bearer"},
)


def _extract_bearer_token(authorization: str) -> str:
    """Pull the token out of an `Authorization: Bearer <token>` header."""
    if not authorization:
        return ""
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def _resolve_user(authorization: str, db: Session):
    """Shared lookup: valid token -> the matching user row, else None."""
    token = _extract_bearer_token(authorization)
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None  # bad signature, tampered, malformed or expired

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None  # account deleted since the token was issued

    # The token also carries the email it was issued for. If the account's email
    # has since changed, the old token should stop working.
    token_email = (payload.get("email") or "").lower()
    if token_email and token_email != (user.email or "").lower():
        return None

    return user


def _assert_account_active(user: models.User) -> models.User:
    """
    Block any account that is not APPROVED, whatever its role.
    This is what stops a PENDING/REJECTED/SUSPENDED user from reaching the API
    even if they somehow hold a token.

    Phase 3B adds the expiry check: a temporary emergency grant stops working
    the moment it runs out, without anybody having to revoke it by hand.
    """
    account_status = (user.status or models.STATUS_PENDING).upper()
    if account_status != models.STATUS_APPROVED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATUS_MESSAGES.get(account_status, "Your account is not currently active."),
        )
    if user.is_access_expired:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your temporary emergency access has expired.",
        )
    return user


def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> models.User:
    """Resolve and validate the caller. 401 if not signed in, 403 if not APPROVED."""
    user = _resolve_user(authorization, db)
    if not user:
        raise _NOT_AUTHENTICATED
    return _assert_account_active(user)


def get_optional_user(
    authorization: str = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """Same as above but returns None instead of raising — for read-only endpoints."""
    user = _resolve_user(authorization, db)
    if not user:
        return None
    account_status = (user.status or models.STATUS_PENDING).upper()
    return user if account_status == models.STATUS_APPROVED else None


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    """Allow only ADMIN. Used for assignment, status changes, dashboard analytics."""
    if user.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail=f"This action is restricted to ADMIN users. You are signed in as {user.role}.",
        )
    return user


def require_staff(user: models.User = Depends(get_current_user)) -> models.User:
    """Allow FACULTY and ADMIN (campus-wide incident visibility), but not STUDENT."""
    if user.role not in (ROLE_ADMIN, ROLE_FACULTY):
        raise HTTPException(
            status_code=403,
            detail=f"This view is restricted to Faculty and Admin users. You are signed in as {user.role}.",
        )
    return user


def require_permanent_account(user: models.User = Depends(get_current_user)) -> models.User:
    """
    Phase 3B — exclude temporary emergency-access accounts.

    Emergency access exists so somebody can REPORT an emergency and follow their
    own report. It is not a way to browse campus operational data such as the
    response-team roster. "Minimum necessary access" (section 5) is enforced
    here rather than by hiding a menu item.
    """
    if user.is_emergency_access:
        raise HTTPException(
            status_code=403,
            detail=(
                "Temporary emergency access is limited to reporting an emergency "
                "and viewing your own reports."
            ),
        )
    return user


def require_staff_permanent(user: models.User = Depends(require_staff)) -> models.User:
    """Staff-only AND not a temporary emergency account."""
    return require_permanent_account(user)


def can_view_incident(user: models.User, incident: models.Incident) -> bool:
    """
    Students may only open incidents they reported themselves.
    Faculty and Admin may view any incident.
    """
    if user.role in (ROLE_ADMIN, ROLE_FACULTY):
        return True
    if incident.reporter_user_id is not None:
        return incident.reporter_user_id == user.id
    # Older Phase 1 rows have no reporter_user_id — fall back to name matching.
    return (incident.reporter_name or "").strip().lower() == (user.name or "").strip().lower()
