import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { checkEmergencyAccess, requestEmergencyAccess } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { homeRouteFor } from "../roles";

/**
 * Phase 3B, section 5 — the public emergency access page.
 *
 * Two tabs: submit a request, or check one you already submitted.
 *
 * Submitting grants nothing. An administrator must approve it, and only then
 * does checking the reference code return a time-limited, minimum-privilege
 * session. This page cannot bypass authentication — it has no way to.
 */
export default function EmergencyAccess() {
  const [tab, setTab] = useState("request");

  return (
    <div
      className="d-flex align-items-center justify-content-center py-5"
      style={{ minHeight: "100vh", background: "linear-gradient(135deg,#2b1216,#16213e)" }}
    >
      <div className="card shadow-lg p-4" style={{ width: 560, maxWidth: "94vw" }}>
        <div className="text-center mb-3">
          <div className="fs-2">🚨</div>
          <h4 className="fw-bold mb-1">Emergency Access</h4>
          <p className="text-muted small mb-0">
            For people without an approved account who need to report a live emergency.
          </p>
        </div>

        <div className="alert alert-danger py-2 small">
          <strong>If life is in danger, call campus security or emergency services first.</strong>{" "}
          This form notifies a campus administrator, who must approve it before access is granted.
        </div>

        <ul className="nav nav-pills nav-fill mb-3">
          <li className="nav-item">
            <button
              className={`nav-link ${tab === "request" ? "active bg-danger" : "text-dark"}`}
              onClick={() => setTab("request")}
              type="button"
            >
              Request access
            </button>
          </li>
          <li className="nav-item">
            <button
              className={`nav-link ${tab === "check" ? "active bg-danger" : "text-dark"}`}
              onClick={() => setTab("check")}
              type="button"
            >
              Check my request
            </button>
          </li>
        </ul>

        {tab === "request" ? <RequestForm onSubmitted={() => setTab("check")} /> : <CheckForm />}

        <hr />
        <p className="text-center text-muted small mb-0">
          <Link to="/login" className="fw-semibold text-decoration-none">
            Back to login
          </Link>
          {" · "}
          <Link to="/signup" className="fw-semibold text-decoration-none">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function RequestForm({ onSubmitted }) {
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    contact_number: "",
    reason: "",
    emergency_description: "",
    location: "",
    incident_details: "",
  });
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const update = (field) => (e) => {
    setForm((f) => ({ ...f, [field]: e.target.value }));
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (form.full_name.trim().length < 2) return setError("Please enter your full name.");
    if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(form.email.trim()))
      return setError("Please enter a valid email address.");
    if (form.reason.trim().length < 5) return setError("Please explain why you need access.");
    if (form.emergency_description.trim().length < 10)
      return setError("Please describe the emergency in a little more detail.");

    setLoading(true);
    try {
      const res = await requestEmergencyAccess({
        full_name: form.full_name.trim(),
        email: form.email.trim().toLowerCase(),
        contact_number: form.contact_number.trim() || undefined,
        reason: form.reason.trim(),
        emergency_description: form.emergency_description.trim(),
        location: form.location.trim() || undefined,
        incident_details: form.incident_details.trim() || undefined,
      });
      setResult(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Could not send your request. If this is urgent, call campus security now."
      );
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div className="text-center">
        <div className="fs-1">📨</div>
        <h5 className="fw-bold mt-2">Request sent</h5>
        <p className="text-muted small">{result.message}</p>
        <div className="alert alert-warning py-3">
          <div className="small text-muted mb-1">Your reference code</div>
          <div className="fs-4 fw-bold font-monospace">{result.reference_code}</div>
        </div>
        <p className="small text-muted">
          Write this down. You need it, together with your email address, to collect access
          once an administrator approves the request.
        </p>
        <button className="btn btn-danger w-100" onClick={onSubmitted}>
          Check my request
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate>
      <div className="row g-2">
        <div className="col-12 col-md-6">
          <label className="form-label small fw-semibold">Full name *</label>
          <input className="form-control" value={form.full_name} onChange={update("full_name")} required />
        </div>
        <div className="col-12 col-md-6">
          <label className="form-label small fw-semibold">Email *</label>
          <input
            type="email"
            className="form-control"
            value={form.email}
            onChange={update("email")}
            required
          />
        </div>
        <div className="col-12 col-md-6">
          <label className="form-label small fw-semibold">Contact number</label>
          <input className="form-control" value={form.contact_number} onChange={update("contact_number")} />
        </div>
        <div className="col-12 col-md-6">
          <label className="form-label small fw-semibold">Where are you now?</label>
          <input
            className="form-control"
            placeholder="e.g. Electrical Lab"
            value={form.location}
            onChange={update("location")}
          />
        </div>
        <div className="col-12">
          <label className="form-label small fw-semibold">What is the emergency? *</label>
          <textarea
            className="form-control"
            rows={3}
            value={form.emergency_description}
            onChange={update("emergency_description")}
            placeholder="Describe what is happening right now."
            required
          />
        </div>
        <div className="col-12">
          <label className="form-label small fw-semibold">Why do you need access? *</label>
          <textarea
            className="form-control"
            rows={2}
            value={form.reason}
            onChange={update("reason")}
            placeholder="e.g. I am a visiting contractor and my account is not approved yet."
            required
          />
        </div>
        <div className="col-12">
          <label className="form-label small fw-semibold">Other relevant details</label>
          <textarea
            className="form-control"
            rows={2}
            value={form.incident_details}
            onChange={update("incident_details")}
          />
        </div>
      </div>

      {error && <div className="alert alert-danger py-2 mt-3 mb-0">{error}</div>}

      <button className="btn btn-danger w-100 mt-3" type="submit" disabled={loading}>
        {loading ? "Sending..." : "Send emergency access request"}
      </button>
    </form>
  );
}

/* ------------------------------------------------------------------ */
function CheckForm() {
  const [reference, setReference] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const { loginUser } = useAuth();
  const navigate = useNavigate();

  const check = async (e) => {
    e.preventDefault();
    setError("");
    setStatus(null);
    setLoading(true);
    try {
      const res = await checkEmergencyAccess(reference.trim().toUpperCase(), email.trim().toLowerCase());
      setStatus(res.data);

      // Approved and still within the window: the backend returned a session.
      if (res.data.access_token && res.data.user) {
        loginUser(res.data.user, res.data.access_token);
      }
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          "Could not check that request. Check your reference code and email."
      );
    } finally {
      setLoading(false);
    }
  };

  const enter = () => navigate(homeRouteFor(status?.user?.role || "STUDENT"));

  return (
    <>
      <form onSubmit={check} noValidate>
        <div className="mb-3">
          <label className="form-label small fw-semibold">Reference code</label>
          <input
            className="form-control font-monospace"
            placeholder="EA-XXXXXXXX"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            required
          />
        </div>
        <div className="mb-3">
          <label className="form-label small fw-semibold">Email used on the request</label>
          <input
            type="email"
            className="form-control"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        {error && <div className="alert alert-danger py-2">{error}</div>}

        <button className="btn btn-danger w-100" type="submit" disabled={loading}>
          {loading ? "Checking..." : "Check status"}
        </button>
      </form>

      {status && (
        <div className="mt-3">
          {status.status === "PENDING" && (
            <div className="alert alert-warning py-2 mb-0">
              <div className="fw-semibold">Awaiting review</div>
              <div className="small">{status.message}</div>
            </div>
          )}

          {status.status === "REJECTED" && (
            <div className="alert alert-danger py-2 mb-0">
              <div className="fw-semibold">Not approved</div>
              <div className="small">{status.message}</div>
            </div>
          )}

          {status.status === "EXPIRED" && (
            <div className="alert alert-secondary py-2 mb-0">
              <div className="fw-semibold">Access expired</div>
              <div className="small">{status.message}</div>
            </div>
          )}

          {status.status === "APPROVED" && status.access_token && (
            <div className="alert alert-success py-3 mb-0">
              <div className="fw-semibold">Emergency access granted</div>
              <div className="small">{status.message}</div>
              {status.access_expires_at && (
                <div className="small mt-1">
                  Expires: {new Date(status.access_expires_at).toLocaleString()}
                </div>
              )}
              <button className="btn btn-danger w-100 mt-3" onClick={enter}>
                Continue and report the emergency
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
