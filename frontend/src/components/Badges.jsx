import React from "react";

// Phase 2 polish: every badge now renders through one small helper so the
// colours for P1..P4 / LOW..CRITICAL / REPORTED..RESOLVED are consistent
// everywhere in the app. (Phase 1's HIGH severity badge produced an empty
// "bg-" class — fixed here.)

const SEVERITY_STYLES = {
  LOW: { bg: "#198754", label: "LOW" },
  MEDIUM: { bg: "#ffc107", label: "MEDIUM", dark: true },
  HIGH: { bg: "#fd7e14", label: "HIGH" },
  CRITICAL: { bg: "#dc3545", label: "CRITICAL" },
};

const PRIORITY_STYLES = {
  P1: { bg: "#b02a37", title: "P1 — respond immediately" },
  P2: { bg: "#fd7e14", title: "P2 — respond urgently" },
  P3: { bg: "#0dcaf0", title: "P3 — respond soon", dark: true },
  P4: { bg: "#6c757d", title: "P4 — routine" },
};

const STATUS_STYLES = {
  REPORTED: { bg: "#6c757d" },
  ANALYZED: { bg: "#0dcaf0", dark: true },
  ASSIGNED: { bg: "#0d6efd" },
  RESPONDING: { bg: "#ffc107", dark: true },
  RESOLVED: { bg: "#198754" },
};

function Pill({ style, children, title }) {
  return (
    <span
      className="badge"
      title={title}
      style={{
        backgroundColor: style?.bg || "#6c757d",
        color: style?.dark ? "#212529" : "#fff",
        fontWeight: 600,
        letterSpacing: "0.02em",
      }}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }) {
  if (!severity) return <Pill>UNKNOWN</Pill>;
  return <Pill style={SEVERITY_STYLES[severity]}>{severity}</Pill>;
}

export function StatusBadge({ status }) {
  return <Pill style={STATUS_STYLES[status]}>{status || "—"}</Pill>;
}

export function PriorityBadge({ priority }) {
  if (!priority) return <Pill>—</Pill>;
  const style = PRIORITY_STYLES[priority];
  return (
    <Pill style={style} title={style?.title}>
      {priority}
    </Pill>
  );
}

/** Small coloured risk number used in tables and headers. */
export function RiskScore({ score, size = "1rem" }) {
  if (score === null || score === undefined) return <span className="text-muted">—</span>;
  let color = "#198754";
  if (score >= 85) color = "#dc3545";
  else if (score >= 65) color = "#fd7e14";
  else if (score >= 45) color = "#ffc107";
  return (
    <span style={{ color, fontWeight: 700, fontSize: size }}>{score}</span>
  );
}
