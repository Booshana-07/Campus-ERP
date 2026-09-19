import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getDashboardStats, listIncidents } from "../api/client";
import { SeverityBadge, StatusBadge, PriorityBadge, RiskScore } from "../components/Badges";
import usePolling from "../hooks/usePolling";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";

const SEVERITY_PIE_COLORS = { LOW: "#198754", MEDIUM: "#ffc107", HIGH: "#fd7e14", CRITICAL: "#dc3545" };

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const navigate = useNavigate();

  const loadData = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const [statsRes, incidentsRes] = await Promise.all([
        getDashboardStats(),
        // Phase 2, Feature 4: the dashboard now uses the smart priority queue.
        listIncidents({ smart_queue: true }),
      ]);
      setStats(statsRes.data);
      setIncidents(incidentsRes.data);
      setLastUpdated(new Date());
      setError("");
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "The command dashboard is available to Faculty and Admin users only."
          : "Could not load dashboard data. Is the backend running?"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(true);
  }, [loadData]);

  // Feature 8: auto-refresh so the dashboard moves on its own during the demo.
  usePolling(() => loadData(false), 10000);

  if (loading) return <div className="text-center py-5">Loading dashboard...</div>;
  if (error) return <div className="alert alert-danger">{error}</div>;

  const criticalIncidents = incidents.filter((i) => i.severity === "CRITICAL" && i.status !== "RESOLVED");
  const queue = incidents.filter((i) => i.status !== "RESOLVED").slice(0, 6);

  // Chart data: incidents by category
  const typeCounts = {};
  incidents.forEach((i) => {
    const t = i.incident_type || "OTHER";
    typeCounts[t] = (typeCounts[t] || 0) + 1;
  });
  const typeChartData = Object.entries(typeCounts).map(([name, count]) => ({ name, count }));

  // Chart data: severity distribution
  const severityCounts = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
  incidents.forEach((i) => {
    if (i.severity && severityCounts[i.severity] !== undefined) severityCounts[i.severity]++;
  });
  const severityChartData = Object.entries(severityCounts)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }));

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
        <div>
          <h3 className="fw-bold mb-0">🚨 Emergency Command Dashboard</h3>
          {lastUpdated && (
            <small className="text-muted">
              Live · auto-refreshes every 10s · updated {lastUpdated.toLocaleTimeString()}
            </small>
          )}
        </div>
        <div className="d-flex gap-2">
          <Link to="/analytics" className="btn btn-outline-danger btn-sm">
            📈 Analytics
          </Link>
          <button className="btn btn-outline-secondary btn-sm" onClick={() => loadData(true)}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {criticalIncidents.length > 0 && (
        <div className="alert alert-danger d-flex align-items-center mb-4 flex-wrap gap-2">
          <strong className="me-2">
            ⚠️ {criticalIncidents.length} CRITICAL incident(s) require immediate attention!
          </strong>
          <Link to="/incidents?severity=CRITICAL" className="ms-auto btn btn-sm btn-danger">
            View Critical
          </Link>
        </div>
      )}

      {/* Stat cards */}
      <div className="row g-3 mb-4">
        <StatCard label="Total Incidents" value={stats.total_incidents} color="primary" icon="📋" />
        <StatCard label="Critical Incidents" value={stats.critical_incidents} color="danger" icon="🔥" />
        <StatCard label="Active Incidents" value={stats.active_incidents} color="warning" icon="⏳" />
        <StatCard label="Resolved Incidents" value={stats.resolved_incidents} color="success" icon="✅" />
      </div>

      {/* Phase 2, Feature 6 — real response metrics, calculated from status history */}
      <div className="row g-3 mb-4">
        <TimeCard
          label="Avg Time to Assignment"
          minutes={stats.avg_time_to_assignment_minutes}
          sample={stats.assignment_sample_size}
          icon="📨"
          color="primary"
        />
        <TimeCard
          label="Avg Response Time"
          minutes={stats.avg_response_time_minutes}
          sample={stats.response_sample_size}
          icon="⏱️"
          color="info"
        />
        <TimeCard
          label="Avg Resolution Time"
          minutes={stats.avg_resolution_time_minutes}
          sample={stats.resolution_sample_size}
          icon="🏁"
          color="success"
        />
      </div>

      <div className="row g-3 mb-4">
        <div className="col-md-7">
          <div className="card shadow-sm h-100">
            <div className="card-body">
              <h6 className="card-title">Incidents by Category</h6>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={typeChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#dc3545" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
        <div className="col-md-5">
          <div className="card shadow-sm h-100">
            <div className="card-body">
              <h6 className="card-title">Severity Distribution</h6>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={severityChartData} dataKey="value" nameKey="name" outerRadius={90} label>
                    {severityChartData.map((entry) => (
                      <Cell key={entry.name} fill={SEVERITY_PIE_COLORS[entry.name] || "#888"} />
                    ))}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>

      <div className="card shadow-sm">
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
            <div>
              <h6 className="card-title mb-0">🧠 Smart Priority Queue</h6>
              <small className="text-muted">
                P1 first, then by risk score — the order teams should work in.
              </small>
            </div>
            <Link to="/incidents" className="btn btn-sm btn-outline-danger">
              View All Incidents
            </Link>
          </div>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>#</th>
                  <th>ID</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Risk</th>
                  <th>Priority</th>
                  <th>Location</th>
                  <th>Team</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {queue.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-center text-muted py-4">
                      No active incidents — everything is resolved. 🎉
                    </td>
                  </tr>
                ) : (
                  queue.map((inc, idx) => (
                    <tr
                      key={inc.id}
                      className={`row-${(inc.priority || "p4").toLowerCase()}`}
                      style={{ cursor: "pointer" }}
                      onClick={() => navigate(`/incidents/${inc.id}`)}
                    >
                      <td className="text-muted fw-bold">{idx + 1}</td>
                      <td>#{inc.id}</td>
                      <td>{inc.incident_type || "—"}</td>
                      <td><SeverityBadge severity={inc.severity} /></td>
                      <td><RiskScore score={inc.risk_score} /></td>
                      <td><PriorityBadge priority={inc.priority} /></td>
                      <td>{inc.location}</td>
                      <td className="small">
                        {inc.assigned_team_name || (
                          <span className="text-muted">
                            {inc.recommended_team_name ? `🤖 ${inc.recommended_team_name}` : "Unassigned"}
                          </span>
                        )}
                      </td>
                      <td><StatusBadge status={inc.status} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color, icon }) {
  return (
    <div className="col-6 col-md-3">
      <div className={`card stat-card shadow-sm border-${color} h-100`}>
        <div className="card-body d-flex justify-content-between align-items-center">
          <div>
            <div className="text-muted small">{label}</div>
            <div className="fs-4 fw-bold">{value}</div>
          </div>
          <div className="fs-2">{icon}</div>
        </div>
      </div>
    </div>
  );
}

/** Response-time card. Shows "No data yet" instead of inventing a number. */
function TimeCard({ label, minutes, sample, color, icon }) {
  return (
    <div className="col-md-4">
      <div className={`card stat-card shadow-sm border-${color} h-100`}>
        <div className="card-body d-flex justify-content-between align-items-center">
          <div>
            <div className="text-muted small">{label}</div>
            {minutes != null ? (
              <>
                <div className="fs-4 fw-bold">{minutes} min</div>
                <div className="text-muted" style={{ fontSize: "0.72rem" }}>
                  from {sample} incident{sample === 1 ? "" : "s"}
                </div>
              </>
            ) : (
              <>
                <div className="fs-6 fw-bold text-muted">No data yet</div>
                <div className="text-muted" style={{ fontSize: "0.72rem" }}>
                  needs a completed incident
                </div>
              </>
            )}
          </div>
          <div className="fs-2">{icon}</div>
        </div>
      </div>
    </div>
  );
}
