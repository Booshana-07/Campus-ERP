"""
Runs the REAL app/migrate.py against a database built to look exactly like a
Phase 2 install, and verifies nothing is lost.

sqlalchemy is not installable in this sandbox, so a thin shim provides the tiny
slice of its API that migrate.py actually uses (`text`, `engine.begin()`,
`conn.execute`, `.fetchall()`, `.first()`, `.rowcount`) on top of stdlib sqlite3.
The migration code itself is imported unmodified.
"""
import os
import sqlite3
import sys
import types

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Minimal SQLAlchemy shim
# ---------------------------------------------------------------------------
class _Text(str):
    pass


def text(sql):
    return _Text(sql)


class _Result:
    def __init__(self, cursor):
        self._rows = cursor.fetchall() if cursor.description else []
        self.rowcount = cursor.rowcount

    def fetchall(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=None):
        cur = self.raw.execute(str(sql), params or {})
        return _Result(cur)


class _Begin:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return _Conn(self.engine.raw)

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.engine.raw.rollback()
        else:
            self.engine.raw.commit()
        return False


class Engine:
    def __init__(self, path):
        self.raw = sqlite3.connect(path)

    def begin(self):
        return _Begin(self)


_sa = types.ModuleType("sqlalchemy")
_sa.text = text
sys.modules["sqlalchemy"] = _sa
sys.modules.setdefault("sqlalchemy.orm", types.ModuleType("sqlalchemy.orm"))

sys.path.insert(0, BACKEND)
from app.migrate import backfill_users, run_migrations  # noqa: E402
from app.security import verify_password  # noqa: E402


# ---------------------------------------------------------------------------
# Build a database that looks like a real Phase 2 install
# ---------------------------------------------------------------------------
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_phase2_sim.db")
if os.path.exists(DB):
    os.remove(DB)

db = sqlite3.connect(DB)
db.executescript(
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        email VARCHAR NOT NULL UNIQUE,
        role VARCHAR NOT NULL
    );
    CREATE TABLE incidents (
        id INTEGER PRIMARY KEY,
        reporter_name VARCHAR NOT NULL,
        reporter_role VARCHAR NOT NULL,
        contact_number VARCHAR NOT NULL,
        description TEXT NOT NULL,
        category VARCHAR NOT NULL,
        location VARCHAR NOT NULL,
        status VARCHAR NOT NULL DEFAULT 'REPORTED',
        risk_score INTEGER,
        reporter_user_id INTEGER,
        recommended_team_id INTEGER,
        recommendation_reason TEXT,
        action_plan TEXT,
        action_plan_source VARCHAR,
        assigned_by_name VARCHAR,
        assignment_overridden INTEGER DEFAULT 0,
        analyzed_at DATETIME,
        assigned_at DATETIME,
        responding_at DATETIME,
        created_at DATETIME
    );
    CREATE TABLE incident_status_history (
        id INTEGER PRIMARY KEY,
        incident_id INTEGER NOT NULL,
        status VARCHAR NOT NULL,
        note VARCHAR,
        timestamp DATETIME,
        actor_name VARCHAR,
        actor_role VARCHAR,
        event_type VARCHAR
    );
    CREATE TABLE notifications (
        id INTEGER PRIMARY KEY,
        title VARCHAR NOT NULL,
        message VARCHAR NOT NULL,
        kind VARCHAR NOT NULL,
        is_read INTEGER DEFAULT 0
    );
    CREATE TABLE response_teams (
        id INTEGER PRIMARY KEY,
        name VARCHAR NOT NULL,
        capability VARCHAR NOT NULL,
        members VARCHAR NOT NULL,
        availability VARCHAR NOT NULL,
        latitude FLOAT NOT NULL,
        longitude FLOAT NOT NULL
    );

    INSERT INTO users (id,name,email,role) VALUES
      (1,'Harish Kumar','student@campus.edu','STUDENT'),
      (2,'Priya Sharma','faculty@campus.edu','FACULTY'),
      (3,'Arjun Kumar','admin@campus.edu','ADMIN');

    INSERT INTO incidents (id,reporter_name,reporter_role,contact_number,description,
                           category,location,status,risk_score,reporter_user_id)
    VALUES
      (1,'Harish Kumar','STUDENT','9876543210','Student collapsed near cafeteria',
       'MEDICAL','Cafeteria','ANALYZED',88,1),
      (2,'Priya Sharma','FACULTY','9876501234','Smoke in electrical lab',
       'FIRE','Electrical Lab','RESOLVED',95,2);

    INSERT INTO incident_status_history (incident_id,status,note,actor_name,actor_role,event_type)
    VALUES (1,'REPORTED','Incident reported.','Harish Kumar','STUDENT','STATUS'),
           (2,'RESOLVED','Area declared safe.','Arjun Kumar','ADMIN','STATUS');

    INSERT INTO notifications (title,message,kind) VALUES ('CRITICAL','Check lab','CRITICAL');

    INSERT INTO response_teams (name,capability,members,availability,latitude,longitude)
    VALUES ('Medical Team','Medical / First Aid','Dr. Kavitha Rao','AVAILABLE',12.97,79.15);
    """
)
db.commit()

before = {
    t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in ("users", "incidents", "incident_status_history", "notifications", "response_teams")
}
incident_snapshot = db.execute(
    "SELECT id,description,status,risk_score,reporter_user_id FROM incidents ORDER BY id"
).fetchall()
db.close()

print("Phase 2 simulated DB row counts:", before)

# ---------------------------------------------------------------------------
# Run the real migration, twice (idempotency check)
# ---------------------------------------------------------------------------
engine = Engine(DB)
added_1 = run_migrations(engine)
fill_1 = backfill_users(engine)
added_2 = run_migrations(engine)
fill_2 = backfill_users(engine)

print("pass 1 added columns :", added_1)
print("pass 1 backfill      :", fill_1)
print("pass 2 added columns :", added_2, "(expected [])")
print("pass 2 backfill      :", fill_2, "(expected all zero)")

for expected in (
    # Phase 3A
    "users.password_hash", "users.status", "users.created_at",
    # Phase 3B
    "users.status_reason", "users.status_changed_at", "users.status_changed_by_id",
    "users.is_emergency_access", "users.access_expires_at",
):
    assert expected in added_1, f"{expected} was not added"
assert added_2 == [], "second run must add nothing"
assert all(v == 0 for v in fill_2.values()), "second backfill must be a no-op"

# ---------------------------------------------------------------------------
# Verify nothing was lost or altered
# ---------------------------------------------------------------------------
db = sqlite3.connect(DB)
after = {
    t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    for t in before
}
assert after == before, f"row counts changed! {before} -> {after}"
print("row counts preserved :", after)

assert (
    db.execute(
        "SELECT id,description,status,risk_score,reporter_user_id FROM incidents ORDER BY id"
    ).fetchall()
    == incident_snapshot
), "incident data was modified"
print("incident data unchanged: OK")

rows = db.execute("SELECT name,email,role,status,password_hash,created_at FROM users").fetchall()
for name, email, role, st, pw_hash, created in rows:
    assert st == "APPROVED", f"{email} should be APPROVED after backfill, got {st}"
    assert pw_hash, f"{email} has no password hash"
    assert created is not None, f"{email} has no created_at"
    assert verify_password("Campus@2025", pw_hash), f"{email} cannot log in with demo password"
    assert not verify_password("wrongpass", pw_hash)
    assert "Campus@2025" not in pw_hash, "plaintext leaked into the hash column"
    print(f"  {email:24} role={role:8} status={st:9} hash={pw_hash[:22]}...")

# ---------------------------------------------------------------------------
# Phase 3B: the new columns exist and are safely defaulted
# ---------------------------------------------------------------------------
cols = {r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()}
for expected in ("status_reason", "status_changed_at", "status_changed_by_id",
                 "is_emergency_access", "access_expires_at"):
    assert expected in cols, f"Phase 3B column {expected} missing"

for email, flag, expires in db.execute(
    "SELECT email, is_emergency_access, access_expires_at FROM users"
).fetchall():
    assert flag == 0, f"{email} was wrongly flagged as a temporary emergency account"
    assert expires is None, f"{email} was given an access expiry it should not have"
print("Phase 3B columns added and safely defaulted: OK")

print("\nALL MIGRATION TESTS PASSED")
db.close()
