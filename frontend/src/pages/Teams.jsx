import React, { useEffect, useState } from "react";
import { listTeams } from "../api/client";

export default function Teams() {
  const [teams, setTeams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    load();
  }, []);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await listTeams();
      setTeams(res.data);
    } catch (err) {
      setError("Could not load teams. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="text-center py-5">Loading teams...</div>;
  if (error) return <div className="alert alert-danger">{error}</div>;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="fw-bold mb-0">👥 Response Teams</h3>
        <button className="btn btn-outline-secondary btn-sm" onClick={load}>↻ Refresh</button>
      </div>
      <div className="row g-3">
        {teams.map((team) => (
          <div className="col-md-4" key={team.id}>
            <div className="card shadow-sm h-100">
              <div className="card-body">
                <div className="d-flex justify-content-between align-items-start">
                  <h5 className="card-title">{team.name}</h5>
                  <span className={`badge ${team.availability === "AVAILABLE" ? "bg-success" : "bg-secondary"}`}>
                    {team.availability}
                  </span>
                </div>
                <p className="text-muted small mb-2">{team.capability}</p>
                <p className="mb-1"><strong>Members:</strong></p>
                <p className="small">{team.members}</p>
                <p className="small text-muted mb-0">
                  📍 {team.latitude.toFixed(4)}, {team.longitude.toFixed(4)}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
