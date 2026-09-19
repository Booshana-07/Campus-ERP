import React, { useCallback, useEffect, useState } from "react";
import {
  approveEmergencyRequest,
  listEmergencyRequests,
  rejectEmergencyRequest,
} from "../../api/client";

/**
 * Phase 3B, section 5 — the admin side of emergency access.
 *
 * Approving here creates a minimum-privilege, time-limited grant. The duration
 * is clamped by the backend (15 minutes to 24 hours), so a typo in this form
 * cannot hand out an indefinite account.
 */
const STATUS_STYLES = {
  PENDING: "bg-warning text-dark",
  APPROVED: "bg-success",
  REJECTED: "bg-danger",
};

const DURATIONS = [
  { value: 30, label: "30 minutes" },
  { value: 60, label: "1 hour" },
  { value: 120, label: "2 hours" },
  { value: 240, label: "4 hours" },
  { value: 720, label: "12 hours" },
];

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function EmergencyAccessReview() {
  const [requests, setRequests] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [filter, setFilter] = useState("PENDING");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [deciding, setDeciding] = useState(null); // { request, action }
  const [note, setNote] = useState("");
  const [duration, setDuration] = useState(120);
  const [working, setWorking] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await listEmergencyRequests(filter ? { status: filter } : {});
      setRequests(res.data.requests || []);
      setPendingCount(res.data.pending_count || 0);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not load emergency access requests.");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
    // These are time-critical, so refresh while the page is open.
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [load]);

  const decide = async () => {
    if (!deciding) return;
    const { request, action } = deciding;
    setWorking(true);
    setError("");
    try {
      if (action === "approve") {
        await approveEmergencyRequest(request.id, note.trim() || undefined, duration);
        setNotice(
          `Emergency access granted to ${request.full_name}. They can collect it with reference ${request.reference_code}.`
        );
      } else {
        await rejectEmergencyRequest(request.id, note.trim() || undefined);
        setNotice(`Request from ${request.full_name} was rejected.`);
      }
      setDeciding(null);
      setNote("");
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "That decision could not be recorded.");
    } finally {
      setWorking(false);
    }
  };

  return (
    <div>
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div>
          <h4 className="fw-bold mb-1">Emergency Access Requests</h4>
          <p className="text-muted mb-0 small">
            People who are not approved yet but report a live emergency. Approving grants
            minimum, time-limited access only.
          </p>
        </div>
        {pendingCount > 0 && (
          <span className="badge bg-danger fs-6">{pendingCount} awaiting decision</span>
        )}
      </div>

      {error && <div className="alert alert-danger py-2">{error}</div>}
      {notice && (
        <div className="alert alert-success py-2 d-flex justify-content-between align-items-center">
          <span>{notice}</span>
          <button className="btn-close" onClick={() => setNotice("")} aria-label="Dismiss" />
        </div>
      )}

      <div className="btn-group mb-3">
        {[
          { value: "PENDING", label: "Pending" },
          { value: "APPROVED", label: "Approved" },
          { value: "REJECTED", label: "Rejected" },
          { value: "", label: "All" },
        ].map((option) => (
          <button
            key={option.label}
            className={`btn btn-sm ${filter === option.value ? "btn-danger" : "btn-outline-secondary"}`}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {loading && <p className="text-muted">Loading requests...</p>}

      {!loading && requests.length === 0 && (
        <div className="card shadow-sm p-4 text-center text-muted">
          No requests in this view.
        </div>
      )}

      <div className="d-flex flex-column gap-3">
        {requests.map((request) => (
          <div key={request.id} className="card shadow-sm p-3">
            <div className="d-flex flex-wrap justify-content-between align-items-start gap-2">
              <div>
                <h6 className="fw-bold mb-1">
                  {request.full_name}{" "}
                  <span className={`badge ${STATUS_STYLES[request.status] || "bg-secondary"}`}>
                    {request.status}
                  </span>
                </h6>
                <div className="small text-muted">
                  {request.email}
                  {request.contact_number ? ` · ${request.contact_number}` : ""}
                  {request.location ? ` · ${request.location}` : ""}
                </div>
              </div>
              <div className="text-end small text-muted">
                <div>Ref {request.reference_code}</div>
                <div>{formatDate(request.created_at)}</div>
              </div>
            </div>

            <hr className="my-2" />

            <div className="small">
              <div className="mb-1">
                <span className="fw-semibold">Emergency:</span> {request.emergency_description}
              </div>
              <div className="mb-1">
                <span className="fw-semibold">Reason for access:</span> {request.reason}
              </div>
              {request.incident_details && (
                <div className="mb-1">
                  <span className="fw-semibold">Details:</span> {request.incident_details}
                </div>
              )}
            </div>

            {request.status === "PENDING" ? (
              <div className="d-flex gap-2 mt-3">
                <button
                  className="btn btn-success btn-sm"
                  onClick={() => {
                    setDeciding({ request, action: "approve" });
                    setNote("");
                    setDuration(120);
                  }}
                >
                  Grant temporary access
                </button>
                <button
                  className="btn btn-outline-danger btn-sm"
                  onClick={() => {
                    setDeciding({ request, action: "reject" });
                    setNote("");
                  }}
                >
                  Reject
                </button>
              </div>
            ) : (
              <div className="small text-muted mt-2 border-top pt-2">
                Reviewed by {request.reviewed_by_name || "—"} on {formatDate(request.reviewed_at)}
                {request.review_note ? ` · ${request.review_note}` : ""}
                {request.status === "APPROVED" && (
                  <>
                    <div>Access expires: {formatDate(request.access_expires_at)}</div>
                    <div>
                      Collected:{" "}
                      {request.collected_at ? formatDate(request.collected_at) : "not yet"}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ---- decision dialog ---- */}
      {deciding && (
        <div
          className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center"
          style={{ background: "rgba(0,0,0,.5)", zIndex: 2000 }}
        >
          <div className="card shadow-lg p-4" style={{ width: 480, maxWidth: "92vw" }}>
            <h5 className="fw-bold mb-1">
              {deciding.action === "approve" ? "Grant emergency access" : "Reject request"}
            </h5>
            <p className="text-muted small mb-3">
              {deciding.request.full_name} · {deciding.request.email}
            </p>

            {deciding.action === "approve" && (
              <>
                <label className="form-label small fw-semibold">Access duration</label>
                <select
                  className="form-select mb-3"
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                >
                  {DURATIONS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
                <div className="alert alert-info py-2 small">
                  Grants a Student-level account that can report an emergency and follow its
                  own report. It expires automatically and cannot be used to sign in with a
                  password.
                </div>
              </>
            )}

            <label className="form-label small fw-semibold">Note (recorded in the audit log)</label>
            <textarea
              className="form-control mb-3"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={
                deciding.action === "approve"
                  ? "e.g. Verified by phone with campus security."
                  : "e.g. Could not verify the caller."
              }
            />

            <div className="d-flex justify-content-end gap-2">
              <button
                className="btn btn-outline-secondary"
                onClick={() => setDeciding(null)}
                disabled={working}
              >
                Cancel
              </button>
              <button
                className={`btn ${deciding.action === "approve" ? "btn-success" : "btn-danger"}`}
                onClick={decide}
                disabled={working}
              >
                {working ? "Recording..." : deciding.action === "approve" ? "Grant access" : "Reject"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
