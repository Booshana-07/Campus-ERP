"""
SENSORA — Phase 3A: real email + password authentication.

Replaces the Phase 1/2 demo login (which accepted any seeded email with no
password at all). What this router provides:

    POST /api/auth/signup  — self-registration as STUDENT or FACULTY
    POST /api/auth/login   — email + password, returns a signed token
    GET  /api/auth/me      — who am I, according to the token
    POST /api/auth/logout  — end the session

The `/api/auth/demo-users` endpoint has been REMOVED: it listed every account
in the database to anyone who asked, which is exactly the kind of credential
exposure Phase 3A is meant to close.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import audit, models, notifications, schemas, security
from ..database import get_db
from ..deps import ROLE_FACULTY, ROLE_STUDENT, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Roles a user is allowed to choose for themselves. ADMIN is intentionally absent.
SELF_SIGNUP_ROLES = (ROLE_STUDENT, ROLE_FACULTY)

# Messages shown for each non-approved account state, exactly as specified.
STATUS_MESSAGES = {
    models.STATUS_PENDING: "Your account is pending administrator approval.",
    models.STATUS_REJECTED: "Your account has been rejected.",
    models.STATUS_SUSPENDED: "Your account is currently suspended.",
}


def _normalise_email(raw: str) -> str:
    return (raw or "").strip().lower()


# ---------------------------------------------------------------------------
# SIGNUP
# ---------------------------------------------------------------------------
@router.post("/signup", response_model=schemas.SignupResponse, status_code=201)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)):
    """
    Create a STUDENT or FACULTY account. The account is created with status
    PENDING and cannot log in until an administrator approves it.
    """
    full_name = (payload.full_name or "").strip()
    email = _normalise_email(payload.email)
    role = (payload.role or "").strip().upper()

    if len(full_name) < 2:
        raise HTTPException(status_code=422, detail="Please enter your full name.")

    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")

    # Rule 3: users must never be able to make themselves an administrator.
    # Checked against an allow-list rather than by blocking "ADMIN", so a typo
    # or an unexpected value can never slip through.
    if role not in SELF_SIGNUP_ROLES:
        raise HTTPException(
            status_code=422,
            detail="You may register as STUDENT or FACULTY only. "
                   "Administrator accounts are created internally.",
        )

    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")

    # Rule 4: the backend validates strength independently of the frontend.
    problems = security.validate_password_strength(payload.password)
    if problems:
        raise HTTPException(status_code=422, detail="Weak password. " + " ".join(problems))

    # Rule 4: no duplicate email addresses.
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="An account with this email address already exists.",
        )

    user = models.User(
        name=full_name,
        email=email,
        role=role,
        password_hash=security.hash_password(payload.password),
        status=models.STATUS_PENDING,  # Rule 5: never auto-approve
    )
    db.add(user)
    db.flush()  # assign the id before notifying/auditing

    # Phase 3B: admin is told a registration needs review, and the event is
    # audited. Both use the existing systems — no parallel machinery.
    notifications.notify_new_registration(db, user)
    audit.record(
        db,
        action="USER_REGISTERED",
        actor=None,
        actor_name=f"{user.name} ({user.email})",
        actor_role="ANONYMOUS",
        target_type="USER",
        target_id=user.id,
        target_label=user.email,
        details=f"Self-registered as {user.role}. Awaiting administrator approval.",
    )

    db.commit()
    db.refresh(user)

    return schemas.SignupResponse(
        message="Account created. Your account is pending administrator approval.",
        user=schemas.UserOut.model_validate(user),
    )


# ---------------------------------------------------------------------------
# LOGIN
# ---------------------------------------------------------------------------
@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with email + password.

    An unknown email and a wrong password deliberately return the SAME 401
    message. Distinguishing them would let anyone enumerate which email
    addresses have accounts on the platform.
    """
    email = _normalise_email(payload.email)
    user = db.query(models.User).filter(models.User.email == email).first()

    generic_failure = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )

    if not user:
        # Still spend the time hashing, so that a missing account and a wrong
        # password take a similar amount of time to answer (timing attacks).
        security.hash_password(payload.password or "placeholder")
        raise generic_failure

    if not security.verify_password(payload.password, user.password_hash):
        raise generic_failure

    # Rule 6: the account state decides what happens next, and it is decided
    # HERE, on the server. No token is issued unless the account is APPROVED,
    # so there is nothing for the frontend to "unlock" by manipulation.
    account_status = (user.status or models.STATUS_PENDING).upper()
    if account_status != models.STATUS_APPROVED:
        # Phase 3B: a blocked sign-in attempt is security-relevant, so it is
        # audited before the request is refused.
        audit.record(
            db,
            action="LOGIN_BLOCKED",
            actor=user,
            target_type="USER",
            target_id=user.id,
            target_label=user.email,
            details=f"Sign-in refused: account status is {account_status}.",
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=STATUS_MESSAGES.get(
                account_status, "Your account is not currently active."
            ),
        )

    # Phase 3B: an expired temporary emergency grant must not still sign in.
    if user.is_access_expired:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your temporary emergency access has expired.",
        )

    # Opportunistic upgrade: if the deployment has since installed bcrypt, move
    # this user's hash over on a successful login. Transparent to the user.
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(payload.password)
        db.commit()
        db.refresh(user)

    token, expires_in = security.create_access_token(user.id, user.email, user.role)

    audit.record(
        db,
        action="LOGIN_SUCCESS",
        actor=user,
        target_type="USER",
        target_id=user.id,
        target_label=user.email,
        details=f"Signed in as {user.role}.",
    )
    db.commit()

    return schemas.TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=schemas.UserOut.model_validate(user),
    )


# ---------------------------------------------------------------------------
# SESSION
# ---------------------------------------------------------------------------
@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    """
    Resolve the current user from the token. The frontend calls this on page
    load so a token that was revoked, expired, or whose account was suspended
    is caught immediately instead of being trusted from browser storage.
    """
    return user


@router.post("/logout")
def logout(user: models.User = Depends(get_current_user)):
    """
    End the session. These tokens are stateless and short-lived, so the
    authoritative action is the client discarding the token — which the
    frontend does on logout. This endpoint confirms the session was valid and
    gives Phase 3B+ a single place to hang server-side revocation if needed.
    """
    return {"message": f"Signed out. Goodbye, {user.name}."}
