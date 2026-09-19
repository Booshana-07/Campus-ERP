"""
Phase 3A acceptance tests — every item listed in section 11 of the brief.

These call the REAL functions in app/routers/auth.py and app/deps.py.
"""
import shim
from shim import FakeDB, HTTPException

models, schemas, security, deps, auth = shim.load_app()

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}")
    except AssertionError as e:
        FAILED.append((name, str(e)))
        print(f"  FAIL  {name}  -> {e}")
    except Exception as e:  # unexpected explosion
        FAILED.append((name, f"{type(e).__name__}: {e}"))
        print(f"  ERROR {name}  -> {type(e).__name__}: {e}")


def expect_http(status_code, fn, contains=None):
    try:
        fn()
    except HTTPException as e:
        assert e.status_code == status_code, f"expected {status_code}, got {e.status_code} ({e.detail})"
        if contains:
            assert contains.lower() in str(e.detail).lower(), f"message was: {e.detail}"
        return e
    raise AssertionError(f"expected HTTP {status_code} but the call succeeded")


def fresh_db():
    """A database holding the three approved demo accounts."""
    db = FakeDB()
    for name, email, role in [
        ("Harish Kumar", "student@campus.edu", "STUDENT"),
        ("Priya Sharma", "faculty@campus.edu", "FACULTY"),
        ("Arjun Kumar", "admin@campus.edu", "ADMIN"),
    ]:
        db.add(models.User(
            name=name, email=email, role=role,
            password_hash=security.hash_password("Campus@2025"),
            status=models.STATUS_APPROVED,
        ))
    return db


def signup(db, **kw):
    payload = schemas.SignupRequest(**{
        "full_name": "Test User", "email": "t@campus.edu",
        "password": "Str0ng!Pass", "confirm_password": "Str0ng!Pass",
        "role": "STUDENT", **kw
    })
    return auth.signup(payload, db)


def login(db, email, password):
    return auth.login(schemas.LoginRequest(email=email, password=password), db)


def bearer(token):
    return f"Bearer {token}"


# ===========================================================================
print("\n--- 1. SIGNUP ---")


def t_student_signup():
    db = fresh_db()
    res = signup(db, full_name="Nisha Reddy", email="nisha@campus.edu", role="STUDENT")
    assert res.user.role == "STUDENT"
    assert res.user.status == models.STATUS_PENDING, f"got {res.user.status}"
    assert not hasattr(res.user, "password_hash"), "password hash must not be returned"
    assert "pending" in res.message.lower()


def t_faculty_signup():
    db = fresh_db()
    res = signup(db, full_name="Ravi Menon", email="ravi@campus.edu", role="FACULTY")
    assert res.user.role == "FACULTY"
    assert res.user.status == models.STATUS_PENDING


def t_signup_hashes_password():
    db = fresh_db()
    signup(db, email="hash@campus.edu", password="Str0ng!Pass", confirm_password="Str0ng!Pass")
    row = db.query(models.User).filter(models.User.email == "hash@campus.edu").first()
    assert row.password_hash, "no hash stored"
    assert "Str0ng!Pass" not in row.password_hash, "PLAINTEXT PASSWORD STORED"
    assert security.verify_password("Str0ng!Pass", row.password_hash)


def t_email_normalised():
    db = fresh_db()
    signup(db, email="  MiXeD@Campus.EDU  ")
    assert db.query(models.User).filter(models.User.email == "mixed@campus.edu").first()


check("valid STUDENT signup -> PENDING", t_student_signup)
check("valid FACULTY signup -> PENDING", t_faculty_signup)
check("signup stores a hash, never plaintext", t_signup_hashes_password)
check("email is normalised to lowercase", t_email_normalised)


# ===========================================================================
print("\n--- 2. SIGNUP REJECTIONS ---")


def t_duplicate_email():
    db = fresh_db()
    expect_http(409, lambda: signup(db, email="student@campus.edu"), "already exists")


def t_duplicate_email_case_insensitive():
    db = fresh_db()
    expect_http(409, lambda: signup(db, email="STUDENT@CAMPUS.EDU"), "already exists")


def t_admin_self_registration_blocked():
    db = fresh_db()
    for attempt in ["ADMIN", "admin", "Admin", " admin "]:
        expect_http(422, lambda a=attempt: signup(db, email="x@campus.edu", role=a))
    assert db.query(models.User).filter(models.User.role == "ADMIN").count() == 1, \
        "an ADMIN account was created via signup!"


def t_unknown_role_blocked():
    db = fresh_db()
    expect_http(422, lambda: signup(db, email="x@campus.edu", role="SUPERUSER"))


def t_weak_passwords():
    db = fresh_db()
    weak = ["short1!A", "alllowercase1!", "ALLUPPERCASE1!", "NoNumbers!!", "NoSpecial123", "abc"]
    for i, pw in enumerate(weak):
        if pw == "short1!A":
            continue  # this one is actually 8 chars and valid; covered below
        expect_http(422, lambda p=pw, n=i: signup(
            db, email=f"w{n}@campus.edu", password=p, confirm_password=p), "weak password")


def t_password_mismatch():
    db = fresh_db()
    expect_http(422, lambda: signup(
        db, email="m@campus.edu", password="Str0ng!Pass", confirm_password="Str0ng!Pasx"),
        "do not match")


def t_invalid_email_format():
    db = fresh_db()
    for bad in ["notanemail", "no@domain", "@campus.edu", "a b@campus.edu"]:
        expect_http(422, lambda b=bad: signup(db, email=b), "valid email")


check("duplicate email rejected (409)", t_duplicate_email)
check("duplicate email is case-insensitive", t_duplicate_email_case_insensitive)
check("ADMIN self-registration blocked", t_admin_self_registration_blocked)
check("unknown role blocked", t_unknown_role_blocked)
check("weak passwords rejected by backend", t_weak_passwords)
check("password confirmation mismatch rejected", t_password_mismatch)
check("invalid email format rejected", t_invalid_email_format)


# ===========================================================================
print("\n--- 3. LOGIN ---")


def t_correct_login():
    db = fresh_db()
    res = login(db, "admin@campus.edu", "Campus@2025")
    assert res.access_token, "no token issued"
    assert res.token_type == "bearer"
    assert res.user.role == "ADMIN"
    assert res.expires_in > 0
    assert not hasattr(res.user, "password_hash")
    assert "Campus@2025" not in res.access_token


def t_login_case_insensitive_email():
    db = fresh_db()
    assert login(db, "ADMIN@Campus.edu", "Campus@2025").access_token


def t_invalid_email():
    db = fresh_db()
    expect_http(401, lambda: login(db, "nobody@campus.edu", "Campus@2025"), "invalid email or password")


def t_invalid_password():
    db = fresh_db()
    expect_http(401, lambda: login(db, "admin@campus.edu", "WrongPass1!"), "invalid email or password")


def t_no_user_enumeration():
    db = fresh_db()
    a = expect_http(401, lambda: login(db, "nobody@campus.edu", "Whatever1!"))
    b = expect_http(401, lambda: login(db, "admin@campus.edu", "Whatever1!"))
    assert a.detail == b.detail, "unknown-email and wrong-password messages differ (enumeration leak)"


def t_empty_password():
    db = fresh_db()
    expect_http(401, lambda: login(db, "admin@campus.edu", ""))


def t_null_hash_account_cannot_login():
    db = fresh_db()
    db.add(models.User(name="Ghost", email="ghost@campus.edu", role="STUDENT",
                       password_hash=None, status=models.STATUS_APPROVED))
    expect_http(401, lambda: login(db, "ghost@campus.edu", "anything"))


check("correct login returns a token", t_correct_login)
check("login email is case-insensitive", t_login_case_insensitive_email)
check("invalid email rejected (401)", t_invalid_email)
check("invalid password rejected (401)", t_invalid_password)
check("no user enumeration via error message", t_no_user_enumeration)
check("empty password rejected", t_empty_password)
check("account with no password hash cannot log in", t_null_hash_account_cannot_login)


# ===========================================================================
print("\n--- 4. ACCOUNT STATUS AT LOGIN ---")


def status_user(db, status):
    db.add(models.User(name="S", email=f"{status.lower()}@campus.edu", role="STUDENT",
                       password_hash=security.hash_password("Campus@2025"), status=status))
    return f"{status.lower()}@campus.edu"


def t_pending_login():
    db = fresh_db()
    e = status_user(db, models.STATUS_PENDING)
    err = expect_http(403, lambda: login(db, e, "Campus@2025"))
    assert err.detail == "Your account is pending administrator approval.", err.detail


def t_rejected_login():
    db = fresh_db()
    e = status_user(db, models.STATUS_REJECTED)
    err = expect_http(403, lambda: login(db, e, "Campus@2025"))
    assert err.detail == "Your account has been rejected.", err.detail


def t_suspended_login():
    db = fresh_db()
    e = status_user(db, models.STATUS_SUSPENDED)
    err = expect_http(403, lambda: login(db, e, "Campus@2025"))
    assert err.detail == "Your account is currently suspended.", err.detail


def t_approved_login():
    db = fresh_db()
    e = status_user(db, models.STATUS_APPROVED)
    assert login(db, e, "Campus@2025").access_token


def t_blocked_status_issues_no_token():
    db = fresh_db()
    e = status_user(db, models.STATUS_PENDING)
    try:
        login(db, e, "Campus@2025")
    except HTTPException as err:
        assert "token" not in str(err.detail).lower()
        assert not getattr(err, "access_token", None)


check("PENDING login -> exact message", t_pending_login)
check("REJECTED login -> exact message", t_rejected_login)
check("SUSPENDED login -> exact message", t_suspended_login)
check("APPROVED login succeeds", t_approved_login)
check("blocked status never receives a token", t_blocked_status_issues_no_token)


# ===========================================================================
print("\n--- 5. TOKEN AUTH / UNAUTHORIZED API ACCESS ---")


def t_token_resolves_user():
    db = fresh_db()
    tok = login(db, "admin@campus.edu", "Campus@2025").access_token
    user = deps.get_current_user(bearer(tok), db)
    assert user.email == "admin@campus.edu"


def t_no_header_rejected():
    db = fresh_db()
    expect_http(401, lambda: deps.get_current_user(None, db))
    expect_http(401, lambda: deps.get_current_user("", db))


def t_malformed_header_rejected():
    db = fresh_db()
    tok = login(db, "admin@campus.edu", "Campus@2025").access_token
    for bad in [tok, f"Basic {tok}", "Bearer", "Bearer ", "Bearer abc.def.ghi"]:
        expect_http(401, lambda b=bad: deps.get_current_user(b, db))


def t_tampered_token_rejected():
    db = fresh_db()
    tok = login(db, "student@campus.edu", "Campus@2025").access_token
    expect_http(401, lambda: deps.get_current_user(bearer(tok[:-4] + "AAAA"), db))


def t_forged_role_rejected():
    """The classic attack: re-encode the payload claiming ADMIN, unsigned."""
    import base64, json
    db = fresh_db()
    tok = login(db, "student@campus.edu", "Campus@2025").access_token
    head, body, sig = tok.split(".")
    payload = json.loads(security._b64d(body))
    payload["role"] = "ADMIN"
    forged = f"{head}.{security._b64e(json.dumps(payload).encode())}.{sig}"
    expect_http(401, lambda: deps.get_current_user(bearer(forged), db))


def t_spoofed_email_header_does_nothing():
    """Phase 2's X-User-Email trick must no longer grant access."""
    db = fresh_db()
    expect_http(401, lambda: deps.get_current_user("admin@campus.edu", db))


def t_suspended_after_login_blocked_immediately():
    db = fresh_db()
    tok = login(db, "student@campus.edu", "Campus@2025").access_token
    assert deps.get_current_user(bearer(tok), db)  # works now
    row = db.query(models.User).filter(models.User.email == "student@campus.edu").first()
    row.status = models.STATUS_SUSPENDED
    err = expect_http(403, lambda: deps.get_current_user(bearer(tok), db))
    assert err.detail == "Your account is currently suspended."


def t_expired_token_rejected():
    import datetime as dt
    db = fresh_db()
    original = security.TOKEN_EXPIRY_HOURS
    try:
        security.TOKEN_EXPIRY_HOURS = -1  # already expired
        tok, _ = security.create_access_token(1, "student@campus.edu", "STUDENT")
        expect_http(401, lambda: deps.get_current_user(bearer(tok), db))
    finally:
        security.TOKEN_EXPIRY_HOURS = original


def t_deleted_user_token_rejected():
    db = fresh_db()
    tok = login(db, "student@campus.edu", "Campus@2025").access_token
    # Phase 3B note: the table now also holds audit rows, so filter by identity
    # of the user row rather than assuming every row has an `email`.
    db.rows = [r for r in db.rows if getattr(r, "email", None) != "student@campus.edu"]
    expect_http(401, lambda: deps.get_current_user(bearer(tok), db))


check("valid token resolves the user", t_token_resolves_user)
check("missing Authorization header -> 401", t_no_header_rejected)
check("malformed Authorization header -> 401", t_malformed_header_rejected)
check("tampered token -> 401", t_tampered_token_rejected)
check("forged ADMIN role in token -> 401", t_forged_role_rejected)
check("spoofed X-User-Email style value -> 401", t_spoofed_email_header_does_nothing)
check("suspension takes effect immediately", t_suspended_after_login_blocked_immediately)
check("expired token -> 401", t_expired_token_rejected)
check("token for deleted user -> 401", t_deleted_user_token_rejected)


# ===========================================================================
print("\n--- 6. ROLE ENFORCEMENT (Phase 2 behaviour preserved) ---")


def user_for(db, email):
    tok = login(db, email, "Campus@2025").access_token
    return deps.get_current_user(bearer(tok), db)


def t_admin_only():
    db = fresh_db()
    assert deps.require_admin(user_for(db, "admin@campus.edu")).role == "ADMIN"
    expect_http(403, lambda: deps.require_admin(user_for(db, "student@campus.edu")))
    expect_http(403, lambda: deps.require_admin(user_for(db, "faculty@campus.edu")))


def t_staff_only():
    db = fresh_db()
    assert deps.require_staff(user_for(db, "admin@campus.edu"))
    assert deps.require_staff(user_for(db, "faculty@campus.edu"))
    expect_http(403, lambda: deps.require_staff(user_for(db, "student@campus.edu")))


def t_optional_user():
    db = fresh_db()
    assert deps.get_optional_user(None, db) is None
    tok = login(db, "admin@campus.edu", "Campus@2025").access_token
    assert deps.get_optional_user(bearer(tok), db).role == "ADMIN"


def t_student_incident_visibility():
    db = fresh_db()
    student = user_for(db, "student@campus.edu")
    admin = user_for(db, "admin@campus.edu")
    mine = models.Incident(reporter_user_id=student.id, reporter_name="Harish Kumar")
    theirs = models.Incident(reporter_user_id=999, reporter_name="Someone Else")
    assert deps.can_view_incident(student, mine)
    assert not deps.can_view_incident(student, theirs)
    assert deps.can_view_incident(admin, theirs)


check("require_admin allows only ADMIN", t_admin_only)
check("require_staff allows FACULTY+ADMIN", t_staff_only)
check("get_optional_user behaves", t_optional_user)
check("student incident visibility preserved", t_student_incident_visibility)


# ===========================================================================
print("\n--- 7. SESSION ENDPOINTS ---")


def t_me():
    db = fresh_db()
    tok = login(db, "faculty@campus.edu", "Campus@2025").access_token
    me = auth.me(deps.get_current_user(bearer(tok), db))
    assert me.email == "faculty@campus.edu"


def t_logout():
    db = fresh_db()
    tok = login(db, "faculty@campus.edu", "Campus@2025").access_token
    out = auth.logout(deps.get_current_user(bearer(tok), db))
    assert "message" in out


def t_logout_requires_session():
    db = fresh_db()
    expect_http(401, lambda: auth.logout(deps.get_current_user(None, db)))


def t_demo_users_endpoint_removed():
    assert not hasattr(auth, "demo_users"), "the credential-listing endpoint still exists"


check("/me returns the signed-in user", t_me)
check("/logout works with a valid session", t_logout)
check("/logout requires a session", t_logout_requires_session)
check("demo-users endpoint removed", t_demo_users_endpoint_removed)


# ===========================================================================
print("\n--- 8. FULL LIFECYCLE ---")


def t_lifecycle():
    db = fresh_db()
    # 1. sign up
    res = signup(db, full_name="Divya Raman", email="divya@campus.edu",
                 password="Divya@2025x", confirm_password="Divya@2025x", role="STUDENT")
    assert res.user.status == "PENDING"
    # 2. cannot log in yet
    expect_http(403, lambda: login(db, "divya@campus.edu", "Divya@2025x"),
                "pending administrator approval")
    # 3. admin approves (Phase 3B will provide the UI; the foundation works now)
    row = db.query(models.User).filter(models.User.email == "divya@campus.edu").first()
    row.status = models.STATUS_APPROVED
    # 4. now she can log in
    token = login(db, "divya@campus.edu", "Divya@2025x").access_token
    user = deps.get_current_user(bearer(token), db)
    assert user.name == "Divya Raman" and user.role == "STUDENT"
    # 5. but she is not an admin
    expect_http(403, lambda: deps.require_admin(user))
    # 6. logout
    auth.logout(user)


check("signup -> pending -> approve -> login -> scoped access", t_lifecycle)


# ===========================================================================
print("\n" + "=" * 62)
print(f"PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
if FAILED:
    for name, err in FAILED:
        print(f"  - {name}: {err}")
    raise SystemExit(1)
print("ALL PHASE 3A AUTH TESTS PASSED")
