import React, { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { signup } from "../api/client";
import {
  PASSWORD_RULES,
  STRENGTH_COLORS,
  STRENGTH_LABELS,
  isPasswordValid,
  passwordStrength,
} from "../utils/password";

/**
 * Phase 3A — self-registration for STUDENT and FACULTY.
 *
 * ADMIN is deliberately absent from the role options, and the backend also
 * rejects it independently — so adding the option back in the browser's dev
 * tools achieves nothing.
 *
 * Every validation below is mirrored on the backend. This copy only exists to
 * give quick feedback while typing.
 */
const ROLES = [
  { value: "STUDENT", label: "Student", hint: "Report emergencies and track your own reports" },
  { value: "FACULTY", label: "Faculty", hint: "Report emergencies and view the campus incident queue" },
];

export default function Signup() {
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirm_password: "",
    role: "STUDENT",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  const update = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setError("");
  };

  const markTouched = (field) => () => setTouched((t) => ({ ...t, [field]: true }));

  const strength = useMemo(() => passwordStrength(form.password), [form.password]);
  const passwordsMatch =
    form.confirm_password.length > 0 && form.password === form.confirm_password;

  const emailLooksValid = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(form.email.trim());

  const canSubmit =
    form.full_name.trim().length >= 2 &&
    emailLooksValid &&
    isPasswordValid(form.password) &&
    passwordsMatch &&
    !loading;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    // Frontend validation (the backend repeats all of this).
    if (form.full_name.trim().length < 2) return setError("Please enter your full name.");
    if (!emailLooksValid) return setError("Please enter a valid email address.");
    if (!isPasswordValid(form.password)) return setError("Your password does not meet the requirements below.");
    if (form.password !== form.confirm_password) return setError("Passwords do not match.");

    setLoading(true);
    try {
      const res = await signup({
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        password: form.password,
        confirm_password: form.confirm_password,
        role: form.role,
      });
      setSuccess(res.data.message || "Account created. Your account is pending administrator approval.");
      setForm({ full_name: "", email: "", password: "", confirm_password: "", role: "STUDENT" });
      setTouched({});
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response) {
        setError(
          typeof detail === "string"
            ? detail
            : "We couldn't create your account. Please check your details and try again."
        );
      } else {
        setError("Could not reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div
        className="d-flex align-items-center justify-content-center py-5"
        style={{ minHeight: "100vh", background: "linear-gradient(135deg,#1a1a2e,#16213e)" }}
      >
        <div className="card shadow-lg p-4 text-center" style={{ width: 460, maxWidth: "94vw" }}>
          <div className="fs-1">✅</div>
          <h4 className="fw-bold mt-2">Account created</h4>
          <p className="text-muted">{success}</p>
          <p className="small text-muted">
            An administrator will review your registration. You'll be able to sign in once your
            account has been approved.
          </p>
          <button className="btn btn-danger" onClick={() => navigate("/login")}>
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="d-flex align-items-center justify-content-center py-5"
      style={{ minHeight: "100vh", background: "linear-gradient(135deg,#1a1a2e,#16213e)" }}
    >
      <div className="card shadow-lg p-4" style={{ width: 480, maxWidth: "94vw" }}>
        <div className="text-center mb-4">
          <h2 className="fw-bold mb-1">🎓 Campus ERP</h2>
          <p className="text-muted mb-0">Create your account</p>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className="mb-3">
            <label className="form-label" htmlFor="su-name">Full name</label>
            <input
              id="su-name"
              type="text"
              className="form-control"
              placeholder="e.g. Nisha Reddy"
              value={form.full_name}
              onChange={update("full_name")}
              onBlur={markTouched("full_name")}
              autoComplete="name"
              required
            />
          </div>

          <div className="mb-3">
            <label className="form-label" htmlFor="su-email">Email</label>
            <input
              id="su-email"
              type="email"
              className={
                "form-control" +
                (touched.email && form.email && !emailLooksValid ? " is-invalid" : "")
              }
              placeholder="you@campus.edu"
              value={form.email}
              onChange={update("email")}
              onBlur={markTouched("email")}
              autoComplete="username"
              required
            />
            {touched.email && form.email && !emailLooksValid && (
              <div className="invalid-feedback">Please enter a valid email address.</div>
            )}
          </div>

          <div className="mb-3">
            <label className="form-label" htmlFor="su-role">I am a</label>
            <select
              id="su-role"
              className="form-select"
              value={form.role}
              onChange={update("role")}
            >
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <div className="form-text">
              {ROLES.find((r) => r.value === form.role)?.hint}
            </div>
          </div>

          <div className="mb-2">
            <label className="form-label" htmlFor="su-password">Password</label>
            <div className="input-group">
              <input
                id="su-password"
                type={showPassword ? "text" : "password"}
                className="form-control"
                value={form.password}
                onChange={update("password")}
                onBlur={markTouched("password")}
                autoComplete="new-password"
                required
              />
              <button
                className="btn btn-outline-secondary"
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? "🙈" : "👁️"}
              </button>
            </div>

            {form.password && (
              <div className="mt-2">
                <div className="d-flex align-items-center gap-2">
                  <div className="flex-grow-1 rounded" style={{ height: 6, background: "#e9ecef" }}>
                    <div
                      className="rounded"
                      style={{
                        height: 6,
                        width: `${(strength / 4) * 100}%`,
                        background: STRENGTH_COLORS[strength],
                        transition: "width .2s ease",
                      }}
                    />
                  </div>
                  <small className="text-muted" style={{ minWidth: 48 }}>
                    {STRENGTH_LABELS[strength]}
                  </small>
                </div>
              </div>
            )}

            <ul className="list-unstyled small mt-2 mb-0">
              {PASSWORD_RULES.map((rule) => {
                const met = rule.test(form.password || "");
                return (
                  <li key={rule.id} className={met ? "text-success" : "text-muted"}>
                    <span className="me-1">{met ? "✓" : "○"}</span>
                    {rule.label}
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="mb-3">
            <label className="form-label" htmlFor="su-confirm">Confirm password</label>
            <input
              id="su-confirm"
              type={showPassword ? "text" : "password"}
              className={
                "form-control" +
                (form.confirm_password && !passwordsMatch ? " is-invalid" : "") +
                (passwordsMatch ? " is-valid" : "")
              }
              value={form.confirm_password}
              onChange={update("confirm_password")}
              onBlur={markTouched("confirm_password")}
              autoComplete="new-password"
              required
            />
            {form.confirm_password && !passwordsMatch && (
              <div className="invalid-feedback">Passwords do not match.</div>
            )}
          </div>

          {error && <div className="alert alert-danger py-2">{error}</div>}

          <div className="alert alert-info py-2 small mb-3">
            New accounts require administrator approval before you can sign in.
          </div>

          <button className="btn btn-danger w-100" type="submit" disabled={!canSubmit}>
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <hr />

        <p className="text-center text-muted small mb-0">
          Already have an account?{" "}
          <Link to="/login" className="fw-semibold text-decoration-none">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
