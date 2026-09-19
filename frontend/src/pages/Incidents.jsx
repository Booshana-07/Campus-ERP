import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { listIncidents } from "../api/client";
import { SeverityBadge, StatusBadge, PriorityBadge, RiskScore } from "../components/Badges";
import usePolling from "../hooks/usePolling";

const CATEGORIES = ["MEDICAL", "FIRE", "ACCIDENT", "SECURITY", "ELECTRICAL", "INFRASTRUCTURE", "OTHER"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const STATUSES = ["REPORTED", "ANALYZED", "ASSIGNED", "RESPONDING", "RESOLVED"];
const PRIORITIES = ["P1", "P2", "P3", "P4"];

// Phase 2, Feature 4: three ordering modes. Smart queue is the default because
// it is the one that matters in an emergency; the two Phase 1 orders are kept.
const SORT_MODES = [
  { key: "smart", label: "🧠 Smart priority queue" },
  { key: "risk", label: "Risk score (high → low)" },
  { key: "newest", label: "Newest first" },
];

export default function Incidents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sortMode, setSortMode] = useState("smart");
  const navigate = useNavigate();

  const filters = {
    incident_type: searchParams.get("incident_type") || "",
    severity: searchParams.get("severity") || "",
    status: searchParams.get("status") || "",
    priority: searchParams.get("priority") || "",
  };

  const loadIncidents = useCallback(
    async (showSpinner = true) => {
      if (showSpinner) setLoading(true);
      try {
        const params = {};
        Object.entries(filters).forEach(([k, v]) => {
          if (v) params[k] = v;
        });
        if (sortMode === "smart") params.smart_queue = true;
        if (sortMode === "risk") params.sort_by_risk = true;
        const res = await listIncidents(params);
        setIncidents(res.data);
        setError("");
      } catch (err) {
        setError(
          err.response?.status === 403
            ? "This incident queue is available to Faculty and Admin users only."
            : "Could not load incidents. Is the backend running?"
        );
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [searchParams, sortMode]
  );

  useEffect(() => {
    loadIncidents(true);
  }, [loadIncidents]);

  // Feature 8: keep the queue fresh without a manual refresh.
  usePolling(() => loadIncidents(false), 10000);

  const updateFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  const clearFilters = () => setSearchParams({});

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
        <div>
          <h3 className="fw-bold mb-0">📋 Incident Queue</h3>
          <small className="text-muted">
            {sortMode === "smart"
              ? "Ordered P1 → P4, then by risk score. Resolved incidents sit at the bottom."
              : "Custom ordering"}
          </small>
        </div>
        <button className="btn btn-outline-secondary btn-sm" onClick={() => loadIncidents(true)}>
          ↻ Refresh
        </button>
      </div>

      <div className="card shadow-sm mb-3 p-3">
        <div className="row g-2 align-items-end">
          <FilterSelect label="Type" options={CATEGORIES} value={filters.incident_type} onChange={(v) => updateFilter("incident_type", v)} />
          <FilterSelect label="Severity" options={SEVERITIES} value={filters.severity} onChange={(v) => updateFilter("severity", v)} />
          <FilterSelect label="Status" options={STATUSES} value={filters.status} onChange={(v) => updateFilter("status", v)} />
          <FilterSelect label="Priority" options={PRIORITIES} value={filters.priority} onChange={(v) => updateFilter("priority", v)} />
          <div className="col-md-3">
            <label className="form-label small mb-1">Order by</label>
            <select
              className="form-select form-select-sm"
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value)}
            >
              {SORT_MODES.map((m) => (
                <option key={m.key} value={m.key}>{m.label}</option>
              ))}
            </select>
          </div>
          <div className="col-md-1">
            <button className="btn btn-outline-danger btn-sm w-100" onClick={clearFilters}>
              Clear
            </button>
          </div>
        </div>
      </div>

      {error && <div className="alert alert-danger">{error}</div>}

      <div className="card shadow-sm">
        <div className="card-body p-0">
          {loading ? (
            <div className="text-center py-5">Loading incidents...</div>
          ) : incidents.length === 0 ? (
            <div className="text-center py-5 text-muted">No incidents match the selected filters.</div>
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    {sortMode === "smart" && <th>#</th>}
                    <th>ID</th>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>Risk</th>
                    <th>Priority</th>
                    <th>Location</th>
                    <th>Team</th>
                    <th>Status</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((inc, idx) => (
                    <tr
                      key={inc.id}
                      className={`row-${(inc.priority || "p4").toLowerCase()}`}
                      style={{
                        cursor: "pointer",
                        opacity: inc.status === "RESOLVED" ? 0.62 : 1,
                      }}
                      onClick={() => navigate(`/incidents/${inc.id}`)}
                    >
                      {sortMode === "smart" && <td className="text-muted fw-bold">{idx + 1}</td>}
                      <td>#{inc.id}</td>
                      <td>{inc.incident_type || "—"}</td>
                      <td><SeverityBadge severity={inc.severity} /></td>
                      <td><RiskScore score={inc.risk_score} /></td>
                      <td><PriorityBadge priority={inc.priority} /></td>
                      <td>{inc.location}</td>
                      <td className="small">
                        {inc.assigned_team_name ? (
                          <>
                            {inc.assigned_team_name}
                            {inc.assignment_overridden && (
                              <span className="badge bg-dark ms-1" title="Admin overrode the AI recommendation">
                                OVERRIDE
                              </span>
                            )}
                          </>
                        ) : inc.recommended_team_name ? (
                          <span className="text-muted">🤖 {inc.recommended_team_name}</span>
                        ) : (
                          <span className="text-muted">Unassigned</span>
                        )}
                      </td>
                      <td><StatusBadge status={inc.status} /></td>
                      <td className="small">{new Date(inc.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterSelect({ label, options, value, onChange }) {
  return (
    <div className="col-6 col-md-2">
      <label className="form-label small mb-1">{label}</label>
      <select className="form-select form-select-sm" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
