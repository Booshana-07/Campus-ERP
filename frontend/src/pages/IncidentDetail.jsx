import React, { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getIncident, updateIncidentStatus, assignTeam, listTeams,
  regenerateRecommendation, regenerateActionPlan, getAssignmentHistory, API_BASE,
} from "../api/client";
import { SeverityBadge, StatusBadge, PriorityBadge, RiskScore } from "../components/Badges";
import { useAuth } from "../context/AuthContext";
import usePolling from "../hooks/usePolling";

// Phase 2, Feature 10: the AI recommendation is now its own visible stage.
const TIMELINE_STEPS = ["REPORTED", "ANALYZED", "RECOMMENDED", "ASSIGNED", "RESPONDING", "RESOLVED"];
const STATUS_STEPS = ["REPORTED", "ANALYZED", "ASSIGNED", "RESPONDING", "RESOLVED"];

const EVENT_ICONS = {
  STATUS: "🔄",
  AI: "🤖",
  RECOMMENDATION: "🎯",
  ASSIGNMENT: "👥",
  OVERRIDE: "🧑‍✈️",
};

function minutesBetween(a, b) {
  if (!a || !b) return null;
  const mins = (new Date(b) - new Date(a)) / 60000;
  return mins >= 0 ? Math.round(mins * 10) / 10 : null;
}

export default function IncidentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [incident, setIncident] = useState(null);
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionMsg, setActionMsg] = useState("");
  const [selectedTeam, setSelectedTeam] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [assignmentHistory, setAssignmentHistory] = useState([]);

  const isAdmin = user?.role === "ADMIN";

  const loadData = useCallback(
    async (showSpinner = true) => {
      if (showSpinner) setLoading(true);
      try {
        const incRes = await getIncident(id);
        setIncident(incRes.data);
        // Only staff need the team list; a student's view is read-only anyway.
        if (user?.role === "ADMIN" || user?.role === "FACULTY") {
          try {
            const teamsRes = await listTeams();
            setTeams(teamsRes.data);
          } catch {
            /* team list is optional here */
          }
        }
        // Phase I: assignment history is admin-only on the backend too, so
        // this quietly does nothing for non-admins rather than erroring.
        if (user?.role === "ADMIN") {
          try {
            const historyRes = await getAssignmentHistory(id);
            setAssignmentHistory(historyRes.data);
          } catch {
            /* history is a nice-to-have panel, never block the page on it */
          }
        }
        setError("");
      } catch (err) {
        setError(
          err.response?.status === 403
            ? "You can only view incidents that you reported."
            : err.response?.status === 404
            ? "That incident does not exist."
            : "Could not load incident. Is the backend running?"
        );
      } finally {
        setLoading(false);
      }
    },
    [id, user?.role]
  );

  useEffect(() => {
    loadData(true);
  }, [loadData]);

  // Feature 8: pick up status changes made by someone else.
  usePolling(() => {
    if (!busy) loadData(false);
  }, 12000);

  const handleStatusChange = async (newStatus) => {
    setBusy(true);
    setActionMsg("");
    try {
      const res = await updateIncidentStatus(id, newStatus, `Status changed to ${newStatus} by ${user.name}`);
      setIncident(res.data);
      setActionMsg(`Status updated to ${newStatus}.`);
    } catch (err) {
      setActionMsg(err.response?.data?.detail || "Failed to update status.");
    } finally {
      setBusy(false);
    }
  };

  const handleAssign = async (teamIdOverride) => {
    const teamId = teamIdOverride ?? selectedTeam;
    if (!teamId) return;
    setBusy(true);
    setActionMsg("");
    try {
      const isOverride =
        incident.recommended_team_id && parseInt(teamId, 10) !== incident.recommended_team_id;
      const isReassignment = Boolean(incident.assigned_team_name);
      // Send whatever reason the admin typed for a reassignment; for a fresh
      // override with no explicit reason, fall back to a generic one so the
      // audit trail/history still says *something*.
      const reasonToSend = overrideReason || (isOverride ? "Admin decision" : undefined);
      const res = await assignTeam(id, parseInt(teamId, 10), reasonToSend || undefined);
      setIncident(res.data);
      setActionMsg(
        isReassignment
          ? `Reassigned to ${res.data.assigned_team_name}.`
          : isOverride
          ? "Team assigned — recorded as an admin override of the AI recommendation."
          : "Team assigned (matching the AI recommendation)."
      );
      setOverrideReason("");
      setSelectedTeam("");
      const teamsRes = await listTeams();
      setTeams(teamsRes.data);
      if (isAdmin) {
        try {
          const historyRes = await getAssignmentHistory(id);
          setAssignmentHistory(historyRes.data);
        } catch {
          /* non-critical */
        }
      }
    } catch (err) {
      setActionMsg(err.response?.data?.detail || "Failed to assign team.");
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerateRecommendation = async () => {
    setBusy(true);
    setActionMsg("");
    try {
      const res = await regenerateRecommendation(id);
      setActionMsg(`AI recommends: ${res.data.team_name || "no available team"}.`);
      await loadData(false);
    } catch (err) {
      setActionMsg(err.response?.data?.detail || "Could not generate a recommendation.");
    } finally {
      setBusy(false);
    }
  };

  const handleRegeneratePlan = async () => {
    setBusy(true);
    setActionMsg("");
    try {
      const res = await regenerateActionPlan(id);
      setIncident(res.data);
      setActionMsg("Action plan regenerated.");
    } catch (err) {
      setActionMsg(err.response?.data?.detail || "Could not generate an action plan.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="text-center py-5">Loading incident...</div>;
  if (error) {
    return (
      <div>
        <button className="btn btn-link px-0 mb-3" onClick={() => navigate(-1)}>
          ← Back
        </button>
        <div className="alert alert-danger">{error}</div>
      </div>
    );
  }
  if (!incident) return null;

  // ---- Timeline position (includes the new RECOMMENDED stage) ----
  let currentStepIndex = STATUS_STEPS.indexOf(incident.status);
  if (incident.status === "ANALYZED") currentStepIndex = incident.recommended_team_id ? 2 : 1;
  else if (currentStepIndex >= 2) currentStepIndex += 1; // shift past RECOMMENDED

  const availableTeams = teams.filter((t) => t.availability === "AVAILABLE");
  const recommendedTeam = teams.find((t) => t.id === incident.recommended_team_id);

  const durations = {
    assignment: minutesBetween(incident.created_at, incident.assigned_at),
    response: minutesBetween(incident.created_at, incident.responding_at || incident.assigned_at),
    resolution: minutesBetween(incident.created_at, incident.resolved_at),
  };

  const selectedIsOverride =
    selectedTeam && incident.recommended_team_id && parseInt(selectedTeam, 10) !== incident.recommended_team_id;

  return (
    <div>
      <button className="btn btn-link px-0 mb-3" onClick={() => navigate(-1)}>
        ← Back
      </button>

      <div className="d-flex justify-content-between align-items-start mb-4 flex-wrap gap-3">
        <div>
          <h3 className="fw-bold mb-1">Incident #{incident.id}</h3>
          <div className="d-flex gap-2 align-items-center flex-wrap">
            <SeverityBadge severity={incident.severity} />
            <PriorityBadge priority={incident.priority} />
            <StatusBadge status={incident.status} />
            {incident.severity === "CRITICAL" && incident.status !== "RESOLVED" && (
              <span className="badge bg-danger">⚠️ CRITICAL — IMMEDIATE ATTENTION</span>
            )}
          </div>
        </div>
        <div className="text-end">
          <RiskScore score={incident.risk_score} size="2rem" />
          <div><small className="text-muted">Risk Score</small></div>
        </div>
      </div>

      {actionMsg && <div className="alert alert-info py-2">{actionMsg}</div>}

      {/* ---- Timeline ---- */}
      <div className="card shadow-sm mb-4 p-3">
        <h6 className="mb-3">Incident Progress</h6>
        <div className="d-flex justify-content-between position-relative">
          {TIMELINE_STEPS.map((step, idx) => (
            <div key={step} className="text-center flex-grow-1 position-relative">
              <div
                className={`rounded-circle mx-auto d-flex align-items-center justify-content-center ${
                  idx <= currentStepIndex ? "bg-danger text-white" : "bg-light border text-muted"
                }`}
                style={{ width: 34, height: 34, fontSize: "0.85rem", position: "relative", zIndex: 2 }}
              >
                {idx <= currentStepIndex ? "✓" : idx + 1}
              </div>
              <div className="small mt-1" style={{ fontSize: "0.72rem" }}>{step}</div>
              {idx < TIMELINE_STEPS.length - 1 && (
                <div
                  className={`timeline-line ${idx < currentStepIndex ? "bg-danger" : "bg-light"}`}
                  style={{ position: "absolute", top: 16, left: "60%", right: "-40%" }}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="row g-3">
        <div className="col-lg-7">
          {/* ---- Report details ---- */}
          <div className="card shadow-sm mb-3">
            <div className="card-body">
              <h6 className="card-title">Report Details</h6>
              <table className="table table-sm detail-table mb-0">
                <tbody>
                  <tr><th>Reporter</th><td>{incident.reporter_name} ({incident.reporter_role})</td></tr>
                  <tr><th>Contact</th><td>{incident.contact_number}</td></tr>
                  <tr><th>Category (reported)</th><td>{incident.category}</td></tr>
                  <tr><th>Location</th><td>{incident.location}</td></tr>
                  <tr><th>Description</th><td>{incident.description}</td></tr>
                  <tr><th>Created</th><td>{new Date(incident.created_at).toLocaleString()}</td></tr>
                  <tr><th>Updated</th><td>{new Date(incident.updated_at).toLocaleString()}</td></tr>
                  {incident.resolved_at && (
                    <tr><th>Resolved</th><td>{new Date(incident.resolved_at).toLocaleString()}</td></tr>
                  )}
                </tbody>
              </table>
              {incident.image_filename && (
                <div className="mt-3">
                  <p className="mb-1 fw-semibold">Attached Photo:</p>
                  <img
                    src={`${API_BASE}/uploads/${incident.image_filename}`}
                    alt="incident"
                    className="img-fluid rounded border"
                    style={{ maxHeight: 260 }}
                  />
                </div>
              )}
            </div>
          </div>

          {/* ---- AI analysis ---- */}
          <div className="card shadow-sm mb-3">
            <div className="card-body">
              <h6 className="card-title">
                {incident.analysis_source === "AI Analysis" ? "🤖 AI Analysis" : "⚙️ Fallback Analysis"}
                <span className="badge bg-light text-dark ms-2" style={{ fontSize: "0.65rem" }}>
                  {incident.analysis_source}
                </span>
              </h6>
              <table className="table table-sm detail-table mb-0">
                <tbody>
                  <tr><th>Classified Type</th><td>{incident.incident_type || "—"}</td></tr>
                  <tr><th>Severity</th><td><SeverityBadge severity={incident.severity} /></td></tr>
                  <tr><th>Priority</th><td><PriorityBadge priority={incident.priority} /></td></tr>
                  <tr><th>Risk Score</th><td><RiskScore score={incident.risk_score} /> / 100</td></tr>
                  <tr><th>AI Reasoning</th><td>{incident.ai_reason || "—"}</td></tr>
                  <tr><th>Recommended Action</th><td>{incident.recommended_action || "—"}</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* ---- Action plan (Feature 5) ---- */}
          <div className="card shadow-sm mb-3">
            <div className="card-body">
              <div className="d-flex justify-content-between align-items-center mb-2 flex-wrap gap-2">
                <h6 className="card-title mb-0">
                  📝 Emergency Action Plan
                  {incident.action_plan_source && (
                    <span className="badge bg-light text-dark ms-2" style={{ fontSize: "0.65rem" }}>
                      {incident.action_plan_source}
                    </span>
                  )}
                </h6>
                {isAdmin && (
                  <button
                    className="btn btn-sm btn-outline-secondary"
                    disabled={busy}
                    onClick={handleRegeneratePlan}
                  >
                    ↻ Regenerate
                  </button>
                )}
              </div>
              {incident.action_plan?.length ? (
                <ol className="mb-0 ps-3">
                  {incident.action_plan.map((step, idx) => (
                    <li key={idx} className="mb-1">{step}</li>
                  ))}
                </ol>
              ) : (
                <p className="text-muted small mb-0">
                  No action plan generated for this incident yet.
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="col-lg-5">
          {/* ---- AI team recommendation + admin override (Features 2 & 3) ---- */}
          <div className="card shadow-sm mb-3 border-danger">
            <div className="card-body">
              <h6 className="card-title">🎯 Response Team</h6>

              <div className="p-2 rounded mb-2" style={{ background: "#f4f1fb" }}>
                <div className="small text-muted">AI RECOMMENDED</div>
                <div className="fw-bold">
                  {incident.recommended_team_name || "No recommendation yet"}
                  {recommendedTeam && (
                    <span
                      className={`badge ms-2 ${
                        recommendedTeam.availability === "AVAILABLE" ? "bg-success" : "bg-secondary"
                      }`}
                    >
                      {recommendedTeam.availability}
                    </span>
                  )}
                </div>
                {incident.recommendation_reason && (
                  <div className="small text-muted mt-1">{incident.recommendation_reason}</div>
                )}
              </div>

              <div className="p-2 rounded mb-3" style={{ background: "#f1f6fb" }}>
                <div className="small text-muted">ASSIGNED BY ADMIN</div>
                <div className="fw-bold">
                  {incident.assigned_team_name || <span className="text-muted">Not yet assigned</span>}
                  {incident.assignment_overridden && (
                    <span className="badge bg-dark ms-2">ADMIN OVERRIDE</span>
                  )}
                </div>
                {incident.assigned_by_name && (
                  <div className="small text-muted mt-1">Assigned by {incident.assigned_by_name}</div>
                )}
              </div>

              {incident.assignment_overridden && (
                <div className="alert alert-warning py-2 small">
                  The admin chose <strong>{incident.assigned_team_name}</strong> instead of the
                  AI-recommended <strong>{incident.recommended_team_name}</strong>. The AI
                  recommendation is advisory — a human always makes the final call.
                </div>
              )}

              {isAdmin ? (
                <>
                  {!incident.recommended_team_name && (
                    <button
                      className="btn btn-sm btn-outline-danger w-100 mb-2"
                      disabled={busy}
                      onClick={handleRegenerateRecommendation}
                    >
                      🤖 Generate AI recommendation
                    </button>
                  )}

                  {incident.recommended_team_id &&
                    recommendedTeam?.availability === "AVAILABLE" &&
                    incident.recommended_team_id !== incident.assigned_team_id && (
                    <button
                      className="btn btn-sm btn-danger w-100 mb-2"
                      disabled={busy}
                      onClick={() => handleAssign(incident.recommended_team_id)}
                    >
                      {incident.assigned_team_name ? "🔁 Switch to" : "✅ Accept &"} assign {incident.recommended_team_name}
                    </button>
                  )}

                  <label className="form-label small mb-1">
                    {incident.assigned_team_name
                      ? "Reassign to a different team:"
                      : "Or choose a different team:"}
                  </label>
                  <div className="d-flex gap-2 mb-2">
                    <select
                      className="form-select form-select-sm"
                      value={selectedTeam}
                      onChange={(e) => setSelectedTeam(e.target.value)}
                    >
                      <option value="">Select available team...</option>
                      {availableTeams.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.name} ({t.capability})
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn btn-sm btn-outline-danger"
                      disabled={!selectedTeam || busy}
                      onClick={() => handleAssign()}
                    >
                      {incident.assigned_team_name ? "Reassign" : "Assign"}
                    </button>
                  </div>

                  {(selectedIsOverride || incident.assigned_team_name) && (
                    <input
                      className="form-control form-control-sm"
                      placeholder={
                        incident.assigned_team_name
                          ? "Reason for reassigning (optional, e.g. \"Fire team unavailable\")"
                          : "Reason for overriding the AI (optional)"
                      }
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                    />
                  )}

                  {availableTeams.length === 0 && (
                    <p className="text-warning small mt-2 mb-0">No teams currently available.</p>
                  )}
                </>
              ) : (
                <p className="text-muted small mb-0">
                  Only Admins can assign or change the response team.
                </p>
              )}
            </div>
          </div>

          {/* ---- Phase I: assignment history (who held this incident, and when) ---- */}
          {isAdmin && assignmentHistory.length > 0 && (
            <div className="card shadow-sm mb-3">
              <div className="card-body">
                <h6 className="card-title">📜 Assignment History</h6>
                <ul className="list-unstyled mb-0 small">
                  {assignmentHistory.map((row) => (
                    <li key={row.id} className="mb-2 pb-2 border-bottom">
                      <div className="d-flex justify-content-between align-items-start">
                        <div>
                          <strong>{row.team_name}</strong>{" "}
                          {row.is_active ? (
                            <span className="badge bg-success">CURRENT</span>
                          ) : (
                            <span className="badge bg-secondary">REPLACED</span>
                          )}
                          {row.is_override && (
                            <span className="badge bg-dark ms-1">OVERRIDE</span>
                          )}
                        </div>
                        <span className="text-muted" style={{ fontSize: "0.75rem" }}>
                          {new Date(row.assigned_at).toLocaleTimeString([], {
                            hour: "2-digit", minute: "2-digit",
                          })}
                        </span>
                      </div>
                      <div className="text-muted">by {row.assigned_by_name}</div>
                      {row.reason && <div className="text-muted fst-italic">"{row.reason}"</div>}
                      {!row.is_active && row.deactivated_at && (
                        <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                          Replaced at {new Date(row.deactivated_at).toLocaleTimeString([], {
                            hour: "2-digit", minute: "2-digit",
                          })}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* ---- Status management ---- */}
          <div className="card shadow-sm mb-3">
            <div className="card-body">
              <h6 className="card-title">Update Status</h6>
              {isAdmin ? (
                <div className="d-grid gap-2">
                  {STATUS_STEPS.map((step) => (
                    <button
                      key={step}
                      className={`btn btn-sm ${incident.status === step ? "btn-danger" : "btn-outline-secondary"}`}
                      disabled={busy || incident.status === step}
                      onClick={() => handleStatusChange(step)}
                    >
                      {step}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-muted small mb-0">Only Admins can change incident status.</p>
              )}
            </div>
          </div>

          {/* ---- Response times (Feature 6) ---- */}
          <div className="card shadow-sm mb-3">
            <div className="card-body">
              <h6 className="card-title">⏱️ Response Times</h6>
              <table className="table table-sm mb-0">
                <tbody>
                  <TimeRow label="Time to assignment" minutes={durations.assignment} />
                  <TimeRow label="Time to response" minutes={durations.response} />
                  <TimeRow label="Total resolution time" minutes={durations.resolution} />
                </tbody>
              </table>
            </div>
          </div>

          {/* ---- Activity timeline (Feature 10) ---- */}
          <div className="card shadow-sm">
            <div className="card-body">
              <h6 className="card-title">Activity Timeline</h6>
              <ul className="list-unstyled mb-0 small">
                {incident.status_history.map((h, idx) => (
                  <li key={idx} className="mb-2 border-bottom pb-2">
                    <div className="d-flex gap-2 align-items-center flex-wrap">
                      <span>{EVENT_ICONS[h.event_type] || "•"}</span>
                      <StatusBadge status={h.status} />
                      <span className="text-muted">{new Date(h.timestamp).toLocaleString()}</span>
                    </div>
                    {h.actor_name && (
                      <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                        by {h.actor_name}
                        {h.actor_role ? ` (${h.actor_role})` : ""}
                      </div>
                    )}
                    {h.note && <div className="text-muted">{h.note}</div>}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TimeRow({ label, minutes }) {
  return (
    <tr>
      <th className="fw-normal text-muted">{label}</th>
      <td className="text-end fw-semibold">
        {minutes != null ? `${minutes} min` : <span className="text-muted fw-normal">Not reached yet</span>}
      </td>
    </tr>
  );
}
