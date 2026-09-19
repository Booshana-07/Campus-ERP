import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import { homeRouteFor, STUDENT, FACULTY, ADMIN } from "./roles";

import Login from "./pages/Login";
import Signup from "./pages/Signup";
import EmergencyAccess from "./pages/EmergencyAccess";
import UserManagement from "./pages/admin/UserManagement";
import EmergencyAccessReview from "./pages/admin/EmergencyAccessReview";
import AuditLog from "./pages/admin/AuditLog";
import Dashboard from "./pages/Dashboard";
import Report from "./pages/Report";
import Incidents from "./pages/Incidents";
import MyIncidents from "./pages/MyIncidents";
import IncidentDetail from "./pages/IncidentDetail";
import Teams from "./pages/Teams";
import CampusMap from "./pages/CampusMap";
import Analytics from "./pages/Analytics";
import NotificationsPage from "./pages/Notifications";

/** Phase 2: "/" sends each role to the right landing page. */
function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homeRouteFor(user.role)} replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* Phase 3A: self-registration for Student / Faculty. */}
          <Route path="/signup" element={<Signup />} />
          {/* Phase 3B: public emergency-access request. Grants nothing on its
              own — an administrator must approve it. */}
          <Route path="/emergency-access" element={<EmergencyAccess />} />
          <Route path="/" element={<HomeRedirect />} />

          {/* Admin command centre */}
          <Route
            path="/dashboard"
            element={<ProtectedRoute roles={[ADMIN]}><Dashboard /></ProtectedRoute>}
          />
          <Route
            path="/analytics"
            element={<ProtectedRoute roles={[ADMIN]}><Analytics /></ProtectedRoute>}
          />

          {/* Phase 3B — admin console. The backend enforces ADMIN on every one
              of these APIs as well; these guards are convenience only. */}
          <Route
            path="/admin/users"
            element={<ProtectedRoute roles={[ADMIN]}><UserManagement /></ProtectedRoute>}
          />
          <Route
            path="/admin/emergency-access"
            element={<ProtectedRoute roles={[ADMIN]}><EmergencyAccessReview /></ProtectedRoute>}
          />
          <Route
            path="/admin/audit-log"
            element={<ProtectedRoute roles={[ADMIN]}><AuditLog /></ProtectedRoute>}
          />

          {/* Campus-wide incident queue — staff only */}
          <Route
            path="/incidents"
            element={<ProtectedRoute roles={[ADMIN, FACULTY]}><Incidents /></ProtectedRoute>}
          />

          {/* Everyone can report, and see their own reports */}
          <Route
            path="/report"
            element={<ProtectedRoute roles={[ADMIN, FACULTY, STUDENT]}><Report /></ProtectedRoute>}
          />
          <Route
            path="/my-incidents"
            element={<ProtectedRoute roles={[ADMIN, FACULTY, STUDENT]}><MyIncidents /></ProtectedRoute>}
          />

          {/* Detail page is open to all roles; the backend decides whether this
              particular incident is visible to this particular user. */}
          <Route
            path="/incidents/:id"
            element={<ProtectedRoute><IncidentDetail /></ProtectedRoute>}
          />

          <Route
            path="/teams"
            element={<ProtectedRoute roles={[ADMIN, FACULTY]}><Teams /></ProtectedRoute>}
          />
          <Route path="/map" element={<ProtectedRoute><CampusMap /></ProtectedRoute>} />
          <Route path="/notifications" element={<ProtectedRoute><NotificationsPage /></ProtectedRoute>} />

          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
