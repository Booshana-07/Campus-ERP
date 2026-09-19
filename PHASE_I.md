# SENSORA — Phase I

## Team Assignment + Reassignment

This phase implements a reliable, team-based (not individual-worker) assignment
workflow on top of the existing platform:

```
REPORT → AI CLASSIFICATION → AI RISK/PRIORITY → TEAM RECOMMENDATION
       → ADMIN ASSIGNMENT → ADMIN REASSIGNMENT → ASSIGNMENT HISTORY
```

Everything here is additive. No table was dropped, no data reset, and
Phase 1, 2, 3A and 3B functionality is unchanged (verified — see §7).

---

## 1. What existed before this phase

The AI team recommender (`app/team_recommender.py`, Phase 2) and the
`PUT /api/incidents/{id}/assign-team` endpoint (admin-only, Phase 2) already
worked. What was missing:

- **No assignment history.** Assigning a second team to an incident silently
  overwrote `incidents.assigned_team_id` with no trace of who held it before.
- **A real bug.** Reassigning to a new team never freed the old one — the old
  team stayed `BUSY` forever, even though nothing was still using it.
- **No reassignment semantics.** The endpoint could not tell "first assignment"
  from "changing my mind later" — both looked identical to the database.

This phase fixes the bug and adds the missing history, without adding a
worker/department hierarchy, individual worker logins, or any new
infrastructure — per the explicit architecture decision to keep the response
unit at the TEAM level only.

---

## 2. Architecture decision (unchanged, reaffirmed)

There is still no:

- Response Worker / Response Head / Department Head login
- Individual worker profile, availability, or workload
- Worker-level authentication or leader hierarchy

The response unit is the **team itself** (`response_teams`, already existed:
Medical, Fire & Safety, Security, Electrical, Maintenance). ADMIN assigns and
reassigns teams; the AI only ever recommends — it never auto-assigns.

---

## 3. Data model

### New table: `incident_assignments`

One row per team "tenure" on an incident.

| Column | Meaning |
|---|---|
| `id` | Primary key |
| `incident_id` | Which incident |
| `team_id`, `team_name` | Which team (name denormalised so history reads correctly forever, matching the existing audit-log convention) |
| `assigned_by_id`, `assigned_by_name` | Which admin made this assignment |
| `is_override` | Did this differ from the AI recommendation at the time? |
| `reason` | Optional free-text reason (e.g. "Fire team unavailable") |
| `assigned_at` | When this tenure started |
| `is_active` | 1 = this is the incident's current team |
| `deactivated_at` | When this tenure ended (null while still active) |

Exactly one row per incident should have `is_active = 1` at any time (zero if
the incident has never been assigned).

`incidents.assigned_team_id` is **still the fast "current team" pointer** used
everywhere else in the app (dashboard, incident list, map, notifications) — it
is kept in sync with the active `incident_assignments` row. Nothing that reads
`assigned_team_id` needed to change.

### Migration

Because `incident_assignments` is a brand-new table, `Base.metadata.create_all()`
creates it automatically — no `ALTER TABLE` needed. A new backfill,
`backfill_assignment_history()` in `app/migrate.py`, gives any incident that
was already assigned a team *before* this phase exactly one active history
row, built from data the incident already carried (`assigned_at`,
`assigned_by_name`, `assignment_overridden`). It is a pure `INSERT`, runs only
for incidents with no existing history row, and is safe to run on every
startup (idempotent).

No existing table was altered, no row was deleted, and no incident lost data.

---

## 4. Team recommendation (unchanged)

Reused as-is from Phase 2 (`app/team_recommender.py`) — capability match →
availability → proximity, weighted higher for CRITICAL/high-risk incidents.
The AI recommendation is shown to the admin (`recommended_team_name`,
`recommendation_reason` on the incident) and is purely advisory: the AI never
calls `assign-team` itself.

---

## 5. Assignment / reassignment logic

`PUT /api/incidents/{id}/assign-team` (unchanged path/payload —
`{team_id, override_reason}`) now branches on whether the incident already has
an active team:

**First assignment** (no previous team):
- Same behaviour as Phase 2: creates the incident's `ASSIGNED` status
  transition, records whether this overrode the AI recommendation, logs
  `TEAM_ASSIGNED` in the audit trail, notifies as before.

**Reassignment** (a different team is requested and one is already active):
- The previous `incident_assignments` row is deactivated (`is_active = 0`,
  `deactivated_at` set) — **never deleted**.
- The outgoing team's availability flips back to `AVAILABLE` (the bug fix).
- A new active `incident_assignments` row is created for the new team.
- The incoming team's availability flips to `BUSY`.
- Logged as `TEAM_REASSIGNED` in the audit trail (old team → new team, reason).
- A `REASSIGNMENT` event is added to the incident's existing status-history
  timeline (the same timeline students/faculty/admin already see).
- A notification is sent (admin feed + the reporter, if any), reusing the
  existing Phase 2 notification system — no second notification system.

### Validation

| Case | Result |
|---|---|
| Incident does not exist | 404 |
| Team does not exist | 404 |
| Incident is `RESOLVED` | 400 — "Cannot assign a team to a resolved incident." |
| Team requested is already the active team | 400 — "\<team\> is already assigned to this incident." |
| Team requested is `BUSY` (on another incident) | 400 — "\<team\> is not currently available" |
| STUDENT calls this endpoint | 403 (`require_admin`) |
| FACULTY calls this endpoint | 403 (`require_admin`) |
| No token / expired token | 401 |

All of the above are enforced in the backend (`app/deps.py` → `require_admin`,
plus explicit checks in the endpoint) — never only by hiding a button.

---

## 6. API

Only one new endpoint was added, per the instruction not to create unnecessary
APIs — everything else reuses the existing Phase 2 endpoint and payload shape.

| Method | Path | Who | Purpose |
|---|---|---|---|
| `PUT` | `/api/incidents/{id}/assign-team` | ADMIN | Assign **or** reassign (existing endpoint, extended) |
| `GET` | `/api/incidents/{id}/assignment-history` | ADMIN | Full history for one incident, oldest first *(new)* |

`{team_id, override_reason}` is unchanged as the request body; `override_reason`
now doubles as the optional reassignment reason.

---

## 7. Audit log & notifications

**No second system was built.** Both reuse exactly what Phase 3B already has.

- `app/audit.py` → `audit.record()` — two new action names,
  `TEAM_ASSIGNED` and `TEAM_REASSIGNED`, added to the existing
  `models.AUDIT_ACTIONS` tuple (a documentation list only; nothing enforces
  against it, so this is purely additive). Each entry carries actor, the
  incident as the target, and a `details` string naming the old and new team
  plus the reason, if any.
- `app/notifications.py` → new `notify_reassignment()` function, calling the
  same `add_notification()` helper every other Phase 2/3B notification uses.
  Writes to the same `notifications` table, shown in the same bell and the
  same `/api/notifications` endpoint. Admin gets one notification; the
  reporter (if the incident has a linked user) gets a second, reporter-facing
  one.

---

## 8. Frontend

`IncidentDetail.jsx` (existing page, extended — not rebuilt):

- The team-selection button now reads **"Reassign"** instead of "Assign" once
  an incident already has a team, and the optional reason field is shown for
  any reassignment (not only when it differs from the AI recommendation).
- The "Accept & assign {AI recommendation}" button now hides itself once that
  team is already the active one (previously it stayed visible and clicking
  it would hit the new 400 "already assigned" guard).
- A new **Assignment History** panel (admin-only, matching the backend guard)
  lists every team that has held the incident, newest at the bottom, each row
  showing: team name, `CURRENT`/`REPLACED` badge, `OVERRIDE` badge where it
  applies, who assigned it, the reason (if given), and the time it started
  and — for replaced rows — the time it was replaced.

No other page was touched. No redesign, no new dashboards.

---

## 9. Testing

### Regression (existing suites, unmodified, all still pass)

```bash
cd backend
python3 tests/test_migration.py   # additive, idempotent, non-destructive
python3 tests/test_auth.py        # 41 cases
python3 tests/test_phase3b.py     # 49 cases
```

### New: `tests/test_phase_i.py` (15 cases)

Unlike the shim-based Phase 3A/3B suites, this one runs against a **real**
running instance (actual FastAPI + SQLAlchemy + SQLite) rather than the
in-memory shim. `app/routers/incidents.py` uses SQLAlchemy features the shim
doesn't model (relationship loading, `case()` for the priority queue, the
multi-table join in the migration backfill) — extending the shim to safely
cover that surface would have been a bigger, riskier change than the feature
itself. A live run also proves the whole stack works together: the new table,
the migration backfill, the audit log and the notification system, not just
each piece in isolation. It starts its own server on a scratch port, never
touches a real `campus_emergency.db` (moves any existing one aside and
restores it afterwards), and cleans up after itself.

```bash
cd backend
python3 tests/test_phase_i.py
```

Covers, in order: student cannot assign; faculty cannot assign; unauthenticated
cannot assign; invalid team rejected (404); admin can assign; assignment
persists (team flips to BUSY); re-assigning the identical team is rejected
(400); admin can reassign to a different team with a reason; reassignment
frees the old team and busies the new one; reassignment preserves both history
rows correctly flagged; assignment history is admin-only; audit log records
both `TEAM_ASSIGNED` and `TEAM_REASSIGNED` with correct detail; a notification
is created for the reassignment; a resolved incident cannot be (re)assigned;
and a regression check that incidents list, dashboard stats and `/auth/me`
still work.

**All 105 tests pass** (90 pre-existing + 15 new).

### Manual FIRE scenario (also exercised by the automated suite above)

1. Student reports "Fire alarm triggered, smoke visible near the Computer Lab"
   (FIRE / Computer Lab) → AI recommends Fire & Safety Team.
2. Admin assigns Fire & Safety Team → incident status becomes `ASSIGNED`, team
   goes `BUSY`.
3. Admin reassigns to Security Team with reason "Fire team unavailable" →
   Fire & Safety Team returns to `AVAILABLE`, Security Team goes `BUSY`.
4. Assignment History shows both rows: Fire & Safety (`REPLACED`), Security
   (`CURRENT`, `OVERRIDE`, reason attached).
5. Admin resolves the incident → further assignment attempts return 400.

---

## 10. Known limitations

- `override_reason` is one field doing double duty (AI-override reason *and*
  reassignment reason) rather than two separate parameters — kept this way
  deliberately to avoid changing the existing request schema for a Phase 2
  endpoint that other code already calls.
- The assignment-history endpoint is ADMIN-only per the spec; Faculty already
  see assignment/reassignment events through the existing incident timeline
  (`incident_status_history`), just not the dedicated history panel.
- No pagination on assignment history — fine at hackathon/demo scale (an
  incident is reassigned a handful of times at most), would need it for a
  long-lived production incident with dozens of reassignments.

---

## 11. Next

Per the strict stop condition for this phase: no full tracking dashboard, no
advanced analytics, no Hybrid AI, no Phase III work was started here.
