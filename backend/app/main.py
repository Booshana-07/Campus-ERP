"""
Campus Emergency Response Platform — FastAPI backend entrypoint.

Run with:
    uvicorn app.main:app --reload --port 8000
(from inside the backend/ directory)
"""
import os
from dotenv import load_dotenv

load_dotenv()  # load GROQ_API_KEY etc. from backend/.env if present

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine, SessionLocal
from .routers import (
    admin_users,
    ai,
    auth,
    dashboard,
    emergency_access,
    incidents,
    notifications,
    teams,
)
from .seed import seed_if_empty
from .migrate import run_migrations, backfill_users, backfill_assignment_history
from .security import hashing_scheme_in_use

# Create all tables if they don't exist yet (this alone creates the new
# Phase I `incident_assignments` table — it's a brand-new table, not an
# altered one, so no ALTER TABLE is needed for it).
Base.metadata.create_all(bind=engine)

# Phase 2 + Phase 3A: add any new columns to tables that already existed.
# Purely additive — no data is dropped. Safe to run on every startup.
_added = run_migrations(engine)
if _added:
    print(f"[migrate] Added columns: {', '.join(_added)}")

# Phase 3A: give any pre-existing user rows a status and a password hash so
# accounts created in Phase 1/2 can still sign in. Only fills NULLs.
_backfilled = backfill_users(engine)
if any(_backfilled.values()):
    print(
        f"[migrate] Phase 3A backfill — status set on {_backfilled['status_set']} user(s), "
        f"password set on {_backfilled['passwords_set']} user(s). "
        f"See PHASE3A.md for the demo password."
    )

# Phase I: give already-assigned incidents a one-row assignment history so the
# new "Assignment History" view isn't empty for data that predates this phase.
_assignment_backfill = backfill_assignment_history(engine)
if _assignment_backfill["backfilled"]:
    print(f"[migrate] Phase I backfill — created assignment history for {_assignment_backfill['backfilled']} incident(s).")

print(f"[security] Password hashing scheme: {hashing_scheme_in_use()}")

# Seed demo data on first run
_db = SessionLocal()
try:
    seed_if_empty(_db)
finally:
    _db.close()

app = FastAPI(title="Campus Emergency Response Platform API", version="phase-I")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon simplicity — tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded incident images
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(incidents.router)
app.include_router(teams.router)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(notifications.router)
# Phase 3B
app.include_router(admin_users.router)
app.include_router(emergency_access.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Campus Emergency Response Platform API"}


@app.get("/api/health")
def health():
    return {"status": "healthy"}
