# PHASE 2 — AI Optimization, Role-Based Access & Hackathon Polish

Phase 1 is untouched and still works exactly as before. Everything below was
added **on top of** it. Same stack (FastAPI + SQLAlchemy + SQLite, React + Vite +
Bootstrap), same demo logins, same Groq-or-fallback architecture, no new
infrastructure.

---

## 1. How to run

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

On startup the app now:
1. creates any missing tables,
2. runs a small **additive migration** that adds Phase 2 columns to tables that
   already exist (your Phase 1 data is kept),
3. seeds demo data only if the database is empty.

The Groq key stays backend-only, in `backend/.env` (copy from `.env.example`):

```
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant
```

Leave `GROQ_API_KEY` blank and everything still works — the deterministic
fallback handles both classification and the action plan.

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

### Demo logins

| Role    | Name         | Email                |
|---------|--------------|----------------------|
| STUDENT | Harish Kumar | student@campus.edu   |
| FACULTY | Priya Sharma | faculty@campus.edu   |
| ADMIN   | Arjun Kumar  | admin@campus.edu     |

---

## 2. What each role sees

| | STUDENT | FACULTY | ADMIN |
|---|---|---|---|
| Report an emergency | ✅ | ✅ | ✅ |
| My Incidents | ✅ | ✅ | — |
| Campus-wide incident queue | ❌ | ✅ (read-only) | ✅ |
| Open any incident | own only | ✅ | ✅ |
| Command dashboard | ❌ | ❌ | ✅ |
| Analytics | ❌ | ❌ | ✅ |
| Assign / override team | ❌ | ❌ | ✅ |
| Change status | ❌ | ❌ | ✅ |
| Response teams | ❌ | ✅ | ✅ |
| Campus map, notifications | ✅ | ✅ | ✅ |

**This is enforced in the backend, not just by hiding buttons.** The frontend
sends the signed-in user's email as an `X-User-Email` header on every request;
`app/deps.py` resolves the user and checks the role. Calling an admin API as a
student returns **403** even from curl or Postman.

---

## 3. Phase 2 features

1. **Role-based experience** — role-aware sidebar, routes and landing pages,
   backed by real API permission checks.
2. **AI response-team recommendation** — every analyzed incident gets a
   recommended team plus a one-sentence explanation, based on incident type,
   severity, risk score, priority, team capability, availability and distance
   from the incident location.
3. **Admin override** — the recommendation is advisory. The admin can accept it
   in one click or assign a different team (optionally with a reason). Both the
   AI choice and the human choice are stored and shown side by side, and the
   override is marked in the timeline and the incident list.
4. **Smart priority queue** — `smart_queue=true` orders incidents P1 → P4, then
   by risk score, then oldest first, with resolved incidents at the bottom. The
   Phase 1 filters and sort-by-risk still work unchanged.
5. **AI emergency action plan** — a 4–7 step plan per incident, from Groq when
   available and from a deterministic per-type plan otherwise.
6. **Real response-time tracking** — no hard-coded numbers. Time to assignment,
   time to response and total resolution time are computed from timestamp
   columns and status history. Where an incident never reached a stage, it
   contributes nothing, and with no data the UI shows "No data yet".
7. **In-app notification centre** — notification rows in the same SQLite
   database, a bell with an unread count, and a full notifications page. No
   Kafka, Redis, Firebase or paid services.
8. **Real-time feel via polling** — a small `usePolling` hook refreshes the
   dashboard, queues and notifications every 8–15 seconds, and pauses while the
   tab is hidden.
9. **Analytics** — category, severity, priority, status, active vs resolved,
   7-day trend and team workload, all from real rows.
10. **Activity timeline** — REPORTED → AI ANALYZED → TEAM RECOMMENDED →
    ASSIGNED → RESPONDING → RESOLVED, with timestamps, who did it, which team,
    and whether the AI was overridden.
11. **UI polish** — consistent P1–P4 / severity / status colours, coloured
    priority rails on table rows, cleaner cards, responsive layout.
12. **Demo mode** — seed data now includes two already-closed incidents so the
    metrics and analytics are populated the moment you start.

---

## 4. New API endpoints

| Method | Path | Who |
|---|---|---|
| `POST` | `/api/incidents/{id}/recommend-team` | ADMIN |
| `POST` | `/api/incidents/{id}/action-plan` | ADMIN |
| `GET` | `/api/dashboard/analytics` | ADMIN |
| `GET` | `/api/notifications` | any signed-in user |
| `PUT` | `/api/notifications/{id}/read` | any signed-in user |
| `PUT` | `/api/notifications/read-all` | any signed-in user |

Existing endpoints keep their paths and payloads. `GET /api/incidents` gains the
optional `smart_queue` and `mine` parameters; `PUT /api/incidents/{id}/assign-team`
accepts an optional `override_reason`.

---

## 5. Database changes

All additive — nothing was dropped or recreated.

**`incidents`** — `reporter_user_id`, `recommended_team_id`,
`recommendation_reason`, `action_plan`, `action_plan_source`, `assigned_by_name`,
`assignment_overridden`, `analyzed_at`, `assigned_at`, `responding_at`

**`incident_status_history`** — `actor_name`, `actor_role`, `event_type`

**`notifications`** (new table) — `id`, `incident_id`, `title`, `message`,
`kind`, `audience_role`, `target_user_id`, `is_read`, `created_at`

`app/migrate.py` adds any of these that are missing from an existing database on
startup, and is safe to run repeatedly.

---

## 6. Demo sequence

1. Log in as **Harish Kumar (STUDENT)** — lands on **My Incidents**.
2. Report: *"Smoke is coming from the electrical lab and students are still inside."*
3. Instantly: **FIRE / CRITICAL / risk 100 / P1**, with the AI-recommended
   **Fire & Safety Team** and a 7-step action plan.
4. Log out, log in as **Arjun Kumar (ADMIN)** — lands on the dashboard, which
   shows the new incident at the top of the smart priority queue, with a
   critical alert banner and a notification on the bell.
5. Open the incident. Point at the AI recommendation and its reasoning.
6. **Override**: assign the Security Team instead, with a reason. The card now
   shows AI recommended vs admin assigned, with an `ADMIN OVERRIDE` badge.
7. Move status to **RESPONDING**, then **RESOLVED**.
8. The assigned team returns to AVAILABLE, dashboard counters and response-time
   metrics update, notifications appear, and the activity timeline shows the
   full history with timestamps and actors.
9. Log back in as the student to show they see status updates on their own
   incident — and that the dashboard and analytics are blocked for their role.

---

## 7. Known limitations

- Login is still demo-only (email, no password) and identity travels in a plain
  header. That is fine for a hackathon demo but is not production auth — real
  deployments need sessions or JWTs over HTTPS.
- Notification read state is per-notification rather than per-user, so if two
  admins are signed in at once, one marking a notification read marks it read
  for both.
- The team recommender is deterministic scoring rather than an LLM call, so the
  reasoning is explainable and never fails mid-demo. The AI inputs it uses
  (type, severity, risk score) still come from the classifier.
- Polling means updates arrive within about 10 seconds rather than instantly.
- Distances use a flat-earth approximation, which is accurate enough across a
  single campus.
- The Groq action plan adds a call only for HIGH/CRITICAL or risk ≥ 60
  incidents, so minor reports stay fast.
