/**
 * Phase 2, Feature 1 — one place that describes what each role can see.
 *
 * This drives the sidebar and the route guards. It is the *convenience* half of
 * role-based access: the real enforcement happens in the FastAPI backend
 * (app/deps.py), so hiding a link here is never the only thing stopping a
 * student from performing an admin action.
 */

export const STUDENT = "STUDENT";
export const FACULTY = "FACULTY";
export const ADMIN = "ADMIN";

export const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "📊", roles: [ADMIN] },
  { to: "/my-incidents", label: "My Incidents", icon: "🧾", roles: [STUDENT, FACULTY] },
  { to: "/report", label: "Report Emergency", icon: "🚨", roles: [STUDENT, FACULTY, ADMIN] },
  { to: "/incidents", label: "Priority Queue", icon: "📋", roles: [FACULTY, ADMIN] },
  { to: "/analytics", label: "Analytics", icon: "📈", roles: [ADMIN] },
  { to: "/admin/users", label: "User Management", icon: "👤", roles: [ADMIN] },
  { to: "/admin/emergency-access", label: "Emergency Access", icon: "🚨", roles: [ADMIN] },
  { to: "/admin/audit-log", label: "Audit Log", icon: "🧾", roles: [ADMIN] },
  { to: "/teams", label: "Response Teams", icon: "👥", roles: [FACULTY, ADMIN] },
  { to: "/map", label: "Campus Map", icon: "🗺️", roles: [STUDENT, FACULTY, ADMIN] },
  { to: "/notifications", label: "Notifications", icon: "🔔", roles: [STUDENT, FACULTY, ADMIN] },
];

/** Where a role lands after login. */
export function homeRouteFor(role) {
  if (role === ADMIN) return "/dashboard";
  if (role === FACULTY) return "/incidents";
  return "/my-incidents";
}

/**
 * Phase 3B: a temporary emergency-access account is limited to reporting an
 * emergency and following its own report. The backend refuses the rest
 * (require_permanent_account), so hiding these is only to avoid showing links
 * that would fail — it is not the security control.
 */
const EMERGENCY_ALLOWED = ["/report", "/my-incidents", "/notifications"];

export function navItemsFor(role, user = null) {
  const items = NAV_ITEMS.filter((item) => item.roles.includes(role));
  if (user?.is_emergency_access) {
    return items.filter((item) => EMERGENCY_ALLOWED.includes(item.to));
  }
  return items;
}

export function isAdmin(user) {
  return user?.role === ADMIN;
}
