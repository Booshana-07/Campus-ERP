import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getNotifications, markAllNotificationsRead, markNotificationRead } from "../api/client";
import usePolling from "../hooks/usePolling";

const KIND_STYLES = {
  CRITICAL: { icon: "🚨", color: "#dc3545", label: "Critical" },
  ASSIGNED: { icon: "🚒", color: "#0d6efd", label: "Assignment" },
  STATUS: { icon: "🔄", color: "#6c757d", label: "Status" },
  RESOLVED: { icon: "✅", color: "#198754", label: "Resolved" },
  AI: { icon: "🤖", color: "#6f42c1", label: "AI" },
};

export default function NotificationsPage() {
  const [data, setData] = useState({ unread_count: 0, notifications: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const res = await getNotifications(50);
      setData(res.data);
      setError("");
    } catch {
      setError("Could not load notifications. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  usePolling(() => load(false), 10000);

  const open = async (note) => {
    if (!note.is_read) {
      try {
        await markNotificationRead(note.id);
      } catch {
        /* ignore */
      }
    }
    if (note.incident_id) navigate(`/incidents/${note.incident_id}`);
    else load(false);
  };

  if (loading) return <div className="text-center py-5">Loading notifications...</div>;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h3 className="fw-bold mb-0">
          🔔 Notifications{" "}
          {data.unread_count > 0 && (
            <span className="badge bg-danger align-middle">{data.unread_count} new</span>
          )}
        </h3>
        <div className="d-flex gap-2">
          <button className="btn btn-outline-secondary btn-sm" onClick={() => load(true)}>
            ↻ Refresh
          </button>
          <button
            className="btn btn-outline-danger btn-sm"
            disabled={data.unread_count === 0}
            onClick={async () => {
              await markAllNotificationsRead();
              load(true);
            }}
          >
            Mark all read
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body p-0">
          {data.notifications.length === 0 ? (
            <div className="text-center py-5 text-muted">No notifications yet.</div>
          ) : (
            <ul className="list-group list-group-flush">
              {data.notifications.map((n) => {
                const style = KIND_STYLES[n.kind] || KIND_STYLES.STATUS;
                return (
                  <li
                    key={n.id}
                    className="list-group-item d-flex gap-3 align-items-start"
                    style={{
                      cursor: n.incident_id ? "pointer" : "default",
                      background: n.is_read ? undefined : "#fff7f7",
                    }}
                    onClick={() => open(n)}
                  >
                    <div className="fs-4">{style.icon}</div>
                    <div className="flex-grow-1">
                      <div className="d-flex gap-2 align-items-center flex-wrap">
                        <strong>{n.title}</strong>
                        <span
                          className="badge"
                          style={{ backgroundColor: style.color, fontSize: "0.65rem" }}
                        >
                          {style.label}
                        </span>
                        {!n.is_read && <span className="badge bg-danger" style={{ fontSize: "0.65rem" }}>NEW</span>}
                      </div>
                      <div className="text-muted small">{n.message}</div>
                      <div className="text-muted" style={{ fontSize: "0.72rem" }}>
                        {new Date(n.created_at).toLocaleString()}
                        {n.incident_id ? ` · Incident #${n.incident_id}` : ""}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
