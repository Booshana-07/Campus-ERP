import React, { useCallback, useEffect, useState } from "react";
import { listAuditLogs } from "../../api/client";

/**
 * Phase 3B, section 6 — a read-only view of the audit trail.
 *
 * There is deliberately no edit or delete control here, and no backend endpoint
 * behind one: the log is append-only.
 */
const ACTION_META = {
  USER_REGISTERED: { label: "Registered", icon: "📝", className: "bg-info text-dark" },
  USER_APPROVED: { label: "Approved", icon: "✅", className: "bg-success" },
  USER_REJECTED: { label: "Rejected", icon: "⛔", className: "bg-danger" },
  USER_SUSPENDED: { label: "Suspended", icon: "⏸", className: "bg-secondary" },
  USER_REACTIVATED: { label: "Reactivated", icon: "🔄", className: "bg-success" },
  LOGIN_SUCCESS: { label: "Signed in", icon: "🔓", className: "bg-light text-dark border" },
  LOGIN_BLOCKED: { label: "Sign-in blocked", icon: "🚫", className: "bg-warning text-dark" },
  EMERGENCY_ACCESS_REQUESTED: { label: "Emergency request", icon: "🚨", className: "bg-danger" },
  EMERGENCY_ACCESS_APPROVED: { label: "Emergency granted", icon: "🔑", className: "bg-success" },
  EMERGENCY_ACCESS_REJECTED: { label: "Emergency denied", icon: "⛔", className: "bg-danger" },
  EMERGENCY_ACCESS_USED: { label: "Emergency access used", icon: "▶", className: "bg-dark" },
  USERS_EXPORTED: { label: "Users exported", icon: "⬇", className: "bg-light text-dark border" },
};

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function AuditLog() {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await listAuditLogs(action ? { action } : {});
      setEntries(res.data.entries || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not load the audit log.");
    } finally {
      setLoading(false);
    }
  }, [action]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="mb-3">
        <h4 className="fw-bold mb-1">Audit Log</h4>
        <p className="text-muted mb-0 small">
          Append-only record of security-sensitive events. {total} entr
          {total === 1 ? "y" : "ies"} recorded.
        </p>
      </div>

      {error && <div className="alert alert-danger py-2">{error}</div>}

      <div className="card shadow-sm p-3 mb-3">
        <label className="form-label small fw-semibold">Filter by event</label>
        <select
          className="form-select"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          style={{ maxWidth: 360 }}
        >
          <option value="">All events</option>
          {Object.entries(ACTION_META).map(([key, meta]) => (
            <option key={key} value={key}>
              {meta.label}
            </option>
          ))}
        </select>
      </div>

      <div className="card shadow-sm">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th>When</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Target</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={5} className="text-center text-muted py-4">
                    Loading audit log...
                  </td>
                </tr>
              )}

              {!loading && entries.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center text-muted py-4">
                    No entries for this filter.
                  </td>
                </tr>
              )}

              {!loading &&
                entries.map((entry) => {
                  const meta = ACTION_META[entry.action] || {
                    label: entry.action,
                    icon: "•",
                    className: "bg-secondary",
                  };
                  return (
                    <tr key={entry.id}>
                      <td className="small text-muted" style={{ whiteSpace: "nowrap" }}>
                        {formatDate(entry.timestamp)}
                      </td>
                      <td className="small">
                        <div className="fw-semibold">{entry.actor_name}</div>
                        <div className="text-muted">{entry.actor_role}</div>
                      </td>
                      <td>
                        <span className={`badge ${meta.className}`}>
                          {meta.icon} {meta.label}
                        </span>
                      </td>
                      <td className="small">
                        {entry.target_label || "—"}
                        {entry.target_type && (
                          <div className="text-muted">{entry.target_type}</div>
                        )}
                      </td>
                      <td className="small text-muted" style={{ maxWidth: 420 }}>
                        {entry.details || "—"}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
