import React, { useCallback, useEffect, useState } from "react";
import { getAnalytics } from "../api/client";
import usePolling from "../hooks/usePolling";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, LineChart, Line,
} from "recharts";

const SEVERITY_COLORS = { LOW: "#198754", MEDIUM: "#ffc107", HIGH: "#fd7e14", CRITICAL: "#dc3545" };
const PRIORITY_COLORS = { P1: "#b02a37", P2: "#fd7e14", P3: "#0dcaf0", P4: "#6c757d" };
const STATE_COLORS = { Active: "#fd7e14", Resolved: "#198754" };

/**
 * Phase 2, Feature 9 — analytics.
 *
 * Every figure on this page is computed by the backend from real rows in the
 * SQLite database. Where there is no data yet, the chart is simply empty and
 * the metric shows "No data yet" rather than a made-up number.
 */
export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const res = await getAnalytics();
      setData(res.data);
      setError("");
    } catch (err) {
      setError(
        err.response?.status === 403
          ? "Analytics are available to Admin users only."
          : "Could not load analytics. Is the backend running?"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  usePolling(() => load(false), 15000);

  if (loading) return <div className="text-center py-5">Loading analytics...</div>;
  if (error) return <div className="alert alert-danger">{error}</div>;
  if (!data) return null;

  const noData = data.by_category.length === 0;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <h3 className="fw-bold mb-0">📈 Analytics</h3>
        <button className="btn btn-outline-secondary btn-sm" onClick={() => load(true)}>
          ↻ Refresh
        </button>
      </div>

      <div className="row g-3 mb-4">
        <MetricCard
          label="Avg Time to Assignment"
          minutes={data.avg_time_to_assignment_minutes}
          icon="📨"
          color="primary"
        />
        <MetricCard
          label="Avg Response Time"
          minutes={data.avg_response_time_minutes}
          icon="⏱️"
          color="warning"
        />
        <MetricCard
          label="Avg Resolution Time"
          minutes={data.avg_resolution_time_minutes}
          icon="✅"
          color="success"
        />
      </div>

      {noData ? (
        <div className="card shadow-sm p-5 text-center text-muted">
          No incidents in the database yet — charts will appear as incidents are reported.
        </div>
      ) : (
        <>
          <div className="row g-3 mb-3">
            <ChartCard title="Incidents by Category" col="col-lg-6">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.by_category}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={11} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#dc3545" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Incidents by Severity" col="col-lg-3">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={data.by_severity} dataKey="count" nameKey="name" outerRadius={80} label>
                    {data.by_severity.map((e) => (
                      <Cell key={e.name} fill={SEVERITY_COLORS[e.name] || "#888"} />
                    ))}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Active vs Resolved" col="col-lg-3">
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={data.active_vs_resolved}
                    dataKey="count"
                    nameKey="name"
                    outerRadius={80}
                    label
                  >
                    {data.active_vs_resolved.map((e) => (
                      <Cell key={e.name} fill={STATE_COLORS[e.name] || "#888"} />
                    ))}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="row g-3 mb-3">
            <ChartCard title="Incidents by Priority" col="col-lg-5">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={data.by_priority}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={11} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {data.by_priority.map((e) => (
                      <Cell key={e.name} fill={PRIORITY_COLORS[e.name] || "#888"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Incident Trend (last 7 days)" col="col-lg-7">
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={data.trend_last_7_days}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" fontSize={11} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#dc3545" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="card shadow-sm">
            <div className="card-body">
              <h6 className="card-title">Team Workload</h6>
              <div className="table-responsive">
                <table className="table table-sm align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th>Team</th>
                      <th>Availability</th>
                      <th>Total Assigned</th>
                      <th>Active</th>
                      <th>Resolved</th>
                      <th>Avg Resolution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.team_workload.map((t) => (
                      <tr key={t.team_name}>
                        <td className="fw-semibold">{t.team_name}</td>
                        <td>
                          <span
                            className={`badge ${
                              t.availability === "AVAILABLE" ? "bg-success" : "bg-secondary"
                            }`}
                          >
                            {t.availability}
                          </span>
                        </td>
                        <td>{t.total_assigned}</td>
                        <td>{t.active_assigned}</td>
                        <td>{t.resolved_assigned}</td>
                        <td>
                          {t.avg_resolution_time_minutes != null
                            ? `${t.avg_resolution_time_minutes} min`
                            : <span className="text-muted">No data yet</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function ChartCard({ title, col, children }) {
  return (
    <div className={col}>
      <div className="card shadow-sm h-100">
        <div className="card-body">
          <h6 className="card-title">{title}</h6>
          {children}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, minutes, icon, color }) {
  return (
    <div className="col-md-4">
      <div className={`card stat-card shadow-sm border-${color} h-100`}>
        <div className="card-body d-flex justify-content-between align-items-center">
          <div>
            <div className="text-muted small">{label}</div>
            <div className="fs-4 fw-bold">
              {minutes != null ? `${minutes} min` : <span className="text-muted fs-6">No data yet</span>}
            </div>
          </div>
          <div className="fs-2">{icon}</div>
        </div>
      </div>
    </div>
  );
}
