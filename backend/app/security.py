"""
SENSORA — Phase 3A
Password hashing, password-strength rules, and signed session tokens.

Design notes
------------
1. NO custom crypto is invented here. Two standard, well-reviewed schemes are
   supported for password hashing:

     * bcrypt           — used automatically if the `bcrypt` package is installed
                          (it is listed in requirements.txt).
     * PBKDF2-HMAC-SHA256 — RFC 8018, from Python's standard library `hashlib`.
                          Used as the fallback so the backend still starts on an
                          environment where `bcrypt` has not been installed yet.

   Both are real, standard KDFs. The fallback exists purely so that an existing
   Phase 1/Phase 2 virtualenv that has not re-run `pip install -r requirements.txt`
   keeps booting instead of crashing on import.

2. Stored hashes are self-describing (`scheme$...`), so a database can hold a
   mix of both schemes and every row still verifies correctly. This also means
   switching a deployment from PBKDF2 to bcrypt later needs no data migration.

3. Session tokens are JWTs (HS256). PyJWT is used if installed; otherwise an
   equivalent stdlib HS256 implementation produces and validates the exact same
   wire format. Signature comparison is constant-time and the `alg` header is
   checked strictly (no `none`, no algorithm confusion).
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets
from typing import Optional, Tuple

# --------------------------------------------------------------------------
# Optional dependencies
# --------------------------------------------------------------------------
try:  # pragma: no cover - depends on the environment
    import bcrypt as _bcrypt
except ImportError:  # pragma: no cover
    _bcrypt = None

try:  # pragma: no cover
    import jwt as _pyjwt
except ImportError:  # pragma: no cover
    _pyjwt = None


# ==========================================================================
# 1. SECRET KEY
# ==========================================================================
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SECRET_FILE = os.path.join(_BASE_DIR, ".sensora_secret")


def _load_or_create_secret() -> str:
    """
    Resolve the signing secret, in order of preference:
      1. SENSORA_SECRET_KEY from the environment / backend/.env
      2. a persisted random secret in backend/.sensora_secret

    The file-backed fallback means tokens survive a server restart during
    development instead of logging everybody out, while still never shipping a
    hard-coded secret in source control (the file is gitignored).
    """
    env_secret = os.getenv("SENSORA_SECRET_KEY", "").strip()
    if env_secret:
        return env_secret

    try:
        if os.path.exists(_SECRET_FILE):
            with open(_SECRET_FILE, "r", encoding="utf-8") as fh:
                saved = fh.read().strip()
            if saved:
                return saved

        generated = secrets.token_urlsafe(48)
        with open(_SECRET_FILE, "w", encoding="utf-8") as fh:
            fh.write(generated)
        try:
            os.chmod(_SECRET_FILE, 0o600)
        except OSError:
            pass  # Windows / restricted filesystems — not fatal
        print(
            "[security] No SENSORA_SECRET_KEY set. Generated one and stored it in "
            "backend/.sensora_secret (gitignored). Set SENSORA_SECRET_KEY in "
            "backend/.env for a fixed secret."
        )
        return generated
    except OSError:
        # Read-only filesystem: fall back to a per-process secret. Tokens then
        # only live as long as the server process does.
        print("[security] WARNING: could not persist a secret key; using a per-process key.")
        return secrets.token_urlsafe(48)


SECRET_KEY = _load_or_create_secret()
TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = int(os.getenv("SENSORA_TOKEN_EXPIRY_HOURS", "12"))


# ==========================================================================
# 2. PASSWORD HASHING
# ==========================================================================
PBKDF2_ITERATIONS = 600_000  # OWASP-recommended floor for PBKDF2-HMAC-SHA256
BCRYPT_ROUNDS = 12


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _bcrypt_prepare(password: str) -> bytes:
    """
    bcrypt silently truncates input beyond 72 bytes. Pre-hashing with SHA-256
    and base64-encoding is the standard mitigation, so long passphrases keep
    their full entropy.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """
    Hash a plaintext password for storage. Never store the plaintext anywhere.
    Returns a self-describing string, e.g.
        "bcrypt$$2b$12$..."  or  "pbkdf2_sha256$600000$<salt>$<hash>"
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    if _bcrypt is not None:
        hashed = _bcrypt.hashpw(_bcrypt_prepare(password), _bcrypt.gensalt(BCRYPT_ROUNDS))
        return "bcrypt$" + hashed.decode("ascii")

    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64e(salt)}${_b64e(derived)}"


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    """
    Check a plaintext password against a stored hash.
    Returns False (never raises) for missing, malformed or unknown-scheme hashes.
    """
    if not password or not stored_hash:
        return False

    try:
        # --- bcrypt (prefixed, or a bare bcrypt string) ---
        if stored_hash.startswith("bcrypt$") or stored_hash.startswith("$2"):
            if _bcrypt is None:
                print(
                    "[security] A bcrypt hash was found but the `bcrypt` package is not "
                    "installed. Run: pip install -r requirements.txt"
                )
                return False
            raw = stored_hash[len("bcrypt$"):] if stored_hash.startswith("bcrypt$") else stored_hash
            return _bcrypt.checkpw(_bcrypt_prepare(password), raw.encode("ascii"))

        # --- PBKDF2-HMAC-SHA256 ---
        if stored_hash.startswith("pbkdf2_sha256$"):
            _, iterations, salt_b64, hash_b64 = stored_hash.split("$", 3)
            derived = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), _b64d(salt_b64), int(iterations)
            )
            return hmac.compare_digest(derived, _b64d(hash_b64))
    except (ValueError, TypeError, IndexError):
        return False

    return False


def needs_rehash(stored_hash: Optional[str]) -> bool:
    """True when a stored hash uses a weaker scheme than the one now available."""
    if not stored_hash:
        return False
    if _bcrypt is not None and stored_hash.startswith("pbkdf2_sha256$"):
        return True
    return False


# ==========================================================================
# 3. PASSWORD STRENGTH RULES
# ==========================================================================
PASSWORD_MIN_LENGTH = 8
SPECIAL_CHARACTERS = "!@#$%^&*()-_=+[]{};:'\",.<>/?\\|`~"

PASSWORD_RULES_TEXT = (
    "Password must be at least 8 characters and include an uppercase letter, "
    "a lowercase letter, a number and a special character."
)


def validate_password_strength(password: str) -> list:
    """
    Return a list of human-readable problems. An empty list means the password
    is acceptable. The frontend mirrors these exact rules for live feedback,
    but this backend copy is the one that actually decides.
    """
    problems = []
    if not isinstance(password, str):
        return ["Password must be text."]

    if len(password) < PASSWORD_MIN_LENGTH:
        problems.append(f"Must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if not any(c.isupper() for c in password):
        problems.append("Must contain an uppercase letter (A-Z).")
    if not any(c.islower() for c in password):
        problems.append("Must contain a lowercase letter (a-z).")
    if not any(c.isdigit() for c in password):
        problems.append("Must contain a number (0-9).")
    if not any(c in SPECIAL_CHARACTERS for c in password):
        problems.append("Must contain a special character (e.g. ! @ # $ %).")
    return problems


# ==========================================================================
# 4. SESSION TOKENS (JWT, HS256)
# ==========================================================================
def _stdlib_jwt_encode(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64e(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64e(signature))
    return ".".join(segments)


def _stdlib_jwt_decode(token: str, secret: str) -> dict:
    """Validate signature + expiry. Raises ValueError on any problem."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token.")

    header_b64, payload_b64, signature_b64 = parts

    header = json.loads(_b64d(header_b64))
    # Strict algorithm check — blocks "alg: none" and algorithm-confusion attacks.
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported token algorithm.")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64d(signature_b64)):
        raise ValueError("Invalid token signature.")

    payload = json.loads(_b64d(payload_b64))
    exp = payload.get("exp")
    if exp is not None and datetime.datetime.utcnow().timestamp() > float(exp):
        raise ValueError("Token has expired.")
    return payload


def create_access_token(user_id: int, email: str, role: str) -> Tuple[str, int]:
    """
    Issue a signed token for a user. Returns (token, expires_in_seconds).

    The token carries identity only. Account status is deliberately NOT trusted
    from the token — it is re-read from the database on every request, so
    suspending or rejecting an account takes effect immediately rather than
    when the token happens to expire.
    """
    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    if _pyjwt is not None:
        token = _pyjwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGORITHM)
        if isinstance(token, bytes):  # PyJWT < 2 returned bytes
            token = token.decode("ascii")
    else:
        token = _stdlib_jwt_encode(payload, SECRET_KEY)

    return token, int(TOKEN_EXPIRY_HOURS * 3600)


def decode_access_token(token: str) -> Optional[dict]:
    """Return the token payload, or None if the token is invalid or expired."""
    if not token:
        return None
    try:
        if _pyjwt is not None:
            return _pyjwt.decode(token, SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        return _stdlib_jwt_decode(token, SECRET_KEY)
    except Exception:
        # Any failure (bad signature, expiry, malformed) is simply "not authenticated".
        return None


def hashing_scheme_in_use() -> str:
    """Reported at startup so it is obvious which KDF is active."""
    return "bcrypt" if _bcrypt is not None else f"pbkdf2_sha256 ({PBKDF2_ITERATIONS:,} iterations)"
