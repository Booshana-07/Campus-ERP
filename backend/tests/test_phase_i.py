"""
Phase I (Team Assignment + Reassignment) — acceptance tests.

Unlike test_auth.py / test_phase3b.py, this suite runs against a REAL running
instance of the app (real FastAPI + SQLAlchemy + SQLite) rather than the
in-memory shim. Reason: app/routers/incidents.py leans on SQLAlchemy features
the shim does not model (relationship loading, `case()` for the smart queue,
multi-table joins for the migration backfill), so a shim big enough to safely
exercise the real assignment/reassignment code path would be a bigger, riskier
change than the feature itself. A live run also proves the whole stack — the
new `incident_assignments` table, the migration backfill, the audit log and
the notification system — actually work together, not just in isolation.

Usage:
    cd backend
    python3 tests/test_phase_i.py

The script starts its own uvicorn instance on a scratch port against a
throwaway SQLite file, runs the checks, and tears the server down again. It
does not touch backend/campus_emergency.db.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}")
    except AssertionError as e:
        FAILED.append((name, str(e)))
        print(f"  FAIL  {name}  -> {e}")
    except Exception as e:
        FAILED.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERROR {name}  -> {type(e).__name__}: {e}")


def call(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def login(email, password="Campus@2025"):
    status, body = call("POST", "/api/auth/login", body={"email": email, "password": password})
    assert status == 200, f"login failed for {email}: {status} {body}"
    return body["access_token"]


def wait_for_server(proc, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server process exited before becoming ready")
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=1):
                return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("server did not become ready in time")


def main():
    scratch_dir = tempfile.mkdtemp(prefix="sensora_phase_i_")
    env = os.environ.copy()
    env["SENSORA_DB_DIR"] = scratch_dir  # harmless if unused by database.py
    scratch_db = os.path.join(scratch_dir, "campus_emergency.db")

    # database.py hard-codes its path next to backend/app, so run the server
    # with a copied/renamed backend dir is overkill — instead point it at a
    # scratch file via env var if database.py supports it; otherwise fall back
    # to running against the real backend dir but on a fresh DB file by
    # temporarily moving any existing dev DB aside and restoring it after.
    real_db = os.path.join(BACKEND_DIR, "campus_emergency.db")
    moved_aside = None
    if os.path.exists(real_db):
        moved_aside = real_db + ".phase_i_test_backup"
        shutil.move(real_db, moved_aside)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=BACKEND_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        wait_for_server(proc)

        admin = login("admin@campus.edu")
        student = login("student@campus.edu")
        faculty = login("faculty@campus.edu")

        status, teams = call("GET", "/api/teams", token=admin)
        assert status == 200
        fire_team = next(t for t in teams if "Fire" in t["name"])
        security_team = next(t for t in teams if "Security" in t["name"])
        medical_team = next(t for t in teams if "Medical" in t["name"])

        # ---- create a FIRE incident to assign/reassign ----
        status, incident = call("POST", "/api/incidents", token=student, body={
            "reporter_name": "Harish Kumar", "reporter_role": "STUDENT",
            "contact_number": "9876500000",
            "description": "Fire alarm triggered, smoke visible near the Computer Lab.",
            "category": "FIRE", "location": "Computer Lab",
        })
        assert status == 201, f"incident creation failed: {incident}"
        inc_id = incident["id"]

        def assign(token, team_id, reason=None):
            body = {"team_id": team_id}
            if reason:
                body["override_reason"] = reason
            return call("PUT", f"/api/incidents/{inc_id}/assign-team", token=token, body=body)

        # 1. Student cannot assign
        def t1():
            status, body = assign(student, fire_team["id"])
            assert status == 403, f"expected 403, got {status}: {body}"
        check("1. Student cannot assign a team", t1)

        # 2. Faculty cannot assign
        def t2():
            status, body = assign(faculty, fire_team["id"])
            assert status == 403, f"expected 403, got {status}: {body}"
        check("2. Faculty cannot assign a team", t2)

        # 3. Unauthenticated cannot assign
        def t3():
            status, body = assign(None, fire_team["id"])
            assert status == 401, f"expected 401, got {status}: {body}"
        check("3. Unauthenticated cannot assign a team", t3)

        # 4. Invalid team is rejected
        def t4():
            status, body = assign(admin, 999999)
            assert status == 404, f"expected 404, got {status}: {body}"
        check("4. Invalid team id is rejected (404)", t4)

        # 5. Admin can assign a team
        def t5():
            status, body = assign(admin, fire_team["id"])
            assert status == 200, f"expected 200, got {status}: {body}"
            assert body["assigned_team_name"] == fire_team["name"]
            assert body["status"] == "ASSIGNED"
        check("5. Admin can assign a team", t5)

        # 6. Assignment is actually stored (team now BUSY)
        def t6():
            status, teams_now = call("GET", "/api/teams", token=admin)
            team_now = next(t for t in teams_now if t["id"] == fire_team["id"])
            assert team_now["availability"] == "BUSY", "team should be BUSY after assignment"
        check("6. Assignment persists — team availability flips to BUSY", t6)

        # 7. Re-assigning the same team is rejected, not silently accepted
        def t7():
            status, body = assign(admin, fire_team["id"])
            assert status == 400, f"expected 400, got {status}: {body}"
        check("7. Re-assigning the identical team is rejected (400)", t7)

        # 8. Admin can reassign to a different team, with a reason
        def t8():
            status, body = assign(admin, security_team["id"], reason="Fire team unavailable")
            assert status == 200, f"expected 200, got {status}: {body}"
            assert body["assigned_team_name"] == security_team["name"]
        check("8. Admin can reassign to a different team", t8)

        # 9. Reassignment frees the OLD team (this was the Phase 1/2 bug)
        def t9():
            status, teams_now = call("GET", "/api/teams", token=admin)
            fire_now = next(t for t in teams_now if t["id"] == fire_team["id"])
            security_now = next(t for t in teams_now if t["id"] == security_team["id"])
            assert fire_now["availability"] == "AVAILABLE", "old team must be freed on reassignment"
            assert security_now["availability"] == "BUSY", "new team must become BUSY"
        check("9. Reassignment frees the old team and busies the new one", t9)

        # 10. Assignment history preserves BOTH rows, correctly ordered/flagged
        def t10():
            status, history = call("GET", f"/api/incidents/{inc_id}/assignment-history", token=admin)
            assert status == 200, f"expected 200, got {status}: {history}"
            assert len(history) == 2, f"expected 2 history rows, got {len(history)}"
            first, second = history
            assert first["team_name"] == fire_team["name"] and first["is_active"] is False
            assert first["deactivated_at"] is not None
            assert second["team_name"] == security_team["name"] and second["is_active"] is True
            assert second["reason"] == "Fire team unavailable"
            assert second["is_override"] is True
        check("10. Reassignment preserves previous assignment history", t10)

        # 11. Only ADMIN can view assignment history
        def t11():
            status, body = call("GET", f"/api/incidents/{inc_id}/assignment-history", token=student)
            assert status == 403, f"expected 403, got {status}: {body}"
            status, body = call("GET", f"/api/incidents/{inc_id}/assignment-history", token=None)
            assert status == 401, f"expected 401, got {status}: {body}"
        check("11. Assignment history is admin-only", t11)

        # 12. Audit log recorded both TEAM_ASSIGNED and TEAM_REASSIGNED
        def t12():
            status, body = call("GET", "/api/admin/audit-logs?action=TEAM_ASSIGNED", token=admin)
            assert status == 200 and body["total"] >= 1, f"missing TEAM_ASSIGNED entry: {body}"
            status, body = call("GET", "/api/admin/audit-logs?action=TEAM_REASSIGNED", token=admin)
            assert status == 200 and body["total"] >= 1, f"missing TEAM_REASSIGNED entry: {body}"
            entry = body["entries"][0]
            assert entry["target_id"] == inc_id
            assert "Fire" in entry["details"] and "Security" in entry["details"]
        check("12. Audit log records TEAM_ASSIGNED and TEAM_REASSIGNED", t12)

        # 13. A notification was created for the reassignment
        def t13():
            status, body = call("GET", "/api/notifications?limit=20", token=admin)
            assert status == 200
            titles = [n["title"] for n in body["notifications"]]
            assert "Incident reassigned" in titles, f"no reassignment notification found: {titles}"
        check("13. Notification created for the reassignment", t13)

        # 14. Cannot assign a team to a RESOLVED incident
        def t14():
            status, body = call("PUT", f"/api/incidents/{inc_id}/status", token=admin,
                                 body={"status": "RESOLVED"})
            assert status == 200, f"resolve failed: {body}"
            status, body = assign(admin, medical_team["id"])
            assert status == 400, f"expected 400 on resolved incident, got {status}: {body}"
        check("14. Cannot assign a team to a resolved incident", t14)

        # 15. Regression — Phase 1/2/3A/3B basics still work
        def t15():
            status, incidents_list = call("GET", "/api/incidents", token=admin)
            assert status == 200 and isinstance(incidents_list, list)
            status, stats = call("GET", "/api/dashboard/stats", token=admin)
            assert status == 200 and "total_incidents" in stats
            status, me = call("GET", "/api/auth/me", token=student)
            assert status == 200 and me["email"] == "student@campus.edu"
        check("15. Regression — existing Phase 1/2/3A/3B endpoints still work", t15)

    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        # Clean up the scratch DB created by this test run, and restore
        # whatever dev DB existed before (never destroy real data).
        if os.path.exists(real_db):
            os.remove(real_db)
        if moved_aside and os.path.exists(moved_aside):
            shutil.move(moved_aside, real_db)
        shutil.rmtree(scratch_dir, ignore_errors=True)

    print("\n" + "=" * 62)
    print(f"PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
    if FAILED:
        print("\nFAILED TESTS:")
        for name, reason in FAILED:
            print(f"  - {name}: {reason}")
        sys.exit(1)
    print("ALL PHASE I TESTS PASSED")


if __name__ == "__main__":
    main()
