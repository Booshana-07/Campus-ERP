# SENSORA — Phase 3B

## User Approval, Role Access & Security

Phase 3B completes the access-control layer that Phase 3A started:

```
Signup → PENDING → Admin review → Approve / Reject → Role-based access
                                                  ↘ Suspend / Reactivate
```

plus a controlled emergency route for people who have no approved account but a
real emergency to report, and an audit trail behind every security-sensitive
action.

Everything is additive. No table was dropped, no data reset, and Phase 1, 2 and
3A functionality is unchanged.

---

## 1. What Phase 3A left open

Phase 3A created the four account statuses and enforced them at login, but there
was no way to move an account between them except editing SQLite by hand. Phase
3B supplies the console, the emergency route around the queue, and the record of
who did what.

---

## 2. Approval workflow

### The journey

| Step | What happens | Who |
|---|---|---|
| 1 | User signs up at `/signup` | Anyone |
| 2 | Account is created **PENDING**; admin is notified; `USER_REGISTERED` audited | System |
| 3 | Account appears in the admin review queue | — |
| 4 | Admin approves or rejects, optionally with a reason | ADMIN |
| 5 | User is notified; the decision is audited | System |
| 6 | Approved users can sign in; rejected users cannot | — |

Later, an admin can **suspend** an active account and **reactivate** a suspended
or rejected one. Every transition notifies the user and writes an audit entry.

### Allowed transitions

| From | Available actions |
|---|---|
| PENDING | Approve, Reject |
| APPROVED | Suspend |
| REJECTED | Reactivate |
| SUSPENDED | Reactivate, Reject |

Redundant changes (approving an already-approved account) return 400 rather than
writing a meaningless audit entry.

### Three safety rules

1. **An admin cannot change their own status** — no accidental self-lockout.
2. **An admin cannot modify another ADMIN.** Administrator accounts are managed
   internally, consistent with the Phase 3A rule that nobody can make themselves
   an admin.
3. **Every change writes its audit entry in the same transaction** as the change
   itself, so the log can never drift from reality.

### Admin console

`/admin/users` — search by name or email, filter by status and role, and act on
any account. Shows registration date, who last reviewed the account and why, and
how many incidents each user has reported.

---

## 3. Role permissions

| Capability | STUDENT | FACULTY | ADMIN | Emergency (temp) |
|---|:---:|:---:|:---:|:---:|
| Submit emergency reports | ✅ | ✅ | ✅ | ✅ |
| View own incidents | ✅ | ✅ | ✅ | ✅ |
| Receive notifications | ✅ | ✅ | ✅ | ✅ |
| View campus incident queue | ❌ | ✅ | ✅ | ❌ |
| View response teams | ❌ | ✅ | ✅ | ❌ |
| Campus map | ✅ | ✅ | ✅ | ❌ |
| Assign response teams | ❌ | ❌ | ✅ | ❌ |
| Change incident status / priority | ❌ | ❌ | ✅ | ❌ |
| Override AI recommendation | ❌ | ❌ | ✅ | ❌ |
| Analytics & dashboard | ❌ | ❌ | ✅ | ❌ |
| Approve / reject / suspend users | ❌ | ❌ | ✅ | ❌ |
| Review emergency access | ❌ | ❌ | ✅ | ❌ |
| Read the audit log | ❌ | ❌ | ✅ | ❌ |
| Export users.pdf | ❌ | ❌ | ✅ | ❌ |

**Faculty never inherit admin permissions.** `require_staff` and `require_admin`
are separate guards; passing the first says nothing about the second.

Enforcement lives in `app/deps.py` and is applied per endpoint:

| Guard | Allows |
|---|---|
| `get_current_user` | Any signed-in, APPROVED, unexpired account |
| `require_staff` | FACULTY + ADMIN |
| `require_admin` | ADMIN only |
| `require_permanent_account` | Any approved account **except** temporary emergency grants |

---

## 4. Emergency access

### The problem

Someone witnesses a fire. Their registration hasn't been approved yet. Making
them wait is unacceptable; letting them straight in would make the approval
system meaningless.

### The design

`/emergency-access` on the login page. **Submitting a request grants nothing** —
no token, no account, no access. It creates a row and notifies the admin.

```
Requester submits          Admin reviews            Requester collects
─────────────────          ─────────────            ──────────────────
name, email, reason,   →   Approve (with a      →   reference code + email
emergency description,     duration) or Reject      → time-limited session
location, contact
        ↓                         ↓                         ↓
  reference code           audit + notify            audit EMERGENCY_ACCESS_USED
  (nothing else)
```

### What "minimum necessary access" means here

On approval the platform creates (or reuses) an account that is:

- **role STUDENT** — the lowest privilege level
- **flagged `is_emergency_access`** — `require_permanent_account` keeps it out of
  the team roster, campus map and every staff/admin endpoint
- **time-limited** via `access_expires_at`, re-checked on *every* request, so a
  grant stops working the moment it lapses without anyone revoking it
- **passwordless** — `password_hash` stays NULL, so it cannot be used for a
  normal login. The only way in is the reference code, before expiry.

Duration is chosen by the admin and **clamped server-side** to 15 minutes–24
hours, so a typo in the form cannot hand out an indefinite account.

### Collecting the grant

`GET /api/emergency-access/status/{reference_code}?email=...`

Both the code **and** the email must match. A mismatch returns the same 404 as a
non-existent code, so the endpoint cannot be used to probe for valid codes.

### Safeguards

| Risk | Mitigation |
|---|---|
| Used as a login bypass | No grant exists until an admin approves; submission returns only a reference code |
| Someone else collects the grant | Requires reference code **and** matching email |
| Probing for valid codes | Wrong code and wrong email return identical 404s |
| Spamming the admin during an emergency | A second request from the same email returns the existing reference |
| Grant never expires | Expiry is mandatory, clamped, and checked on every request |
| Emergency account browsing campus data | `require_permanent_account` blocks it |
| Downgrading a real account | An already-APPROVED account keeps its role and gets no expiry |

---

## 5. Audit log

`audit_logs` is **append-only**. Nothing updates or deletes a row, and no
endpoint exists that could.

Every entry records:

| Field | Meaning |
|---|---|
| `actor_id`, `actor_name`, `actor_role` | Who (denormalised, so it still reads correctly if the account changes later) |
| `action` | What |
| `target_type`, `target_id`, `target_label` | To whom |
| `details` | Why / extra context |
| `timestamp` | When |

### Events recorded

`USER_REGISTERED` · `USER_APPROVED` · `USER_REJECTED` · `USER_SUSPENDED` ·
`USER_REACTIVATED` · `LOGIN_SUCCESS` · `LOGIN_BLOCKED` ·
`EMERGENCY_ACCESS_REQUESTED` · `EMERGENCY_ACCESS_APPROVED` ·
`EMERGENCY_ACCESS_REJECTED` · `EMERGENCY_ACCESS_USED` · `USERS_EXPORTED`

Viewable at `/admin/audit-log`, filterable by event type.

---

## 6. users.pdf

`GET /api/admin/users/export/pdf` (ADMIN only) downloads a roster containing
exactly four fields: **Name, Role, Email, Status**. A sample is included at the
project root as `users.pdf`.

**It never contains passwords.** Three independent reasons:

1. The platform stores no plaintext password anywhere — only hashes.
2. The endpoint's query selects only those four columns; `password_hash` is
   never read into memory.
3. `pdf_export.py` filters its input through an explicit allow-list
   (`ALLOWED_FIELDS`), so credential material cannot reach the document even if
   a future caller passed it in. A test asserts this by deliberately passing
   both a plaintext password and a hash, then scanning the raw PDF bytes.

The export itself is audited (`USERS_EXPORTED`).

> reportlab is an optional dependency. Without it the endpoint returns a clear
> 503 and nothing else is affected.

---

## 7. Security

Every rule is enforced by the backend, verified against direct API calls rather
than UI behaviour.

| Requirement | How it is enforced |
|---|---|
| Student cannot call admin APIs | `require_admin` on all 12 admin endpoints; a STUDENT token gets 403 |
| Faculty cannot perform admin actions | Same guard; `require_staff` is separate and grants nothing extra |
| Unapproved user gets no access | `_assert_account_active` re-reads status from the DB on every request |
| Emergency access needs approval | No token exists until an admin approves |
| Temporary access is limited | `require_permanent_account` + expiry checked per request |
| Status changes are attributable | Audit entry written in the same transaction |

A structural test asserts that each admin endpoint actually declares
`require_admin` — without it, a behavioural test alone would still pass if an
endpoint forgot its guard, because the guard raises before the body runs.

**Not changed in this phase:** CORS is still `allow_origins=["*"]`, and there is
no rate limiting on login or on emergency-access submissions. Both should be
addressed before any real deployment.

---

## 8. Database changes

Additive only. No table dropped, recreated or reset; no row deleted.

### New columns on `users`

| Column | Purpose |
|---|---|
| `status_reason` | Why the last status change was made |
| `status_changed_at` | When |
| `status_changed_by_id` | Which admin did it |
| `is_emergency_access` | 1 = temporary emergency grant |
| `access_expires_at` | When a temporary grant lapses |

### New tables

`audit_logs` and `emergency_access_requests` — created by
`Base.metadata.create_all()`, which only ever creates *missing* tables.

### Migration

`run_migrations()` adds the columns; `backfill_users()` normalises
`is_emergency_access` to 0 on pre-existing rows so no established account is
ever mistaken for a temporary grant. Both are idempotent — restarting the server
repeatedly is safe.

---

## 9. API reference

### Admin — users

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/admin/users` | List with `?q=`, `?status=`, `?role=` |
| GET | `/api/admin/users/pending` | Review queue |
| GET | `/api/admin/users/{id}` | One account |
| POST | `/api/admin/users/{id}/approve` | Approve |
| POST | `/api/admin/users/{id}/reject` | Reject |
| POST | `/api/admin/users/{id}/suspend` | Suspend |
| POST | `/api/admin/users/{id}/reactivate` | Reactivate |
| GET | `/api/admin/audit-logs` | Audit trail |
| GET | `/api/admin/users/export/pdf` | Download `users.pdf` |

### Emergency access

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/api/emergency-access/request` | none | Submit (grants nothing) |
| GET | `/api/emergency-access/status/{code}?email=` | none | Check / collect |
| GET | `/api/emergency-access` | ADMIN | Review queue |
| POST | `/api/emergency-access/{id}/approve` | ADMIN | Grant, with duration |
| POST | `/api/emergency-access/{id}/reject` | ADMIN | Decline |

---

## 10. Notifications

The existing Phase 2 notification system is reused — **no second system was
created**. Phase 3B adds four event types to `app/notifications.py`, which write
to the same `notifications` table and appear in the same bell and
`/api/notifications` endpoint.

| Event | Who is told |
|---|---|
| New registration | ADMIN |
| Emergency access requested | ADMIN (as CRITICAL) |
| Account approved / rejected / suspended | The affected user |
| Emergency access decision | The granted account |

---

## 11. Testing

### Automated

```bash
cd backend
python3 tests/test_migration.py   # additive, idempotent, non-destructive
python3 tests/test_auth.py        # 41 Phase 3A cases (regression)
python3 tests/test_phase3b.py     # 49 Phase 3B cases
```

All run with plain `python3` and no installed dependencies — `tests/shim.py`
supplies the slice of FastAPI / Pydantic / SQLAlchemy the code under test uses,
so the **real** routers and guards are exercised without a running server.

Phase 3B coverage: registration → queue → approve / reject / suspend /
reactivate; the three admin safety rules; every admin endpoint guarded
(structurally and behaviourally); the full emergency-access lifecycle including
wrong-code, wrong-email, expiry, duration clamping, double review, and the
"never downgrade a real account" rule; all 12 audit event types with their five
required fields; PDF credential-leak testing; search and filtering; and Phase
1/2/3A regression.

### Manual checklist

| # | Test | Expected |
|---|---|---|
| 1 | Sign up as a student | PENDING; admin bell shows a new registration |
| 2 | Try to log in as that user | "pending administrator approval" |
| 3 | Admin → User Management | The account is in the queue |
| 4 | Approve it | User can now log in; they see an approval notification |
| 5 | Suspend it | Login blocked with the suspension message |
| 6 | Reactivate it | Login works again |
| 7 | Reject a different account | Login blocked with the rejection message |
| 8 | Search and filter the user list | Results narrow correctly |
| 9 | Export users.pdf | Downloads; contains no passwords |
| 10 | `/emergency-access` → submit | Reference code returned; admin notified |
| 11 | Check the reference before review | "awaiting review", no access |
| 12 | Reject it, then check again | "not approved", no access |
| 13 | Submit again, approve with 30 min | Checking returns a session |
| 14 | As that emergency user, open Campus Map | Blocked — temporary access banner shown |
| 15 | Report an emergency as them | Works |
| 16 | Admin → Audit Log | Every action above is listed |

### Direct API checks (not the UI)

```bash
# Student token calling an admin API -> 403
curl -H "Authorization: Bearer <STUDENT_TOKEN>" localhost:8000/api/admin/users

# Faculty token calling an admin API -> 403
curl -H "Authorization: Bearer <FACULTY_TOKEN>" localhost:8000/api/admin/users

# No token -> 401
curl localhost:8000/api/admin/users

# Submitting an emergency request returns no token
curl -X POST localhost:8000/api/emergency-access/request \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test","email":"t@x.com","reason":"testing this",
       "emergency_description":"Smoke in the lab right now"}'
```

### Regression

Confirm Phase 1/2/3A still work: reporting with AI classification, priority and
smart queue, team recommendation and assignment with override, incident
timeline, notifications, analytics, campus map, login/logout, signup, and
student-only visibility of their own incidents.

---

## 12. Next

**Phase 3C — Response Command.** Not started here, as instructed; neither is
Hybrid AI (3D).

Sequence: 3A → **3B** → 3C → 3D → 3E FINAL.
