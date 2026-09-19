import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listIncidents } from "../api/client";
import { SeverityBadge, StatusBadge, PriorityBadge, RiskScore } from "../components/Badges";
import { useAuth } from "../context/AuthContext";
import usePolling from "../hooks/usePolling";

const STEPS = ["REPORTED", "ANALYZED", "ASSIGNED", "RESPONDING", "RESOLVED"];

/**
 * Phase 2, Feature 1 — the student (and faculty) view.
 *
 * Students get their own reports only. That isn't done by filtering in the
 * browser: the backend returns only their incidents for a STUDENT identity.
 */
export default function MyIncidents() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const res = await listIncidents({ mine: true, smart_queue: true });
      setIncidents(res.data);
      setError("");
    } catch {
      setError("Could not load your incidents. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(true);
  }, [load]);

  // Feature 8: refresh quietly so status changes appear without a manual reload.
  usePolling(() => load(false), 10000);

  const active = incidents.filter((i) => i.status !== "RESOLVED");
  const resolved = incidents.filter((i) => i.status === "RESOLVED");

  if (loading) return <div className="text-center py-5">Loading your incidents...</div>;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-1 flex-wrap gap-2">
        <h3 className="fw-bold mb-0">🧾 My Incidents</h3>
        <div className="d-flex gap-2">
          <button className="btn btn-outline-secondary btn-sm" onClick={() => load(true)}>
            ↻ Refresh
          </button>
          <Link className="btn btn-danger btn-sm" to="/report">
            🚨 Report Emergency
          </Link>
        </div>
      </div>
      <p className="text-muted">
        Hello {user?.name?.split(" ")[0]} — these are the emergencies you reported, and where each
        one has reached.
      </p>

      {error && <div className="alert alert-danger">{error}</div>}

      {incidents.length === 0 ? (
        <div className="card shadow-sm p-5 text-center">
          <div className="fs-1">📭</div>
          <h6 className="fw-bold mt-2">You haven't reported anything yet</h6>
          <p className="text-muted mb-3">
            If you see an emergency on campus, report it here and it will be analyzed instantly.
          </p>
          <div>
            <Link className="btn btn-danger" to="/report">
              Report an Emergency
            </Link>
          </div>
        </div>
      ) : (
        <>
          <h6 className="text-muted mt-3 mb-2">Active ({active.length})</h6>
          {active.length === 0 ? (
            <div className="card shadow-sm p-3 text-muted small">
              Nothing active — all of your reports have been resolved.
            </div>
          ) : (
            <div className="row g-3">
              {active.map((inc) => (
                <IncidentCard key={inc.id} incident={inc} onOpen={() => navigate(`/incidents/${inc.id}`)} />
              ))}
            </div>
          )}

          {resolved.length > 0 && (
            <>
              <h6 className="text-muted mt-4 mb-2">Resolved ({resolved.length})</h6>
              <div className="row g-3">
                {resolved.map((inc) => (
                  <IncidentCard key={inc.id} incident={inc} onOpen={() => navigate(`/incidents/${inc.id}`)} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function IncidentCard({ incident, onOpen }) {
  const stepIndex = STEPS.indexOf(incident.status);
  const pct = stepIndex >= 0 ? ((stepIndex + 1) / STEPS.length) * 100 : 0;

  return (
    <div className="col-md-6">
      <div
        className="card shadow-sm h-100"
        style={{ cursor: "pointer" }}
        onClick={onOpen}
        role="button"
      >
        <div className="card-body">
          <div className="d-flex justify-content-between align-items-start mb-2">
            <div>
              <div className="fw-bold">
                #{incident.id} · {incident.incident_type || "Pending"}
              </div>
              <div className="text-muted small">📍 {incident.location}</div>
            </div>
            <div className="text-end">
              <RiskScore score={incident.risk_score} size="1.3rem" />
              <div className="text-muted" style={{ fontSize: "0.7rem" }}>
                risk
              </div>
            </div>
          </div>

          <p className="small mb-2">{incident.description}</p>

          <div className="d-flex gap-2 flex-wrap mb-2">
            <SeverityBadge severity={incident.severity} />
            <PriorityBadge priority={incident.priority} />
            <StatusBadge status={incident.status} />
          </div>

          <div className="progress" style={{ height: 6 }}>
            <div
              className={`progress-bar ${incident.status === "RESOLVED" ? "bg-success" : "bg-danger"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="d-flex justify-content-between mt-1">
            <small className="text-muted">{incident.status}</small>
            <small className="text-muted">
              {incident.assigned_team_name ? `👥 ${incident.assigned_team_name}` : "Awaiting team"}
            </small>
          </div>
        </div>
      </div>
    </div>
  );
}
