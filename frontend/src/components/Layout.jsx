import React from "react";
import Sidebar from "./Sidebar";
import NotificationBell from "./NotificationBell";
import { useAuth } from "../context/AuthContext";

export default function Layout({ children }) {
  const { user } = useAuth();

  return (
    <div className="d-flex">
      <Sidebar />
      <div className="flex-grow-1" style={{ backgroundColor: "#f5f6fa", minHeight: "100vh" }}>
        {/* Phase 2: slim top bar carrying the notification centre (Feature 7). */}
        <div
          className="d-flex justify-content-end align-items-center gap-3 px-4 py-2 bg-white border-bottom"
          style={{ position: "sticky", top: 0, zIndex: 1030 }}
        >
          <span className="small text-muted d-none d-sm-inline">
            Signed in as <strong>{user?.name}</strong> ({user?.role})
          </span>
          <NotificationBell />
        </div>

        {/* Phase 3B: make a temporary emergency grant visible and its expiry
            obvious, so nobody is surprised when access stops working. */}
        {user?.is_emergency_access && (
          <div className="alert alert-danger rounded-0 border-0 mb-0 py-2 px-4 small">
            <strong>Temporary emergency access.</strong> You can report an emergency and
            follow your own report.
            {user.access_expires_at && (
              <> This access expires at {new Date(user.access_expires_at).toLocaleString()}.</>
            )}
          </div>
        )}

        <div className="p-3 p-md-4">{children}</div>
      </div>
    </div>
  );
}
