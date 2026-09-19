# 🎓 AI-Powered Campus Emergency Response Platform

An end-to-end emergency management platform for a college campus that turns:

> Report → manually analyze → manually prioritize → manually assign

into:

> Report → **AI Classify** → **AI Risk Score** → Prioritize → Recommend Action → Assign Team → Track → Resolve

**Phase 1** is the working MVP described below. **Phase 2** (role-based access,
AI team recommendation with admin override, smart priority queue, AI action
plans, real response-time metrics, notifications, analytics) has now been built
on top of it — see **[PHASE2.md](PHASE2.md)** for what was added, how to run it,
and the demo sequence.

**Phase 3A** replaces the demo login with real email + password authentication:
hashed passwords, a Student/Faculty signup flow, account statuses
(PENDING / APPROVED / REJECTED / SUSPENDED), and signed session tokens verified
by the backend on every request — see **[PHASE3A.md](PHASE3A.md)**.

**Phase 3B** completes the access-control layer: an admin console for approving,
rejecting, suspending and reactivating accounts; a controlled emergency-access
route for people without an approved account; an append-only audit log; and a
`users.pdf` export — see **[PHASE3B.md](PHASE3B.md)**.

---

## 1. Problem Statement

Campus emergencies (medical, fire, security, electrical, accidents) are currently
reported and handled manually — someone has to read the report, decide how serious
it is, and call the right team. That takes time, and time is the one thing you
don't have in an emergency. This platform automates the triage step: the moment
an emergency is reported, AI (or a reliable local fallback) instantly classifies
it, scores its risk, assigns a priority, and recommends an action — so admins can
spend their time responding, not reading.

---

## 2. Features Implemented (Phase 1)

- **Demo login** for three roles: STUDENT, FACULTY, ADMIN *(superseded in Phase 3A by real email + password authentication — see [PHASE3A.md](PHASE3A.md))*
- **Emergency reporting form** with category, campus location, contact info, optional photo
- **AI incident classification** (type, severity, risk score 0-100, priority, reasoning, recommended action)
- **Deterministic local fallback classifier** — the app works fully even with no API key or if the AI call fails
- **Admin command dashboard** — live stats, charts (category bar chart, severity pie chart), top-risk incident table
- **Incident list** with filtering (type/severity/status/priority) and sort-by-risk
- **Incident detail page** with a visual REPORTED → ANALYZED → ASSIGNED → RESPONDING → RESOLVED timeline and full status history
- **Manual status updates** and **manual team assignment**, persisted to the database
- **Campus map** (Leaflet + OpenStreetMap, no paid Maps API) showing incidents and response teams as markers
- **Response teams** management (5 seeded teams, availability tracking)
- **Realistic Indian-college seed data** (users, teams, incidents)
- Full error handling: form validation, loading states, empty states, API error handling, AI-failure fallback

---

## 3. Architecture

```
Browser (React SPA)
   │  Axios (REST/JSON)
   ▼
FastAPI backend  ──►  Groq API (if GROQ_API_KEY set)
   │                       │
   │                  (on failure/missing key)
   │                       ▼
   │                Local rule-based fallback classifier
   ▼
SQLite database (SQLAlchemy ORM)
```

No Docker, no microservices, no message queues — a single Python process and a
single Node dev server, both runnable on a normal Windows/Mac/Linux laptop.

---

## 4. Technology Stack

**Frontend:** React 18, Vite, JavaScript, Bootstrap 5, Axios, React Router 6, Recharts, React-Leaflet + Leaflet (OpenStreetMap tiles)

**Backend:** Python, FastAPI, Uvicorn

**Database:** SQLite via SQLAlchemy ORM (zero setup — a `.db` file is created automatically)

**AI:** Groq API (free tier, OpenAI-compatible endpoint) when `GROQ_API_KEY` is set, using model `llama-3.1-8b-instant` by default — otherwise a deterministic keyword/rule-based fallback classifier

---

## 5. Folder Structure

```
campus-emergency-platform/
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app entrypoint
│   │   ├── database.py            # SQLAlchemy engine/session
│   │   ├── models.py              # users, incidents, response_teams, incident_status_history
│   │   ├── schemas.py             # Pydantic request/response models
│   │   ├── ai_classifier.py       # Groq call + validation + deterministic fallback
│   │   ├── seed.py                # Demo data seeding
│   │   ├── uploads/                # incident photo uploads (created at runtime)
│   │   └── routers/
│   │       ├── auth.py
│   │       ├── incidents.py
│   │       ├── teams.py
│   │       ├── dashboard.py
│   │       └── ai.py
│   ├── requirements.txt
│   ├── .env.example
│   └── campus_emergency.db        # created automatically on first run
├── frontend/
│   ├── src/
│   │   ├── main.jsx / App.jsx
│   │   ├── pages/                 # Login, Dashboard, Report, Incidents, IncidentDetail, Teams, CampusMap
│   │   ├── components/            # Sidebar, Layout, ProtectedRoute, Badges
│   │   ├── context/AuthContext.jsx
│   │   └── api/client.js          # Axios wrapper for every backend endpoint
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
└── README.md
```

---

## 6. Environment Variables

**backend/.env** (copy from `backend/.env.example`):
```
GROQ_API_KEY=            # optional — leave blank to always use the fallback classifier
GROQ_MODEL=llama-3.1-8b-instant
```

**frontend/.env** (copy from `frontend/.env.example`):
```
VITE_API_BASE_URL=http://localhost:8000
```

If you don't create these files, the app still runs — `GROQ_API_KEY` blank means
"always use fallback", and the frontend defaults to `http://localhost:8000`.

---

## 7. Installation

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend
```bash
cd campus-emergency-platform/backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env       # Windows — or: cp .env.example .env
```

### Frontend
```bash
cd campus-emergency-platform/frontend
npm install
copy .env.example .env       # Windows — or: cp .env.example .env
```

---

## 8. Running the Application

### Start the backend (Terminal 1)
```bash
cd campus-emergency-platform/backend
uvicorn app.main:app --reload --port 8000
```
This automatically creates `campus_emergency.db`, creates all tables, and loads
demo seed data on first run. API docs available at `http://localhost:8000/docs`.

**Phase 3A/3B note:** `pip install -r requirements.txt` now also installs
`bcrypt`, `PyJWT` and `reportlab` (the last powers the `users.pdf` export). Both are optional at runtime (the app falls back to standard-library
equivalents), but bcrypt is the stronger password hash and is recommended. The
startup log prints which scheme is active. Existing databases are migrated
automatically and additively — no data is lost.

### Start the frontend (Terminal 2)
```bash
cd campus-emergency-platform/frontend
npm run dev
```
App available at `http://localhost:5173`.

### Database setup
No manual steps needed — SQLite is a file-based database and SQLAlchemy creates
the schema and seed data automatically on the first backend start. To reset,
just delete `backend/campus_emergency.db` and restart the backend.

---

## 9. Demo Accounts

| Role    | Name          | Email               |
|---------|---------------|----------------------|
| STUDENT | Harish Kumar  | student@campus.edu  |
| FACULTY | Priya Sharma  | faculty@campus.edu  |
| ADMIN   | Arjun Kumar   | admin@campus.edu    |

**Since Phase 3A these accounts require a password.** It is whatever
`DEMO_USER_PASSWORD` is set to in `backend/.env` (default `Campus@2025`).
The one-click demo login buttons were removed — they exposed working credentials
in the UI and in the page source.

New Student and Faculty accounts can be created at `/signup`. They start as
PENDING and need administrator approval before they can sign in. **Since Phase
3B** an admin approves them at **User Management** (`/admin/users`) — no more
editing SQLite by hand.

People with no approved account who need to report a live emergency can use
**Emergency Access** from the login page. That is a request for admin review,
not a bypass — see [PHASE3B.md](PHASE3B.md) section 4.

---

## 10. API Endpoints

| Method | Endpoint                              | Description                          |
|--------|----------------------------------------|---------------------------------------|
| POST   | `/api/auth/signup`                    | Register as STUDENT or FACULTY (Phase 3A) |
| POST   | `/api/auth/login`                     | Login with email + password → session token |
| GET    | `/api/auth/me`                        | The signed-in user (Phase 3A)         |
| POST   | `/api/auth/logout`                    | End the session (Phase 3A)            |
| GET    | `/api/admin/users`                    | List/search users (Phase 3B, ADMIN)   |
| GET    | `/api/admin/users/pending`            | Registration review queue (ADMIN)     |
| POST   | `/api/admin/users/{id}/approve`       | Approve an account (ADMIN)            |
| POST   | `/api/admin/users/{id}/reject`        | Reject an account (ADMIN)             |
| POST   | `/api/admin/users/{id}/suspend`       | Suspend an account (ADMIN)            |
| POST   | `/api/admin/users/{id}/reactivate`    | Reactivate an account (ADMIN)         |
| GET    | `/api/admin/audit-logs`               | Audit trail (ADMIN)                   |
| GET    | `/api/admin/users/export/pdf`         | Download `users.pdf` (ADMIN)          |
| POST   | `/api/emergency-access/request`       | Request emergency access (public)     |
| GET    | `/api/emergency-access/status/{code}` | Check/collect a decision (public)     |
| GET    | `/api/emergency-access`               | Emergency request queue (ADMIN)       |
| POST   | `/api/emergency-access/{id}/approve`  | Grant temporary access (ADMIN)        |
| POST   | `/api/emergency-access/{id}/reject`   | Decline the request (ADMIN)           |
| POST   | `/api/incidents`                      | Report an emergency (runs AI/fallback classification) |
| GET    | `/api/incidents`                      | List incidents (filter/sort query params) |
| GET    | `/api/incidents/{id}`                 | Get incident details + status history |
| PUT    | `/api/incidents/{id}/status`          | Update incident status                |
| PUT    | `/api/incidents/{id}/assign-team`     | Assign a response team                |
| POST   | `/api/incidents/upload-image`         | Upload an optional incident photo     |
| GET    | `/api/teams`                          | List response teams                   |
| GET    | `/api/dashboard/stats`                | Dashboard summary stats               |
| POST   | `/api/ai/analyze`                     | Standalone AI/fallback classification preview |

`GET /api/incidents` query params: `status`, `severity`, `incident_type`, `priority`, `sort_by_risk=true`.

---

## 11. AI Configuration & Fallback Behavior

- If `GROQ_API_KEY` is set in `backend/.env`, every new incident is sent to the
  Groq API (`llama-3.1-8b-instant` by default) for classification.
- The AI's JSON response is **strictly validated** — invalid `incidentType`,
  `severity`, or `priority` values are corrected to safe defaults, and `riskScore`
  is clamped to 0–100. Malformed AI output can never crash the app.
- If `GROQ_API_KEY` is missing, or the Groq call fails/times out/returns bad JSON,
  the app **automatically and silently** falls back to a local deterministic
  keyword/rule-based classifier (see `backend/app/ai_classifier.py`).
- Every incident's analysis is labeled either **"AI Analysis"** or
  **"Fallback Analysis"** so it's always clear which path was used — visible on
  the incident detail page.

---

## 12. Hackathon Demo Flow

1. **Login** as Admin (`admin@campus.edu`) to see the command dashboard.
   *(Since Phase 3A this needs the password from `DEMO_USER_PASSWORD`.)*
2. Open a new tab/incognito and **login as Student** (`student@campus.edu`).
3. Go to **Report Emergency**, submit:
   > "Smoke is coming from the electrical lab and students are still inside."
   Category: FIRE, Location: Electrical Lab.
4. Watch it get classified instantly (FIRE / CRITICAL / ~90+ risk / P1) and see
   the recommended action.
5. Switch back to the **Admin** tab, refresh the **Dashboard** — the critical
   incident banner appears immediately.
6. Go to **Incidents**, click the new incident, and walk through the **timeline**.
7. As Admin, **assign the Fire & Safety Team** and progress the status through
   RESPONDING → RESOLVED — show the persisted status history.
8. Open the **Campus Map** to show the incident and team markers.
9. Show the **Teams** page — the assigned team is now marked BUSY, and becomes
   AVAILABLE again once the incident is resolved.

---

## 13. What Was Implemented (Phase 1 Scope)

Everything in the Phase 1 spec: demo auth for 3 roles, emergency reporting with
image upload, AI classification with strict validation, deterministic fallback
classifier, admin dashboard with charts and stats, incident detail with timeline,
manual status management persisted to DB, campus map with Leaflet, response teams
with manual assignment, full REST API, SQLite schema (`users`, `incidents`,
`response_teams`, `incident_status_history`), seed data, and complete error
handling (validation, loading/empty states, API + AI + DB failure handling).

**Not implemented (intentionally, reserved for Phase 2):** AI-driven optimal team
recommendation/auto-assignment, production authentication (passwords/JWT/OAuth),
real-time push notifications, and live GPS navigation.

*Update: the team recommendation landed in Phase 2, password-based
authentication with signed tokens landed in Phase 3A, user approval,
emergency access and auditing landed in Phase 3B, and team assignment +
reassignment (with full history) landed in Phase I — see `PHASE_I.md`.*

---

## 14. Verification Checklist (all confirmed working before delivery)

1. ✅ Backend starts successfully (`uvicorn app.main:app`)
2. ✅ Frontend starts successfully (`npm run dev`, Vite ready, all modules transform with HTTP 200)
3. ✅ Database initializes automatically (SQLite file + tables created)
4. ✅ Demo data loads (3 users, 5 teams, 5 incidents) on first run
5. ✅ Emergency can be submitted via `POST /api/incidents`
6. ✅ Incident is saved and retrievable
7. ✅ AI analysis works when `GROQ_API_KEY` is configured
8. ✅ Fallback AI works with no API key (tested: correctly returns FIRE/CRITICAL/P1/~90+ for the smoke-in-electrical-lab example)
9. ✅ Dashboard stats endpoint returns correct totals
10. ✅ Incident details endpoint returns full history
11. ✅ Status can be changed and is persisted (`REPORTED → ANALYZED → ASSIGNED → RESPONDING → RESOLVED` tested end-to-end)
12. ✅ Team can be assigned, becomes unavailable, and frees up again on resolution
13. ✅ Map data available (incidents + teams with coordinates); Leaflet/OSM renders client-side
14. ✅ Frontend build (`npm run build`) completes with 0 errors
15. ✅ Backend log shows no errors across the full tested request flow
