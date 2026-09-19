import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createIncident, uploadIncidentImage } from "../api/client";
import { useAuth } from "../context/AuthContext";

const CATEGORIES = ["MEDICAL", "FIRE", "ACCIDENT", "SECURITY", "ELECTRICAL", "INFRASTRUCTURE", "OTHER"];
const LOCATIONS = [
  "Main Block", "AI & DS Lab", "Computer Lab", "Electrical Lab", "Library", "Hostel",
  "Cafeteria", "Playground", "Parking Area", "Medical Centre", "Security Gate", "Auditorium",
];

export default function Report() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    reporter_name: user?.name || "",
    reporter_role: user?.role || "STUDENT",
    contact_number: "",
    description: "",
    category: "",
    location: "",
  });
  const [imageFile, setImageFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [validationErrors, setValidationErrors] = useState({});
  const [result, setResult] = useState(null);

  const handleChange = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const validate = () => {
    const errs = {};
    if (!form.reporter_name.trim()) errs.reporter_name = "Reporter name is required.";
    if (!form.contact_number.trim() || form.contact_number.trim().length < 10)
      errs.contact_number = "Enter a valid contact number (at least 10 digits).";
    if (!form.description.trim() || form.description.trim().length < 10)
      errs.description = "Please describe the emergency in at least 10 characters.";
    if (!form.category) errs.category = "Select an emergency category.";
    if (!form.location) errs.location = "Select a campus location.";
    setValidationErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setResult(null);
    if (!validate()) return;

    setSubmitting(true);
    try {
      let image_filename = null;
      if (imageFile) {
        const uploadRes = await uploadIncidentImage(imageFile);
        image_filename = uploadRes.data.filename;
      }

      const res = await createIncident({ ...form, image_filename });
      setResult(res.data);
    } catch (err) {
      setError(
        err.response?.data?.detail
          ? `Submission failed: ${err.response.data.detail}`
          : "Could not submit the report. Is the backend running?"
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <div className="card shadow-sm p-4">
        <h4 className="text-success">✅ Emergency Reported Successfully</h4>
        <p className="text-muted">Incident #{result.id} has been created and analyzed.</p>
        <div className="row g-3 mt-2">
          <div className="col-md-6">
            <div className="alert alert-info mb-0">
              <strong>{result.analysis_source}</strong>
              <div>Type: <strong>{result.incident_type}</strong></div>
              <div>Severity: <strong>{result.severity}</strong></div>
              <div>Risk Score: <strong>{result.risk_score}</strong></div>
              <div>Priority: <strong>{result.priority}</strong></div>
              <div className="mt-2"><em>{result.ai_reason}</em></div>
            </div>
          </div>
          <div className="col-md-6">
            <p><strong>Recommended Action:</strong></p>
            <p>{result.recommended_action}</p>

            {/* Phase 2, Feature 2 — the team the AI suggests for this incident */}
            {result.recommended_team_name && (
              <div className="p-2 rounded" style={{ background: "#f4f1fb" }}>
                <div className="small text-muted">AI RECOMMENDED RESPONSE TEAM</div>
                <div className="fw-bold">🎯 {result.recommended_team_name}</div>
                {result.recommendation_reason && (
                  <div className="small text-muted mt-1">{result.recommendation_reason}</div>
                )}
                <div className="small text-muted mt-1">
                  An admin will confirm or change this before dispatch.
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Phase 2, Feature 5 — what to do right now, while help is on the way */}
        {result.action_plan?.length > 0 && (
          <div className="mt-3">
            <p className="fw-semibold mb-1">
              📝 What to do now
              {result.action_plan_source && (
                <span className="badge bg-light text-dark ms-2" style={{ fontSize: "0.65rem" }}>
                  {result.action_plan_source}
                </span>
              )}
            </p>
            <ol className="ps-3 mb-0">
              {result.action_plan.map((step, idx) => (
                <li key={idx}>{step}</li>
              ))}
            </ol>
          </div>
        )}

        <div className="mt-3 d-flex gap-2 flex-wrap">
          <button className="btn btn-danger" onClick={() => navigate(`/incidents/${result.id}`)}>
            View Incident Details
          </button>
          <button
            className="btn btn-outline-secondary"
            onClick={() => {
              setResult(null);
              setForm({ ...form, description: "", category: "", location: "" });
              setImageFile(null);
            }}
          >
            Report Another Emergency
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h3 className="fw-bold mb-4">🚨 Report an Emergency</h3>
      <div className="card shadow-sm p-4" style={{ maxWidth: 720 }}>
        {error && <div className="alert alert-danger">{error}</div>}
        <form onSubmit={handleSubmit} noValidate>
          <div className="row g-3">
            <div className="col-md-6">
              <label className="form-label">Reporter Name</label>
              <input
                className={`form-control ${validationErrors.reporter_name ? "is-invalid" : ""}`}
                value={form.reporter_name}
                onChange={handleChange("reporter_name")}
              />
              {validationErrors.reporter_name && <div className="invalid-feedback">{validationErrors.reporter_name}</div>}
            </div>
            <div className="col-md-6">
              <label className="form-label">Reporter Role</label>
              {/* Phase 2: the role comes from the signed-in account rather than
                  being freely selectable, so reports are attributable. */}
              <input className="form-control" value={form.reporter_role} readOnly disabled />
            </div>
            <div className="col-md-6">
              <label className="form-label">Contact Number</label>
              <input
                className={`form-control ${validationErrors.contact_number ? "is-invalid" : ""}`}
                placeholder="e.g. 9876543210"
                value={form.contact_number}
                onChange={handleChange("contact_number")}
              />
              {validationErrors.contact_number && <div className="invalid-feedback">{validationErrors.contact_number}</div>}
            </div>
            <div className="col-md-6">
              <label className="form-label">Emergency Category</label>
              <select
                className={`form-select ${validationErrors.category ? "is-invalid" : ""}`}
                value={form.category}
                onChange={handleChange("category")}
              >
                <option value="">Select category...</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              {validationErrors.category && <div className="invalid-feedback">{validationErrors.category}</div>}
            </div>
            <div className="col-md-6">
              <label className="form-label">Campus Location</label>
              <select
                className={`form-select ${validationErrors.location ? "is-invalid" : ""}`}
                value={form.location}
                onChange={handleChange("location")}
              >
                <option value="">Select location...</option>
                {LOCATIONS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
              {validationErrors.location && <div className="invalid-feedback">{validationErrors.location}</div>}
            </div>
            <div className="col-md-6">
              <label className="form-label">Photo (optional)</label>
              <input
                type="file"
                accept="image/*"
                className="form-control"
                onChange={(e) => setImageFile(e.target.files?.[0] || null)}
              />
            </div>
            <div className="col-12">
              <label className="form-label">Emergency Description</label>
              <textarea
                className={`form-control ${validationErrors.description ? "is-invalid" : ""}`}
                rows={4}
                placeholder="Describe what happened in detail — this is analyzed by AI to determine severity and priority."
                value={form.description}
                onChange={handleChange("description")}
              />
              {validationErrors.description && <div className="invalid-feedback">{validationErrors.description}</div>}
            </div>
          </div>

          <button className="btn btn-danger mt-4 w-100" type="submit" disabled={submitting}>
            {submitting ? "Submitting & Analyzing..." : "🚨 Submit Emergency Report"}
          </button>
        </form>
      </div>
    </div>
  );
}
