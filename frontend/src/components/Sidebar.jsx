import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { logout as logoutRequest } from "../api/client";
import { navItemsFor } from "../roles";

const ROLE_COLORS = {
  STUDENT: "#0dcaf0",
  FACULTY: "#ffc107",
  ADMIN: "#dc3545",
};

export default function Sidebar() {
  const { user, logoutUser } = useAuth();
  const navigate = useNavigate();

  // Phase 3A: tell the backend the session is over, then clear the token
  // locally. The local clear happens either way — if the server is unreachable
  // the user must still end up signed out on this device.
  const handleLogout = async () => {
    try {
      await logoutRequest();
    } catch {
      /* session already invalid or server unreachable — sign out regardless */
    } finally {
      logoutUser();
      navigate("/login", { replace: true });
    }
  };

  // Phase 2: the menu is built from the role, so a student never sees admin pages.
  // Phase 3B: temporary emergency accounts get a further-reduced menu.
  const items = navItemsFor(user?.role, user);

  return (
    <div
      className="d-flex flex-column p-3 text-white"
      style={{
        width: 240,
        minWidth: 240,
        position: "sticky",
        top: 0,
        height: "100vh",
        background: "linear-gradient(180deg,#171a2b,#111322)",
      }}
    >
      <div className="mb-4">
        <h5 className="mb-0">🎓 Campus ERP</h5>
        <small className="text-white-50">Emergency Response</small>
      </div>

      <nav className="nav nav-pills flex-column mb-auto gap-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              "nav-link text-white d-flex align-items-center gap-2" +
              (isActive ? " active bg-danger" : "")
            }
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <hr className="text-white-50" />

      {user && (
        <div className="mb-2">
          <div className="fw-semibold small">{user.name}</div>
          <span
            className="badge"
            style={{
              backgroundColor: ROLE_COLORS[user.role] || "#6c757d",
              color: user.role === "FACULTY" ? "#212529" : "#fff",
            }}
          >
            {user.role}
          </span>
          {user.is_emergency_access && (
            <div className="mt-2">
              <span className="badge bg-danger">⏱ Temporary access</span>
            </div>
          )}
        </div>
      )}
      <button className="btn btn-outline-light btn-sm mt-2" onClick={handleLogout}>
        Logout
      </button>
    </div>
  );
}
