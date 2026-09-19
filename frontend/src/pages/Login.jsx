import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { login } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { homeRouteFor } from "../roles";

/**
 * Phase 3A — real email + password login.
 *
 * The Phase 1/2 quick-login buttons have been removed: they listed working
 * accounts directly in the UI and in the page source. No credentials appear
 * anywhere in this file.
 */
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [statusNotice, setStatusNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const { loginUser } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionExpired = searchParams.get("expired") === "1";

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setStatusNotice("");

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !password) {
      setError("Please enter both your email and password.");
      return;
    }

    setLoading(true);
    try {
      const res = await login(trimmedEmail, password);
      const { access_token, user } = res.data;
      loginUser(user, access_token);
      // Clear the password from memory as soon as it has been used.
      setPassword("");
      navigate(homeRouteFor(user.role));
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail;

      if (status === 403) {
        // PENDING / REJECTED / SUSPENDED — the backend decides the wording.
        setStatusNotice(detail || "Your account is not currently active.");
      } else if (status === 401) {
        setError(detail || "Invalid email or password.");
      } else if (status === 422) {
        setError(detail || "Please check the details you entered.");
      } else if (err.response) {
        setError("Something went wrong signing you in. Please try again.");
      } else {
        setError("Could not reach the server. Is the backend running on port 8000?");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="d-flex align-items-center justify-content-center py-5"
      style={{ minHeight: "100vh", background: "linear-gradient(135deg,#1a1a2e,#16213e)" }}
    >
      <div className="card shadow-lg p-4" style={{ width: 420, maxWidth: "94vw" }}>
        <div className="text-center mb-4">
          <h2 className="fw-bold mb-1">🎓 Campus ERP</h2>
          <p className="text-muted mb-0">AI-Powered Emergency Response Platform</p>
        </div>

        {sessionExpired && !error && !statusNotice && (
          <div className="alert alert-warning py-2 small">
            Your session has ended. Please sign in again.
          </div>
        )}

        <form onSubmit={handleLogin} noValidate>
          <div className="mb-3">
            <label className="form-label" htmlFor="login-email">Email</label>
            <input
              id="login-email"
              type="email"
              className="form-control"
              placeholder="you@campus.edu"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <div className="mb-3">
            <label className="form-label" htmlFor="login-password">Password</label>
            <div className="input-group">
              <input
                id="login-password"
                type={showPassword ? "text" : "password"}
                className="form-control"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
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
          </div>

          {error && <div className="alert alert-danger py-2">{error}</div>}

          {statusNotice && (
            <div className="alert alert-warning py-2">
              <div className="fw-semibold mb-1">Account not active</div>
              <div className="small">{statusNotice}</div>
            </div>
          )}

          <button className="btn btn-danger w-100" type="submit" disabled={loading}>
            {loading ? "Signing in..." : "Login"}
          </button>
        </form>

        <hr />

        <p className="text-center text-muted small mb-2">
          Don't have an account?{" "}
          <Link to="/signup" className="fw-semibold text-decoration-none">
            Create one
          </Link>
        </p>

        {/* Phase 3B: a controlled route for someone with a genuine emergency and
            no approved account. It is a request for review, not a bypass. */}
        <Link
          to="/emergency-access"
          className="btn btn-outline-danger btn-sm w-100 d-flex align-items-center justify-content-center gap-2"
        >
          <span>🚨</span>
          <span>Emergency access (no approved account)</span>
        </Link>
      </div>
    </div>
  );
}
