# SENSORA — Phase 3A

## Real Email + Password Authentication

Phase 3A replaces the demo login with genuine authentication. Everything built
in Phase 1 and Phase 2 keeps working; this phase changes *how a user proves who
they are*, not what the platform does.

---

## 1. What changed, in one paragraph

Phase 1/2 logged you in with an email address alone, and every subsequent API
call identified the caller with an `X-User-Email` header. That was never
authentication — anyone could run
`curl -H "X-User-Email: admin@campus.edu" .../api/dashboard/analytics` and get
full administrator data. Phase 3A adds password hashing, a signup flow, account
statuses, and a signed session token that the backend verifies on every request.

---

## 2. Authentication architecture

```
  Browser                         FastAPI backend
  ───────                         ───────────────
  POST /api/auth/login  ────────► verify password against stored hash
  { email, password }             check account status == APPROVED
                                  │
                        ◄──────── { access_token, expires_in, user }
                                  (no token is issued unless BOTH pass)

  Every later request:
  Authorization: Bearer <token> ► verify signature + expiry
                                  load the user from the database
                                  re-check status is still APPROVED
                                  re-check role for the endpoint
```

**Key files**

| File | Role |
|---|---|
| `backend/app/security.py` | Password hashing, strength rules, token signing/verifying |
| `backend/app/routers/auth.py` | `/signup`, `/login`, `/me`, `/logout` |
| `backend/app/deps.py` | Extracts and validates the bearer token; role guards |
| `backend/app/migrate.py` | Additive migration + backfill of existing users |
| `frontend/src/api/client.js` | Attaches the token; clears the session on 401 |
| `frontend/src/context/AuthContext.jsx` | Holds the session; revalidates on load |
| `frontend/src/utils/password.js` | Frontend mirror of the password rules |

### Session tokens

Tokens are **JWTs signed with HS256**. They carry `sub` (user id), `email`,
`role`, `iat` and `exp`, and expire after `SENSORA_TOKEN_EXPIRY_HOURS` (default
12).

Two deliberate decisions:

- **The role in the token is not trusted for authorisation.** The user is loaded
  from the database on every request and the role is read from there. A forged
  token is rejected by the signature check first, but even a valid token cannot
  carry a stale or elevated role into a decision.
- **Account status is never read from the token.** It is re-read from the
  database each request, so suspending an account takes effect on that user's
  very next request rather than whenever their token happens to expire.

The signing secret comes from `SENSORA_SECRET_KEY`. If unset in development, one
is generated and persisted to `backend/.sensora_secret` (gitignored) so a server
restart doesn't sign everybody out. **Set it explicitly for any real deployment.**

---

## 3. Password security

Passwords are **never stored, logged, or returned** in plaintext. Only a hash is
written to `users.password_hash`, and no schema or endpoint exposes that column.

Two standard schemes are supported, chosen automatically:

| Scheme | When used | Notes |
|---|---|---|
| **bcrypt** (cost 12) | When the `bcrypt` package is installed | Preferred. Input is SHA-256 pre-hashed and base64-encoded so bcrypt's 72-byte limit can't silently truncate a long passphrase |
| **PBKDF2-HMAC-SHA256** (600,000 iterations) | Fallback, from the standard library | RFC 8018. Meets the current OWASP iteration floor |

No custom cryptography was written. The fallback exists so an existing Phase 1/2
virtualenv that hasn't re-run `pip install -r requirements.txt` still boots
instead of crashing on a missing import.

Stored hashes are **self-describing** (`bcrypt$...` or `pbkdf2_sha256$...`), so
a database can hold a mix of both and every row still verifies. When a
PBKDF2 user logs in on a deployment that has since installed bcrypt, their hash
is transparently upgraded on that login.

Verification uses a constant-time comparison. On login, an unknown email still
performs a hash operation so that "no such account" and "wrong password" take a
similar amount of time.

---

## 4. Signup flow

`POST /api/auth/signup`

```json
{
  "full_name": "Nisha Reddy",
  "email": "nisha@campus.edu",
  "password": "Str0ng!Pass",
  "confirm_password": "Str0ng!Pass",
  "role": "STUDENT"
}
```

| Rule | Behaviour |
|---|---|
| Role | **STUDENT or FACULTY only.** Checked against an allow-list, so `ADMIN`, `admin`, or any unexpected value is rejected with 422 |
| Email | Must be a valid address; normalised to lowercase |
| Duplicate email | 409 Conflict (case-insensitive) |
| Password | Must satisfy all five rules below, validated on the backend |
| Confirm password | Must match |
| Status | Always created as **PENDING** |

Signup returns the new user and a message — **never a token**. A new account
cannot be used until an administrator approves it.

### Password rules

Minimum 8 characters, plus at least one uppercase letter, one lowercase letter,
one number, and one special character.

These are enforced in **two independent places**:

- `backend/app/security.py` → `validate_password_strength()` — the authority
- `frontend/src/utils/password.js` → live checklist and strength bar while typing

The frontend copy is for feedback only. Bypassing it changes nothing: the
backend rejects the request anyway. *(If you change a rule, change it in both
files — a parity test is described in section 8.)*

---

## 5. Account statuses

| Status | Meaning |
|---|---|
| `PENDING` | Registered, awaiting administrator approval. **Default for all new signups** |
| `APPROVED` | Normal access, according to the user's role |
| `REJECTED` | Registration was declined |
| `SUSPENDED` | Access temporarily withdrawn |

### Login behaviour

| Status | Result |
|---|---|
| `APPROVED` | Token issued; user lands on the page for their role |
| `PENDING` | 403 — "Your account is pending administrator approval." |
| `REJECTED` | 403 — "Your account has been rejected." |
| `SUSPENDED` | 403 — "Your account is currently suspended." |

**These cannot be bypassed from the frontend.** A non-approved account never
receives a token at all, so there is nothing stored in the browser to tamper
with. Editing `sessionStorage` to claim a different role or status changes the
sidebar and nothing else — every protected endpoint re-reads the real role and
status from the database.

The administrator interface for moving accounts between these states arrives in
**Phase 3B**. The statuses, the storage and the enforcement all work now.

---

## 6. API reference

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/signup` | none | Register as STUDENT or FACULTY (creates a PENDING account) |
| POST | `/api/auth/login` | none | Email + password → session token |
| GET | `/api/auth/me` | Bearer | The signed-in user; used to revalidate a stored session |
| POST | `/api/auth/logout` | Bearer | End the session |

`GET /api/auth/demo-users` has been **removed**. It listed every account in the
database to any anonymous caller.

### Status codes

| Code | Meaning |
|---|---|
| 401 | Not signed in, or invalid email/password |
| 403 | Signed in, but account not APPROVED or role not permitted |
| 409 | Email already registered |
| 422 | Validation failure (weak password, mismatch, bad role, bad email) |

Invalid email and invalid password return the **same** 401 message, so the API
cannot be used to discover which email addresses have accounts.

---

## 7. Database migration

**No table is dropped, recreated, or reset. No existing row is deleted.** All
Phase 1 and Phase 2 data survives.

Three columns are added to `users`:

| Column | Type | Purpose |
|---|---|---|
| `password_hash` | VARCHAR | The hashed password |
| `status` | VARCHAR | PENDING / APPROVED / REJECTED / SUSPENDED |
| `created_at` | DATETIME | Registration timestamp |

Two steps run automatically at startup, both idempotent:

1. **`run_migrations(engine)`** — `ALTER TABLE users ADD COLUMN ...` for any
   column that isn't already there. This extends the existing Phase 2
   migration; the Phase 2 entries are untouched.
2. **`backfill_users(engine)`** — fills the new columns for rows that predate
   Phase 3A:
   - `status` → `APPROVED`. Accounts that already existed were trusted under
     Phase 1/2; marking them PENDING would lock a working system out.
   - `created_at` → now, where unknown.
   - `password_hash` → a hash of `DEMO_USER_PASSWORD` (default `Campus@2025`),
     so existing accounts remain usable after the upgrade.

Only `NULL` values are ever written. Running the backfill a second time is a
no-op, so restarting the server repeatedly is safe.

> The columns are added as nullable on purpose. SQLite cannot add a `NOT NULL`
> column to a table that already contains rows, and forcing one would mean
> rebuilding the table — which is exactly the kind of destructive operation this
> phase must avoid. Nullable-then-backfill is the safe route.

### Demo accounts

The three seeded accounts keep their emails and now have real passwords:

| Email | Role |
|---|---|
| `student@campus.edu` | STUDENT |
| `faculty@campus.edu` | FACULTY |
| `admin@campus.edu` | ADMIN |

Password for all three: whatever `DEMO_USER_PASSWORD` is set to in
`backend/.env` (default **`Campus@2025`**).

This value is documented here and configured in `.env` — it does **not** appear
anywhere in the frontend source, the UI, or any API response. Change it before
any shared demo.

---

## 8. Testing

### Automated

Two suites accompany this phase:

- **Migration safety** — builds a database matching a Phase 2 install (users,
  incidents, status history, notifications, response teams), runs the real
  migration twice, and asserts that every row count is unchanged, that incident
  data is byte-identical, that the migration is idempotent, and that every
  migrated user can log in with the demo password.
- **Authentication** — 41 cases covering signup, rejections, login, all four
  account statuses, token handling, role enforcement and the full lifecycle.

Notable security cases covered: forging an `ADMIN` role inside a token,
tampering with the signature, `alg: none` substitution, replaying an expired
token, spoofing the old `X-User-Email` value, using a token for a deleted
account, and suspending an account mid-session.

### Manual checklist

| # | Test | Expected |
|---|---|---|
| 1 | Sign up as STUDENT with a strong password | Success screen, "pending approval" |
| 2 | Sign up as FACULTY | Same |
| 3 | Sign up with an existing email | "An account with this email address already exists." |
| 4 | Sign up with `password1` | Blocked; checklist shows which rules fail |
| 5 | Mismatched confirm password | "Passwords do not match." |
| 6 | Log in with an unregistered email | "Invalid email or password." |
| 7 | Log in with the wrong password | Same message as #6 |
| 8 | Log in as the new PENDING user | "Your account is pending administrator approval." |
| 9 | Set that user's status to `REJECTED`, log in | "Your account has been rejected." |
| 10 | Set to `SUSPENDED`, log in | "Your account is currently suspended." |
| 11 | Set to `APPROVED`, log in | Lands on the role's home page |
| 12 | Log out | Returns to login; the back button does not restore the session |
| 13 | `curl http://localhost:8000/api/teams` with no header | 401 |
| 14 | `curl -H "X-User-Email: admin@campus.edu" .../api/dashboard/analytics` | 401 — the Phase 2 bypass is closed |
| 15 | Log in as STUDENT, call an admin endpoint with that token | 403 |

Until Phase 3B ships the approval screen, change a status directly:

```bash
cd backend
sqlite3 campus_emergency.db \
  "UPDATE users SET status='APPROVED' WHERE email='nisha@campus.edu';"
```

### Phase 1 + Phase 2 regression

After signing in, confirm: reporting an emergency with AI classification, the
priority queue and smart queue, team recommendation and assignment with
override, the incident timeline, notifications, analytics, and the campus map.
Students still see only their own incidents; faculty and admin see all.

---

## 9. Security notes

**Fixed in this phase**

- Passwords are hashed with a standard KDF; plaintext is never stored
- The spoofable `X-User-Email` header is gone; sessions use signed tokens
- Account status is enforced on the server, on every request
- Users cannot make themselves administrators
- The endpoint that listed every account was removed
- No credentials appear in the UI or frontend source
- Login errors don't reveal whether an email is registered

**Deliberately deferred**

- Admin approval interface → Phase 3B
- Password reset / email verification → later phase
- Refresh tokens and server-side revocation — tokens are stateless and
  short-lived; `/api/auth/logout` is the hook for adding a denylist later
- Rate limiting on login attempts
- CORS is still `allow_origins=["*"]` — tighten before any real deployment

---

## 10. Configuration

`backend/.env` (see `.env.example`):

```bash
SENSORA_SECRET_KEY=            # blank in dev → generated into .sensora_secret
SENSORA_TOKEN_EXPIRY_HOURS=12
DEMO_USER_PASSWORD=Campus@2025
```

Install the recommended auth packages:

```bash
cd backend
pip install -r requirements.txt   # adds bcrypt and PyJWT
```

Both are optional at runtime — the app falls back to standard-library
equivalents if they're absent — but bcrypt is the stronger password KDF and is
recommended. The active scheme is printed at startup:

```
[security] Password hashing scheme: bcrypt
```

---

## 11. Next

**Phase 3B** — the administrator approval interface: pending-account queue,
approve/reject/suspend actions, and the audit trail behind them.

Sequence: Phase 3A → **3B** → 3C → 3D → 3E FINAL.
