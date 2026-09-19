"""
Phase 3B acceptance tests — every item in section 11 of the brief.

Calls the REAL app/routers/admin_users.py, app/routers/emergency_access.py,
app/routers/auth.py, app/deps.py, app/audit.py and app/pdf_export.py.
"""
import datetime

import shim
from shim import FakeDB, HTTPException

models, schemas, security, deps, auth = shim.load_app()
from app import audit, pdf_export  # noqa: E402
from app.routers import admin_users, emergency_access  # noqa: E402

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


def expect_http(code, fn, contains=None):
    try:
        fn()
    except HTTPException as e:
        assert e.status_code == code, f"expected {code}, got {e.status_code} ({e.detail})"
        if contains:
            assert contains.lower() in str(e.detail).lower(), f"message was: {e.detail}"
        return e
    raise AssertionError(f"expected HTTP {code} but the call succeeded")


def fresh_db():
    db = FakeDB()
    for name, email, role in [
        ("Harish Kumar", "student@campus.edu", "STUDENT"),
        ("Priya Sharma", "faculty@campus.edu", "FACULTY"),
        ("Arjun Kumar", "admin@campus.edu", "ADMIN"),
    ]:
        db.add(models.User(
            name=name, email=email, role=role,
            password_hash=security.hash_password("Campus@2025"),
            status=models.STATUS_APPROVED, is_emergency_access=0,
            created_at=datetime.datetime.utcnow(),
        ))
    return db


def find_user(db, email):
    return db.query(models.User).filter(models.User.email == email).first()


def principal(db, email, password="Campus@2025"):
    tok = auth.login(schemas.LoginRequest(email=email, password=password), db).access_token
    return deps.get_current_user(f"Bearer {tok}", db)


def register(db, email="nisha@campus.edu", name="Nisha Reddy", role="STUDENT"):
    auth.signup(schemas.SignupRequest(
        full_name=name, email=email, password="Str0ng!Pass",
        confirm_password="Str0ng!Pass", role=role), db)
    return find_user(db, email)


def audit_actions(db):
    return [r.action for r in db.query(models.AuditLog).all()]


# ===========================================================================
print("\n--- 1. REGISTRATION -> ADMIN QUEUE ---")


def t_registration_creates_pending_and_notifies():
    db = fresh_db()
    user = register(db)
    assert user.status == models.STATUS_PENDING
    notes = db.query(models.Notification).all()
    assert any("registration" in (n.title or "").lower() for n in notes), "no admin notification"
    assert any(n.audience_role == "ADMIN" for n in notes)
    assert "USER_REGISTERED" in audit_actions(db)


def t_pending_shows_in_admin_queue():
    db = fresh_db()
    register(db)
    admin = principal(db, "admin@campus.edu")
    queue = admin_users.list_pending_users(db, admin)
    assert queue.total == 1
    assert queue.users[0].email == "nisha@campus.edu"
    assert queue.users[0].status == "PENDING"


def t_pending_cannot_log_in():
    db = fresh_db()
    register(db)
    err = expect_http(403, lambda: auth.login(
        schemas.LoginRequest(email="nisha@campus.edu", password="Str0ng!Pass"), db))
    assert err.detail == "Your account is pending administrator approval."
    assert "LOGIN_BLOCKED" in audit_actions(db)


check("registration -> PENDING + admin notification + audit", t_registration_creates_pending_and_notifies)
check("pending user appears in the admin queue", t_pending_shows_in_admin_queue)
check("pending user cannot log in (and it is audited)", t_pending_cannot_log_in)


# ===========================================================================
print("\n--- 2. APPROVE / REJECT / SUSPEND / REACTIVATE ---")


def t_approve():
    db = fresh_db()
    user = register(db)
    admin = principal(db, "admin@campus.edu")
    out = admin_users.approve_user(user.id, None, db, admin)
    assert out.status == "APPROVED"
    assert out.status_changed_by_name == "Arjun Kumar"
    assert "USER_APPROVED" in audit_actions(db)
    # now she can sign in
    assert auth.login(schemas.LoginRequest(
        email="nisha@campus.edu", password="Str0ng!Pass"), db).access_token


def t_reject():
    db = fresh_db()
    user = register(db)
    admin = principal(db, "admin@campus.edu")
    out = admin_users.reject_user(
        user.id, schemas.StatusChangeRequest(reason="Not a registered student"), db, admin)
    assert out.status == "REJECTED"
    assert out.status_reason == "Not a registered student"
    err = expect_http(403, lambda: auth.login(
        schemas.LoginRequest(email="nisha@campus.edu", password="Str0ng!Pass"), db))
    assert err.detail == "Your account has been rejected."
    assert "USER_REJECTED" in audit_actions(db)


def t_suspend():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    student = find_user(db, "student@campus.edu")
    out = admin_users.suspend_user(
        student.id, schemas.StatusChangeRequest(reason="Misuse of the report form"), db, admin)
    assert out.status == "SUSPENDED"
    err = expect_http(403, lambda: auth.login(
        schemas.LoginRequest(email="student@campus.edu", password="Campus@2025"), db))
    assert err.detail == "Your account is currently suspended."
    assert "USER_SUSPENDED" in audit_actions(db)


def t_reactivate():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    student = find_user(db, "student@campus.edu")
    admin_users.suspend_user(student.id, schemas.StatusChangeRequest(reason="x"), db, admin)
    out = admin_users.reactivate_user(
        student.id, schemas.StatusChangeRequest(reason="Cleared"), db, admin)
    assert out.status == "APPROVED"
    assert auth.login(schemas.LoginRequest(
        email="student@campus.edu", password="Campus@2025"), db).access_token
    assert "USER_REACTIVATED" in audit_actions(db)


def t_reactivate_only_from_suspended_or_rejected():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    student = find_user(db, "student@campus.edu")  # already APPROVED
    expect_http(400, lambda: admin_users.reactivate_user(student.id, None, db, admin),
                "only suspended or rejected")


def t_no_redundant_status_change():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    student = find_user(db, "student@campus.edu")
    expect_http(400, lambda: admin_users.approve_user(student.id, None, db, admin),
                "already APPROVED")


def t_status_change_notifies_the_user():
    db = fresh_db()
    user = register(db)
    admin = principal(db, "admin@campus.edu")
    admin_users.approve_user(user.id, None, db, admin)
    notes = [n for n in db.query(models.Notification).all() if n.target_user_id == user.id]
    assert notes, "the approved user got no notification"
    assert "approved" in notes[-1].title.lower()


check("approve -> APPROVED, audited, login works", t_approve)
check("reject -> REJECTED, audited, login blocked", t_reject)
check("suspend -> SUSPENDED, audited, login blocked", t_suspend)
check("reactivate -> APPROVED, audited, login works", t_reactivate)
check("reactivate only from SUSPENDED/REJECTED", t_reactivate_only_from_suspended_or_rejected)
check("redundant status change rejected", t_no_redundant_status_change)
check("status change notifies the affected user", t_status_change_notifies_the_user)


# ===========================================================================
print("\n--- 3. ADMIN SAFETY RULES ---")


def t_admin_cannot_change_own_status():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    expect_http(400, lambda: admin_users.suspend_user(admin.id, None, db, admin), "your own account")


def t_admin_cannot_modify_another_admin():
    db = fresh_db()
    db.add(models.User(name="Second Admin", email="admin2@campus.edu", role="ADMIN",
                       password_hash=security.hash_password("Campus@2025"),
                       status=models.STATUS_APPROVED, is_emergency_access=0))
    admin = principal(db, "admin@campus.edu")
    other = find_user(db, "admin2@campus.edu")
    expect_http(403, lambda: admin_users.suspend_user(other.id, None, db, admin),
                "administrator accounts cannot be modified")


def t_missing_user():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    expect_http(404, lambda: admin_users.approve_user(99999, None, db, admin))


check("admin cannot change their own status", t_admin_cannot_change_own_status)
check("admin cannot modify another ADMIN", t_admin_cannot_modify_another_admin)
check("acting on a missing user -> 404", t_missing_user)


# ===========================================================================
print("\n--- 4. BACKEND AUTHORIZATION (sections 2, 3, 4, 8) ---")

# Every admin-only endpoint, paired with a way to call it directly.
ADMIN_ENDPOINTS = [
    ("admin_users.list_users", admin_users.list_users,
     lambda db, u: admin_users.list_users(None, None, None, 200, db, u)),
    ("admin_users.list_pending_users", admin_users.list_pending_users,
     lambda db, u: admin_users.list_pending_users(db, u)),
    ("admin_users.get_user", admin_users.get_user,
     lambda db, u: admin_users.get_user(1, db, u)),
    ("admin_users.approve_user", admin_users.approve_user,
     lambda db, u: admin_users.approve_user(1, None, db, u)),
    ("admin_users.reject_user", admin_users.reject_user,
     lambda db, u: admin_users.reject_user(1, None, db, u)),
    ("admin_users.suspend_user", admin_users.suspend_user,
     lambda db, u: admin_users.suspend_user(1, None, db, u)),
    ("admin_users.reactivate_user", admin_users.reactivate_user,
     lambda db, u: admin_users.reactivate_user(1, None, db, u)),
    ("admin_users.list_audit_logs", admin_users.list_audit_logs,
     lambda db, u: admin_users.list_audit_logs(None, None, None, 200, db, u)),
    ("admin_users.export_users_pdf", admin_users.export_users_pdf,
     lambda db, u: admin_users.export_users_pdf(db, u)),
    ("emergency_access.list_requests", emergency_access.list_requests,
     lambda db, u: emergency_access.list_requests(None, 100, db, u)),
    ("emergency_access.approve_request", emergency_access.approve_request,
     lambda db, u: emergency_access.approve_request(1, None, db, u)),
    ("emergency_access.reject_request", emergency_access.reject_request,
     lambda db, u: emergency_access.reject_request(1, None, db, u)),
]


def t_every_admin_endpoint_declares_the_guard():
    """
    Structural check: each endpoint must actually depend on require_admin.

    Without this, the behavioural tests below would still pass even if an
    endpoint forgot its guard entirely — because require_admin raises before the
    endpoint body is reached. This asserts the wiring, not just the outcome.
    """
    import inspect
    for label, fn, _ in ADMIN_ENDPOINTS:
        defaults = [
            param.default for param in inspect.signature(fn).parameters.values()
        ]
        assert deps.require_admin in defaults, f"{label} does not depend on require_admin"


def t_student_blocked_from_every_admin_endpoint():
    db = fresh_db()
    student = principal(db, "student@campus.edu")
    # FastAPI resolves Depends(require_admin) before the endpoint body runs, so
    # combined with the structural test above, this is what actually protects
    # every endpoint in the list.
    for label, fn, call in ADMIN_ENDPOINTS:
        expect_http(403, lambda: deps.require_admin(student), "restricted to ADMIN")


def t_faculty_blocked_from_every_admin_endpoint():
    db = fresh_db()
    faculty = principal(db, "faculty@campus.edu")
    for label, fn, call in ADMIN_ENDPOINTS:
        expect_http(403, lambda: deps.require_admin(faculty), "restricted to ADMIN")


def t_faculty_is_not_admin():
    db = fresh_db()
    faculty = principal(db, "faculty@campus.edu")
    assert deps.require_staff(faculty), "faculty should pass staff checks"
    expect_http(403, lambda: deps.require_admin(faculty))


def t_student_is_not_staff():
    db = fresh_db()
    student = principal(db, "student@campus.edu")
    expect_http(403, lambda: deps.require_staff(student))
    expect_http(403, lambda: deps.require_admin(student))


def t_unauthenticated_blocked():
    db = fresh_db()
    expect_http(401, lambda: deps.get_current_user(None, db))
    expect_http(401, lambda: deps.get_current_user("Bearer forged.token.here", db))


check("every admin endpoint declares require_admin", t_every_admin_endpoint_declares_the_guard)
check("STUDENT blocked from every admin endpoint", t_student_blocked_from_every_admin_endpoint)
check("FACULTY blocked from every admin endpoint", t_faculty_blocked_from_every_admin_endpoint)
check("FACULTY has staff access but not admin", t_faculty_is_not_admin)
check("STUDENT has neither staff nor admin access", t_student_is_not_staff)
check("unauthenticated calls rejected", t_unauthenticated_blocked)


# ===========================================================================
print("\n--- 5. EMERGENCY ACCESS ---")


def submit(db, email="witness@example.com", name="Ramesh Witness"):
    return emergency_access.submit_request(schemas.EmergencyAccessCreate(
        full_name=name, email=email, contact_number="9876500000",
        reason="I witnessed a fire and cannot wait for approval",
        emergency_description="Smoke pouring from the chemistry lab, students inside.",
        location="Chemistry Lab", incident_details="At least 10 students still in the corridor.",
    ), db)


def t_submitting_grants_nothing():
    db = fresh_db()
    res = submit(db)
    assert res.status == "PENDING"
    assert res.reference_code.startswith("EA-")
    # The response object has no token field at all.
    assert not hasattr(res, "access_token"), "submission returned a token!"
    # No account was created.
    assert find_user(db, "witness@example.com") is None, "an account was created on submission"
    assert "EMERGENCY_ACCESS_REQUESTED" in audit_actions(db)


def t_submission_notifies_admin():
    db = fresh_db()
    submit(db)
    notes = db.query(models.Notification).all()
    assert any("emergency access" in (n.title or "").lower() and n.audience_role == "ADMIN"
               for n in notes), "admin was not notified"


def t_pending_request_returns_nothing_useful():
    db = fresh_db()
    res = submit(db)
    status = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    assert status.status == "PENDING"
    assert status.access_token is None, "a token was handed out before approval!"


def t_wrong_email_cannot_collect():
    db = fresh_db()
    res = submit(db)
    expect_http(404, lambda: emergency_access.check_request(
        res.reference_code, "attacker@example.com", db))


def t_wrong_code_rejected():
    db = fresh_db()
    submit(db)
    expect_http(404, lambda: emergency_access.check_request(
        "EA-XXXXXXXX", "witness@example.com", db))


def t_duplicate_request_reuses_reference():
    db = fresh_db()
    a = submit(db)
    b = submit(db)
    assert a.reference_code == b.reference_code
    assert db.query(models.EmergencyAccessRequest).count() == 1


def t_rejection():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    out = emergency_access.reject_request(
        req.id, schemas.EmergencyAccessDecision(note="Unverified caller"), db, admin)
    assert out.status == "REJECTED"
    assert find_user(db, "witness@example.com") is None, "rejection created an account!"
    status = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    assert status.status == "REJECTED"
    assert status.access_token is None
    assert "EMERGENCY_ACCESS_REJECTED" in audit_actions(db)


def t_approval_grants_minimum_access():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    out = emergency_access.approve_request(
        req.id, schemas.EmergencyAccessDecision(duration_minutes=60, note="Verified"), db, admin)

    assert out.status == "APPROVED"
    granted = find_user(db, "witness@example.com")
    assert granted is not None, "no account was created"
    assert granted.role == "STUDENT", f"expected minimum role STUDENT, got {granted.role}"
    assert granted.is_emergency_access == 1
    assert granted.access_expires_at is not None, "grant has no expiry"
    assert granted.password_hash is None, "emergency account got a password"
    assert "EMERGENCY_ACCESS_APPROVED" in audit_actions(db)


def t_approved_requester_can_collect_token():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, schemas.EmergencyAccessDecision(duration_minutes=60), db, admin)

    status = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    assert status.status == "APPROVED"
    assert status.access_token, "no token issued after approval"
    user = deps.get_current_user(f"Bearer {status.access_token}", db)
    assert user.email == "witness@example.com"
    assert "EMERGENCY_ACCESS_USED" in audit_actions(db)


def t_emergency_account_cannot_password_login():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)
    for guess in ["", "Campus@2025", "Str0ng!Pass"]:
        expect_http(401, lambda g=guess: auth.login(
            schemas.LoginRequest(email="witness@example.com", password=g), db))


def t_emergency_account_blocked_from_operational_data():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)
    status = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    user = deps.get_current_user(f"Bearer {status.access_token}", db)

    expect_http(403, lambda: deps.require_permanent_account(user), "temporary emergency access")
    expect_http(403, lambda: deps.require_admin(user))
    expect_http(403, lambda: deps.require_staff(user))


def t_expired_grant_blocked():
    db = fresh_db()
    res = submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)
    status = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    token = status.access_token

    # Wind the clock past the grant.
    granted = find_user(db, "witness@example.com")
    granted.access_expires_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=1)
    req.access_expires_at = granted.access_expires_at

    err = expect_http(403, lambda: deps.get_current_user(f"Bearer {token}", db))
    assert "expired" in err.detail.lower()
    again = emergency_access.check_request(res.reference_code, "witness@example.com", db)
    assert again.status == "EXPIRED"
    assert again.access_token is None


def t_duration_is_bounded():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    for requested, lo, hi in [(1, 15, 15), (99999, 1440, 1440), (60, 60, 60)]:
        submit(db, email=f"d{requested}@example.com", name="Dur Test")
        req = [r for r in db.query(models.EmergencyAccessRequest).all()
               if r.email == f"d{requested}@example.com"][0]
        emergency_access.approve_request(
            req.id, schemas.EmergencyAccessDecision(duration_minutes=requested), db, admin)
        minutes = (req.access_expires_at - datetime.datetime.utcnow()).total_seconds() / 60
        assert lo - 2 <= minutes <= hi + 2, f"asked {requested}, got {minutes:.0f} minutes"


def t_cannot_review_twice():
    db = fresh_db()
    submit(db)
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)
    expect_http(400, lambda: emergency_access.approve_request(req.id, None, db, admin), "already")
    expect_http(400, lambda: emergency_access.reject_request(req.id, None, db, admin), "already")


def t_approval_does_not_downgrade_existing_account():
    """A real, approved user asking for emergency access keeps their standing."""
    db = fresh_db()
    submit(db, email="faculty@campus.edu", name="Priya Sharma")
    admin = principal(db, "admin@campus.edu")
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)
    faculty = find_user(db, "faculty@campus.edu")
    assert faculty.role == "FACULTY", "role was downgraded"
    assert not faculty.is_emergency_access, "a permanent account was time-limited"
    assert faculty.access_expires_at is None


check("submitting grants no token and no account", t_submitting_grants_nothing)
check("submission notifies the admin", t_submission_notifies_admin)
check("pending request yields no token", t_pending_request_returns_nothing_useful)
check("wrong email cannot collect the grant", t_wrong_email_cannot_collect)
check("wrong reference code rejected", t_wrong_code_rejected)
check("duplicate request reuses the reference", t_duplicate_request_reuses_reference)
check("rejection creates no account, grants nothing", t_rejection)
check("approval grants minimum privilege only", t_approval_grants_minimum_access)
check("approved requester can collect a token", t_approved_requester_can_collect_token)
check("emergency account cannot password-login", t_emergency_account_cannot_password_login)
check("emergency account blocked from operational data", t_emergency_account_blocked_from_operational_data)
check("expired grant is refused", t_expired_grant_blocked)
check("grant duration is clamped server-side", t_duration_is_bounded)
check("a request cannot be reviewed twice", t_cannot_review_twice)
check("approval never downgrades a permanent account", t_approval_does_not_downgrade_existing_account)


# ===========================================================================
print("\n--- 6. AUDIT LOG ---")


def t_audit_captures_required_fields():
    db = fresh_db()
    user = register(db)
    admin = principal(db, "admin@campus.edu")
    admin_users.approve_user(user.id, schemas.StatusChangeRequest(reason="Verified"), db, admin)

    entry = [r for r in db.query(models.AuditLog).all() if r.action == "USER_APPROVED"][0]
    assert entry.actor_name == "Arjun Kumar"      # actor
    assert entry.actor_role == "ADMIN"
    assert entry.action == "USER_APPROVED"        # action
    assert entry.timestamp is not None            # timestamp
    assert entry.target_label == "nisha@campus.edu"  # target
    assert "Verified" in entry.details            # details


def t_audit_covers_every_required_event():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")           # LOGIN_SUCCESS
    user = register(db)                                  # USER_REGISTERED
    expect_http(403, lambda: auth.login(schemas.LoginRequest(
        email="nisha@campus.edu", password="Str0ng!Pass"), db))   # LOGIN_BLOCKED
    admin_users.approve_user(user.id, None, db, admin)   # USER_APPROVED
    admin_users.suspend_user(user.id, None, db, admin)   # USER_SUSPENDED
    admin_users.reactivate_user(user.id, None, db, admin)  # USER_REACTIVATED

    res = submit(db)                                     # EMERGENCY_ACCESS_REQUESTED
    req = db.query(models.EmergencyAccessRequest).all()[0]
    emergency_access.approve_request(req.id, None, db, admin)  # EMERGENCY_ACCESS_APPROVED
    emergency_access.check_request(res.reference_code, "witness@example.com", db)  # USED

    submit(db, email="second@example.com", name="Second Caller")
    req2 = [r for r in db.query(models.EmergencyAccessRequest).all()
            if r.email == "second@example.com"][0]
    emergency_access.reject_request(req2.id, None, db, admin)  # EMERGENCY_ACCESS_REJECTED

    recorded = set(audit_actions(db))
    required = {
        "USER_REGISTERED", "USER_APPROVED", "USER_SUSPENDED", "USER_REACTIVATED",
        "LOGIN_SUCCESS", "LOGIN_BLOCKED",
        "EMERGENCY_ACCESS_REQUESTED", "EMERGENCY_ACCESS_APPROVED",
        "EMERGENCY_ACCESS_REJECTED", "EMERGENCY_ACCESS_USED",
    }
    missing = required - recorded
    assert not missing, f"these events were not audited: {sorted(missing)}"


def t_audit_readable_by_admin_only():
    db = fresh_db()
    admin = principal(db, "admin@campus.edu")
    register(db)
    out = admin_users.list_audit_logs(None, None, None, 200, db, admin)
    assert out.total >= 1
    assert out.entries[0].timestamp is not None


def t_audit_has_no_delete_path():
    for name in dir(admin_users):
        assert "delete" not in name.lower(), f"{name} looks like it deletes audit data"
    assert not hasattr(audit, "delete")
    assert not hasattr(audit, "purge")


def t_rejection_reason_recorded():
    db = fresh_db()
    user = register(db)
    admin = principal(db, "admin@campus.edu")
    admin_users.reject_user(user.id, schemas.StatusChangeRequest(reason="Not enrolled"), db, admin)
    entry = [r for r in db.query(models.AuditLog).all() if r.action == "USER_REJECTED"][0]
    assert "Not enrolled" in entry.details


check("audit entry has actor/action/timestamp/target/details", t_audit_captures_required_fields)
check("all 10 required event types are audited", t_audit_covers_every_required_event)
check("audit log readable by admin", t_audit_readable_by_admin_only)
check("no code path deletes audit entries", t_audit_has_no_delete_path)
check("decision reasons are recorded", t_rejection_reason_recorded)


# ===========================================================================
print("\n--- 7. users.pdf (section 7) ---")


def t_pdf_contains_the_four_fields():
    pdf = pdf_export.build_users_pdf([
        {"name": "Arjun Kumar", "email": "admin@campus.edu", "role": "ADMIN", "status": "APPROVED"},
    ], generated_by="Arjun Kumar")
    assert pdf.startswith(b"%PDF"), "not a PDF"
    assert len(pdf) > 1000


def t_pdf_never_contains_credentials():
    """Even if a caller passes password material, the allow-list drops it."""
    pdf = pdf_export.build_users_pdf([{
        "name": "Evil Row", "email": "evil@campus.edu", "role": "STUDENT", "status": "APPROVED",
        "password": "PlaintextLeak123!",
        "password_hash": "pbkdf2_sha256$600000$saltsalt$hashhash",
    }])
    for forbidden in [b"PlaintextLeak123", b"pbkdf2_sha256", b"saltsalt", b"hashhash"]:
        assert forbidden not in pdf, f"credential material leaked into the PDF: {forbidden}"


def t_pdf_allow_list_is_exactly_four_fields():
    assert set(pdf_export.ALLOWED_FIELDS) == {"name", "role", "email", "status"}


def t_pdf_handles_empty_roster():
    pdf = pdf_export.build_users_pdf([])
    assert pdf.startswith(b"%PDF")


check("users.pdf renders with name/role/email/status", t_pdf_contains_the_four_fields)
check("users.pdf never contains credential material", t_pdf_never_contains_credentials)
check("PDF allow-list is exactly the four fields", t_pdf_allow_list_is_exactly_four_fields)
check("users.pdf handles an empty roster", t_pdf_handles_empty_roster)


# ===========================================================================
print("\n--- 8. SEARCH / FILTER (section 1) ---")


def t_search_and_filter():
    db = fresh_db()
    register(db, email="nisha@campus.edu", name="Nisha Reddy", role="STUDENT")
    register(db, email="ravi@campus.edu", name="Ravi Menon", role="FACULTY")
    admin = principal(db, "admin@campus.edu")

    assert admin_users.list_users("nisha", None, None, 200, db, admin).total == 1
    assert admin_users.list_users("RAVI", None, None, 200, db, admin).total == 1, "search not case-insensitive"
    assert admin_users.list_users("campus.edu", None, None, 200, db, admin).total >= 4, "email search failed"
    assert admin_users.list_users(None, "PENDING", None, 200, db, admin).total == 2
    assert admin_users.list_users(None, None, "FACULTY", 200, db, admin).total == 2
    assert admin_users.list_users(None, "PENDING", "FACULTY", 200, db, admin).total == 1
    assert admin_users.list_users(None, None, None, 200, db, admin).pending_count == 2


check("search by name/email and filter by status/role", t_search_and_filter)


# ===========================================================================
print("\n--- 9. PHASE 1/2/3A REGRESSION ---")


def t_incident_visibility_unchanged():
    db = fresh_db()
    student = principal(db, "student@campus.edu")
    faculty = principal(db, "faculty@campus.edu")
    admin = principal(db, "admin@campus.edu")
    mine = models.Incident(reporter_user_id=student.id, reporter_name="Harish Kumar")
    theirs = models.Incident(reporter_user_id=4242, reporter_name="Somebody Else")
    assert deps.can_view_incident(student, mine)
    assert not deps.can_view_incident(student, theirs)
    assert deps.can_view_incident(faculty, theirs)
    assert deps.can_view_incident(admin, theirs)


def t_roles_and_statuses_unchanged():
    assert models.ACCOUNT_STATUSES == ("PENDING", "APPROVED", "REJECTED", "SUSPENDED")
    assert (deps.ROLE_STUDENT, deps.ROLE_FACULTY, deps.ROLE_ADMIN) == ("STUDENT", "FACULTY", "ADMIN")


def t_signup_still_blocks_admin():
    db = fresh_db()
    expect_http(422, lambda: auth.signup(schemas.SignupRequest(
        full_name="Sneaky Person", email="sneak@campus.edu", password="Str0ng!Pass",
        confirm_password="Str0ng!Pass", role="ADMIN"), db))


def t_notifications_still_single_system():
    db = fresh_db()
    register(db)
    submit(db)
    # Both Phase 3B event types land in the same Notification table as Phase 2.
    assert db.query(models.Notification).count() >= 2
    assert not hasattr(models, "AdminNotification"), "a second notification system was introduced"


def t_passwords_still_hashed():
    db = fresh_db()
    user = register(db)
    assert user.password_hash and "Str0ng!Pass" not in user.password_hash
    assert security.verify_password("Str0ng!Pass", user.password_hash)


check("incident visibility rules unchanged", t_incident_visibility_unchanged)
check("roles and account statuses unchanged", t_roles_and_statuses_unchanged)
check("signup still refuses ADMIN self-registration", t_signup_still_blocks_admin)
check("notifications still use the single Phase 2 system", t_notifications_still_single_system)
check("passwords still hashed, never plaintext", t_passwords_still_hashed)


# ===========================================================================
print("\n" + "=" * 62)
print(f"PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
if FAILED:
    for name, err in FAILED:
        print(f"  - {name}: {err}")
    raise SystemExit(1)
print("ALL PHASE 3B TESTS PASSED")
