import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getNotifications, markAllNotificationsRead, markNotificationRead } from "../api/client";
import usePolling from "../hooks/usePolling";

const KIND_ICONS = {
  CRITICAL: "🚨",
  ASSIGNED: "🚒",
  STATUS: "🔄",
  RESOLVED: "✅",
  AI: "🤖",
};

export default function NotificationBell() {
  const [data, setData] = useState({ unread_count: 0, notifications: [] });
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const res = await getNotifications(10);
      setData(res.data);
    } catch {
      // Notifications are non-critical — never break the page over them.
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Feature 8: poll every 8 seconds so new alerts appear during the demo.
  usePolling(load, 8000);

  const handleOpenIncident = async (note) => {
    setOpen(false);
    if (!note.is_read) {
      try {
        await markNotificationRead(note.id);
        load();
      } catch {
        /* ignore */
      }
    }
    if (note.incident_id) navigate(`/incidents/${note.incident_id}`);
  };

  const handleMarkAll = async () => {
    try {
      await markAllNotificationsRead();
      load();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="position-relative">
      <button
        className="btn btn-light btn-sm position-relative"
        onClick={() => setOpen((v) => !v)}
        title="Notifications"
      >
        🔔
        {data.unread_count > 0 && (
          <span className="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-danger">
            {data.unread_count > 9 ? "9+" : data.unread_count}
          </span>
        )}
      </button>

      {open && (
        <>
          {/* click-away layer */}
          <div
            style={{ position: "fixed", inset: 0, zIndex: 1040 }}
            onClick={() => setOpen(false)}
          />
          <div
            className="card shadow"
            style={{ position: "absolute", right: 0, top: "110%", width: 340, zIndex: 1050 }}
          >
            <div className="card-header d-flex justify-content-between align-items-center py-2">
              <strong className="small">Notifications</strong>
              <button className="btn btn-link btn-sm p-0" onClick={handleMarkAll}>
                Mark all read
              </button>
            </div>
            <div style={{ maxHeight: 340, overflowY: "auto" }}>
              {data.notifications.length === 0 ? (
                <div className="p-3 text-muted small text-center">Nothing yet.</div>
              ) : (
                data.notifications.map((n) => (
                  <button
                    key={n.id}
                    className="d-block w-100 text-start border-0 border-bottom bg-transparent p-2"
                    style={{ background: n.is_read ? "transparent" : "#fff5f5" }}
                    onClick={() => handleOpenIncident(n)}
                  >
                    <div className="small fw-semibold">
                      {KIND_ICONS[n.kind] || "🔔"} {n.title}
                    </div>
                    <div className="small text-muted">{n.message}</div>
                    <div className="text-muted" style={{ fontSize: "0.7rem" }}>
                      {new Date(n.created_at).toLocaleString()}
                    </div>
                  </button>
                ))
              )}
            </div>
            <div className="card-footer py-1 text-center">
              <button
                className="btn btn-link btn-sm"
                onClick={() => {
                  setOpen(false);
                  navigate("/notifications");
                }}
              >
                View all
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
