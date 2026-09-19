import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
});

// ---------------------------------------------------------------------------
// Phase 3A: authenticate every request with the signed session token.
//
// This replaces the Phase 2 `X-User-Email` header, which was not authentication
// at all — anyone could send `X-User-Email: admin@campus.edu` and be treated as
// an administrator. The token below is issued only by /api/auth/login, only
// after a password hash check, and the backend verifies its signature on every
// request.
// ---------------------------------------------------------------------------
const TOKEN_KEY = "campus_emergency_token";
const USER_KEY = "campus_emergency_user";

export function getStoredToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function storeSession(token) {
  try {
    sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage unavailable (private mode) — the session just won't persist */
  }
}

export function clearStoredSession() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// If the session has expired or the account was suspended mid-session, drop the
// stale credentials and send the user back to the login page rather than
// leaving them on a screen full of failed requests.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url || "";
    const isAuthCall = url.includes("/api/auth/login") || url.includes("/api/auth/signup");

    if (status === 401 && !isAuthCall) {
      clearStoredSession();
      if (window.location.pathname !== "/login") {
        window.location.replace("/login?expired=1");
      }
    }
    return Promise.reject(error);
  }
);

// ---- Auth (Phase 3A) ----
export const login = (email, password) =>
  api.post("/api/auth/login", { email, password });

export const signup = (payload) => api.post("/api/auth/signup", payload);

export const getMe = () => api.get("/api/auth/me");

export const logout = () => api.post("/api/auth/logout");

// ---- Admin: user management (Phase 3B) ----
export const listUsers = (params = {}) => api.get("/api/admin/users", { params });
export const listPendingUsers = () => api.get("/api/admin/users/pending");
export const approveUser = (id, reason) => api.post(`/api/admin/users/${id}/approve`, { reason });
export const rejectUser = (id, reason) => api.post(`/api/admin/users/${id}/reject`, { reason });
export const suspendUser = (id, reason) => api.post(`/api/admin/users/${id}/suspend`, { reason });
export const reactivateUser = (id, reason) => api.post(`/api/admin/users/${id}/reactivate`, { reason });

export const listAuditLogs = (params = {}) => api.get("/api/admin/audit-logs", { params });

/** Downloads users.pdf as a blob so the browser can save it. */
export const downloadUsersPdf = () =>
  api.get("/api/admin/users/export/pdf", { responseType: "blob" });

// ---- Emergency access (Phase 3B) ----
// The request + status endpoints are public: someone who is not approved yet
// still needs to be able to report a genuine emergency.
export const requestEmergencyAccess = (payload) =>
  api.post("/api/emergency-access/request", payload);

export const checkEmergencyAccess = (referenceCode, email) =>
  api.get(`/api/emergency-access/status/${encodeURIComponent(referenceCode)}`, {
    params: { email },
  });

export const listEmergencyRequests = (params = {}) =>
  api.get("/api/emergency-access", { params });

export const approveEmergencyRequest = (id, note, duration_minutes) =>
  api.post(`/api/emergency-access/${id}/approve`, { note, duration_minutes });

export const rejectEmergencyRequest = (id, note) =>
  api.post(`/api/emergency-access/${id}/reject`, { note });

// ---- Incidents ----
export const createIncident = (payload) => api.post("/api/incidents", payload);
export const uploadIncidentImage = (file) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/api/incidents/upload-image", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};
export const listIncidents = (params = {}) => api.get("/api/incidents", { params });
export const getIncident = (id) => api.get(`/api/incidents/${id}`);
export const updateIncidentStatus = (id, status, note) =>
  api.put(`/api/incidents/${id}/status`, { status, note });

// Phase 2: assignment can carry an override reason when the admin picks a
// different team from the one the AI recommended.
export const assignTeam = (id, team_id, override_reason) =>
  api.put(`/api/incidents/${id}/assign-team`, { team_id, override_reason });

// Phase I — team assignment history (who was assigned/reassigned, and when)
export const getAssignmentHistory = (id) =>
  api.get(`/api/incidents/${id}/assignment-history`);


export const regenerateRecommendation = (id) =>
  api.post(`/api/incidents/${id}/recommend-team`);
export const regenerateActionPlan = (id) => api.post(`/api/incidents/${id}/action-plan`);

// ---- Teams ----
export const listTeams = () => api.get("/api/teams");

// ---- Dashboard & analytics ----
export const getDashboardStats = () => api.get("/api/dashboard/stats");
export const getAnalytics = () => api.get("/api/dashboard/analytics");

// ---- Notifications (Phase 2) ----
export const getNotifications = (limit = 20) =>
  api.get("/api/notifications", { params: { limit } });
export const markNotificationRead = (id) => api.put(`/api/notifications/${id}/read`);
export const markAllNotificationsRead = () => api.put("/api/notifications/read-all");

// ---- AI ----
export const analyzeDescription = (description, category, location) =>
  api.post("/api/ai/analyze", { description, category, location });

export const API_BASE = API_BASE_URL;

export default api;
