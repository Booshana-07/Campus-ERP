import React from "react";
import { Navigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Layout from "./Layout";
import { homeRouteFor } from "../roles";

/**
 * Phase 2: the guard now takes a list of allowed roles.
 *
 * `adminOnly` from Phase 1 still works, so nothing that used it breaks.
 * Remember this is convenience only — the backend checks roles too.
 */
export default function ProtectedRoute({ children, adminOnly = false, roles = null }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const allowed = roles || (adminOnly ? ["ADMIN"] : null);

  if (allowed && !allowed.includes(user.role)) {
    return (
      <Layout>
        <div className="card shadow-sm p-4 text-center" style={{ maxWidth: 520, margin: "3rem auto" }}>
          <div className="fs-1">🔒</div>
          <h5 className="fw-bold mt-2">This page isn't available to your role</h5>
          <p className="text-muted mb-3">
            You are signed in as <strong>{user.role}</strong>. This section is limited to{" "}
            {allowed.join(" and ")} users.
          </p>
          <Link className="btn btn-danger" to={homeRouteFor(user.role)}>
            Go to my home page
          </Link>
        </div>
      </Layout>
    );
  }

  return <Layout>{children}</Layout>;
}
