"""
Phase 2 — tiny, additive SQLite migration.

Why this exists: Phase 1 may already have created `campus_emergency.db` on your
machine with real demo data in it. SQLAlchemy's `create_all()` creates *missing
tables* but never adds *missing columns* to a table that already exists. So this
module simply looks at each table and runs `ALTER TABLE ... ADD COLUMN` for any
Phase 2 column that isn't there yet.

It never drops, renames, or recreates anything — existing rows and data are kept.
Running it twice is safe (it checks first).
"""
import datetime
import os

from sqlalchemy import text

# table -> [(column_name, SQL column definition), ...]
NEW_COLUMNS = {
    "incidents": [
        ("reporter_user_id", "INTEGER"),
        ("recommended_team_id", "INTEGER"),
        ("recommendation_reason", "TEXT"),
        ("action_plan", "TEXT"),
        ("action_plan_source", "VARCHAR"),
        ("assigned_by_name", "VARCHAR"),
        ("assignment_overridden", "INTEGER DEFAULT 0"),
        ("analyzed_at", "DATETIME"),
        ("assigned_at", "DATETIME"),
        ("responding_at", "DATETIME"),
    ],
    "incident_status_history": [
        ("actor_name", "VARCHAR"),
        ("actor_role", "VARCHAR"),
        ("event_type", "VARCHAR"),
    ],
    # ----- Phase 3A: real authentication -----
    # Note the deliberate absence of NOT NULL here. SQLite cannot add a NOT NULL
    # column to a table that already has rows without a default, and forcing one
    # would mean rebuilding the table — which would risk existing data. The
    # columns are added as nullable and then backfilled by backfill_users()
    # below, which is the safe, purely additive route.
    "users": [
        ("password_hash", "VARCHAR"),
        ("status", "VARCHAR"),
        ("created_at", "DATETIME"),
        # ----- Phase 3B -----
        ("status_reason", "TEXT"),
        ("status_changed_at", "DATETIME"),
        ("status_changed_by_id", "INTEGER"),
        ("is_emergency_access", "INTEGER DEFAULT 0"),
        ("access_expires_at", "DATETIME"),
    ],
}


def _existing_columns(conn, table_name: str) -> set:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {r[1] for r in rows}


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": table_name},
    ).first()
    return row is not None


def run_migrations(engine) -> list:
    """Add any missing Phase 2 / Phase 3A columns. Returns a list of what was added."""
    added = []
    with engine.begin() as conn:
        for table, columns in NEW_COLUMNS.items():
            if not _table_exists(conn, table):
                continue  # create_all() will build it fresh with every column
            present = _existing_columns(conn, table)
            for col_name, col_def in columns:
                if col_name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))
                    added.append(f"{table}.{col_name}")
    return added


# ---------------------------------------------------------------------------
# Phase 3A backfill
# ---------------------------------------------------------------------------
def backfill_users(engine) -> dict:
    """
    Give pre-Phase-3A user rows everything they need to log in under the new
    password system. Purely an UPDATE of NULL columns — no row is deleted,
    no table is rebuilt, and nothing that already has a value is touched.

      * status       -> APPROVED for accounts that existed before Phase 3A.
                        They were already trusted under Phase 1/Phase 2, so
                        locking them out as PENDING would break a working system.
                        Brand-new signups still start PENDING (handled in the
                        auth router, not here).
      * created_at   -> now, where unknown.
      * password_hash-> a hash of DEMO_USER_PASSWORD, so the existing demo
                        accounts remain usable after the upgrade. Only ever
                        applied where password_hash IS NULL.

    Running this repeatedly is safe: after the first pass there is nothing left
    that is NULL, so it becomes a no-op.
    """
    from .security import hash_password

    demo_password = os.getenv("DEMO_USER_PASSWORD", "Campus@2025").strip() or "Campus@2025"

    result = {"status_set": 0, "created_at_set": 0, "passwords_set": 0, "emergency_flag_set": 0}

    with engine.begin() as conn:
        if not _table_exists(conn, "users"):
            return result

        present = _existing_columns(conn, "users")
        if not {"password_hash", "status", "created_at"}.issubset(present):
            return result  # columns not there yet; run_migrations() handles that

        res = conn.execute(
            text("UPDATE users SET status = 'APPROVED' WHERE status IS NULL OR status = ''")
        )
        result["status_set"] = res.rowcount or 0

        res = conn.execute(
            text("UPDATE users SET created_at = :now WHERE created_at IS NULL"),
            {"now": datetime.datetime.utcnow()},
        )
        result["created_at_set"] = res.rowcount or 0

        # Hash once, then apply to each password-less account individually.
        rows = conn.execute(
            text("SELECT id FROM users WHERE password_hash IS NULL OR password_hash = ''")
        ).fetchall()
        for row in rows:
            conn.execute(
                text("UPDATE users SET password_hash = :h WHERE id = :i"),
                {"h": hash_password(demo_password), "i": row[0]},
            )
        result["passwords_set"] = len(rows)

        # ----- Phase 3B -----
        # `is_emergency_access` is NOT NULL in the model but arrives as NULL on
        # rows that predate the column. Normalise it to 0 (a normal account) so
        # nothing is ever mistaken for a temporary emergency grant.
        if "is_emergency_access" in present:
            res = conn.execute(
                text("UPDATE users SET is_emergency_access = 0 WHERE is_emergency_access IS NULL")
            )
            result["emergency_flag_set"] = res.rowcount or 0

    return result


# ---------------------------------------------------------------------------
# Phase I backfill — assignment history
# ---------------------------------------------------------------------------
def backfill_assignment_history(engine) -> dict:
    """
    `incident_assignments` is a brand-new table (Phase I), so create_all()
    creates it empty. Any incident that was already assigned a team *before*
    this phase would otherwise show no history at all. This backfill creates
    exactly one active history row per already-assigned incident, using the
    data that incident already carries (assigned_at, assigned_by_name,
    assignment_overridden) — no guessing, no fabricated data, and it is a
    pure INSERT: no existing row in any table is touched.

    Idempotent: only incidents with assigned_team_id set AND no existing
    `incident_assignments` row are backfilled, so running this on every
    startup is safe.
    """
    result = {"backfilled": 0}
    with engine.begin() as conn:
        if not _table_exists(conn, "incident_assignments") or not _table_exists(conn, "incidents"):
            return result

        rows = conn.execute(text(
            """
            SELECT i.id, i.assigned_team_id, t.name, i.assigned_by_name,
                   i.assignment_overridden, i.assigned_at, i.created_at
            FROM incidents i
            JOIN response_teams t ON t.id = i.assigned_team_id
            WHERE i.assigned_team_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM incident_assignments a WHERE a.incident_id = i.id
              )
            """
        )).fetchall()

        for inc_id, team_id, team_name, assigned_by_name, overridden, assigned_at, created_at in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO incident_assignments
                        (incident_id, team_id, team_name, assigned_by_id, assigned_by_name,
                         is_override, reason, assigned_at, is_active, deactivated_at)
                    VALUES
                        (:incident_id, :team_id, :team_name, NULL, :assigned_by_name,
                         :is_override, NULL, :assigned_at, 1, NULL)
                    """
                ),
                {
                    "incident_id": inc_id,
                    "team_id": team_id,
                    "team_name": team_name,
                    "assigned_by_name": assigned_by_name or "System",
                    "is_override": overridden or 0,
                    "assigned_at": assigned_at or created_at or datetime.datetime.utcnow(),
                },
            )
            result["backfilled"] += 1

    return result
