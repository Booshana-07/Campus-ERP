import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveUser,
  downloadUsersPdf,
  listUsers,
  reactivateUser,
  rejectUser,
  suspendUser,
} from "../../api/client";

/**
 * Phase 3B, section 1 — the admin user console.
 *
 * Everything here is a convenience layer. The backend independently enforces
 * that only an ADMIN can call these endpoints, so removing the `disabled`
 * attribute in dev tools achieves nothing.
 */
const STATUS_STYLES = {
  APPROVED: "bg-success",
  PENDING: "bg-warning text-dark",
  REJECTED: "bg-danger",
  SUSPENDED: "bg-secondary",
};

const ROLE_STYLES = {
  ADMIN: "bg-danger",
  FACULTY: "bg-warning text-dark",
  STUDENT: "bg-info text-dark",
};

// Which buttons make sense for an account in each state.
const ACTIONS_FOR = {
  PENDING: ["approve", "reject"],
  APPROVED: ["suspend"],
  REJECTED: ["reactivate"],
  SUSPENDED: ["reactivate", "reject"],
};

const ACTION_LABELS = {
  approve: { label: "Approve", className: "btn-success" },
  reject: { label: "Reject", className: "btn-outline-danger" },
  suspend: { label: "Suspend", className: "btn-outline-secondary" },
  reactivate: { label: "Reactivate", className: "btn-success" },
};

const ACTION_FNS = {
  approve: approveUser,
  reject: rejectUser,
  suspend: suspendUser,
  reactivate: reactivateUser,
};

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");

  // The action awaiting confirmation: { user, action }
  const [confirming, setConfirming] = useState(null);
  const [reason, setReason] = useState("");
  const [working, setWorking] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const params = {};
      if (search.trim()) params.q = search.trim();
      if (statusFilter) params.status = statusFilter;
      if (roleFilter) params.role = roleFilter;
      const res = await listUsers(params);
      setUsers(res.data.users || []);
      setPendingCount(res.data.pending_count || 0);
    } catch (err) {
      setError(
        err.response?.data?.detail || "Could not load users. Is the backend running?"
      );
    } finally {
      setLoading(false);
    }
  }, [search, statusFilter, roleFilter]);

  // Debounce the search box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
  }, [load]);

  const runAction = async () => {
    if (!confirming) return;
    const { user, action } = confirming;
    setWorking(true);
    setError("");
    try {
      await ACTION_FNS[action](user.id, reason.trim() || undefined);
      setNotice(`${user.name} — ${ACTION_LABELS[action].label.toLowerCase()}d.`);
      setConfirming(null);
      setReason("");
      await load();
    } catch (err) {
      setError(err.response?.data?.detail || "That action could not be completed.");
    } finally {
      setWorking(false);
    }
  };

  const handleExport = async () => {
    setError("");
    try {
      const res = await downloadUsersPdf();
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", "users.pdf");
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(
        err.response?.status === 503
          ? "PDF export needs the reportlab package on the backend (pip install -r requirements.txt)."
          : "Could not generate users.pdf."
      );
    }
  };

  const counts = useMemo(() => {
    const out = {};
    users.forEach((u) => {
      out[u.status] = (out[u.status] || 0) + 1;
    });
    return out;
  }, [users]);

  return (
    <div>
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <div>
          <h4 className="fw-bold mb-1">User Management</h4>
          <p className="text-muted mb-0 small">
            Approve, reject, suspend and reactivate campus accounts.
          </p>
        </div>
        <div className="d-flex gap-2">
          {pendingCount > 0 && (
            <span className="badge bg-warning text-dark align-self-center">
              {pendingCount} awaiting review
            </span>
          )}
          <button className="btn btn-outline-dark btn-sm" onClick={handleExport}>
            ⬇ Export users.pdf
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger py-2">{error}</div>}
      {notice && (
        <div className="alert alert-success py-2 d-flex justify-content-between align-items-center">
          <span>{notice}</span>
          <button className="btn-close" onClick={() => setNotice("")} aria-label="Dismiss" />
        </div>
      )}

      {/* ---- filters ---- */}
      <div className="card shadow-sm p-3 mb-3">
        <div className="row g-2">
          <div className="col-12 col-md-6">
            <input
              className="form-control"
              placeholder="Search by name or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="col-6 col-md-3">
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All statuses</option>
              <option value="PENDING">Pending</option>
              <option value="APPROVED">Approved</option>
              <option value="REJECTED">Rejected</option>
              <option value="SUSPENDED">Suspended</option>
            </select>
          </div>
          <div className="col-6 col-md-3">
            <select
              className="form-select"
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
            >
              <option value="">All roles</option>
              <option value="STUDENT">Student</option>
              <option value="FACULTY">Faculty</option>
              <option value="ADMIN">Admin</option>
            </select>
          </div>
        </div>
        {!loading && (
          <div className="small text-muted mt-2">
            Showing {users.length} account{users.length === 1 ? "" : "s"}
            {Object.keys(counts).length > 0 && (
              <>
                {" — "}
                {Object.entries(counts)
                  .map(([status, n]) => `${n} ${status.toLowerCase()}`)
                  .join(", ")}
              </>
            )}
          </div>
        )}
      </div>

      {/* ---- table ---- */}
      <div className="card shadow-sm">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Registered</th>
                <th>Last review</th>
                <th className="text-end">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={7} className="text-center text-muted py-4">
                    Loading users...
                  </td>
                </tr>
              )}

              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center text-muted py-4">
                    No accounts match these filters.
                  </td>
                </tr>
              )}

              {!loading &&
                users.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <div className="fw-semibold">{user.name}</div>
                      {user.is_emergency_access && (
                        <span className="badge bg-danger-subtle text-danger-emphasis border border-danger-subtle">
                          ⏱ Temporary emergency access
                        </span>
                      )}
                      {user.incident_count > 0 && (
                        <div className="small text-muted">
                          {user.incident_count} report{user.incident_count === 1 ? "" : "s"}
                        </div>
                      )}
                    </td>
                    <td className="small">{user.email}</td>
                    <td>
                      <span className={`badge ${ROLE_STYLES[user.role] || "bg-secondary"}`}>
                        {user.role}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${STATUS_STYLES[user.status] || "bg-secondary"}`}>
                        {user.status}
                      </span>
                      {user.status_reason && (
                        <div className="small text-muted mt-1">{user.status_reason}</div>
                      )}
                    </td>
                    <td className="small text-muted">{formatDate(user.created_at)}</td>
                    <td className="small text-muted">
                      {user.status_changed_at ? (
                        <>
                          {formatDate(user.status_changed_at)}
                          {user.status_changed_by_name && (
                            <div>by {user.status_changed_by_name}</div>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="text-end">
                      {user.role === "ADMIN" ? (
                        <span className="small text-muted">Managed internally</span>
                      ) : (
                        <div className="d-inline-flex gap-1 flex-wrap justify-content-end">
                          {(ACTIONS_FOR[user.status] || []).map((action) => (
                            <button
                              key={action}
                              className={`btn btn-sm ${ACTION_LABELS[action].className}`}
                              onClick={() => {
                                setConfirming({ user, action });
                                setReason("");
                              }}
                            >
                              {ACTION_LABELS[action].label}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ---- confirmation ---- */}
      {confirming && (
        <div
          className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center"
          style={{ background: "rgba(0,0,0,.5)", zIndex: 2000 }}
        >
          <div className="card shadow-lg p-4" style={{ width: 460, maxWidth: "92vw" }}>
            <h5 className="fw-bold mb-1">
              {ACTION_LABELS[confirming.action].label} {confirming.user.name}?
            </h5>
            <p className="text-muted small">
              {confirming.user.email} · {confirming.user.role}
            </p>

            <label className="form-label small fw-semibold">
              Reason {confirming.action === "approve" ? "(optional)" : "(recommended)"}
            </label>
            <textarea
              className="form-control mb-3"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Recorded in the audit log and shown to the user."
            />

            <div className="d-flex justify-content-end gap-2">
              <button
                className="btn btn-outline-secondary"
                onClick={() => setConfirming(null)}
                disabled={working}
              >
                Cancel
              </button>
              <button
                className={`btn ${ACTION_LABELS[confirming.action].className.replace("btn-outline-", "btn-")}`}
                onClick={runAction}
                disabled={working}
              >
                {working ? "Working..." : `Confirm ${ACTION_LABELS[confirming.action].label.toLowerCase()}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
