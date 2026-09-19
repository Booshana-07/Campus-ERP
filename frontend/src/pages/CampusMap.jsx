import React, { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import { listIncidents, listTeams } from "../api/client";
import { SeverityBadge, StatusBadge } from "../components/Badges";

// Fix default marker icons not loading with bundlers
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const CAMPUS_LOCATIONS = {
  "Main Block": [12.9716, 79.159],
  "AI & DS Lab": [12.9721, 79.1598],
  "Computer Lab": [12.9719, 79.1585],
  "Electrical Lab": [12.9712, 79.1601],
  Library: [12.9725, 79.158],
  Hostel: [12.9705, 79.161],
  Cafeteria: [12.9718, 79.1575],
  Playground: [12.97, 79.1595],
  "Parking Area": [12.973, 79.1605],
  "Medical Centre": [12.9722, 79.157],
  "Security Gate": [12.9695, 79.158],
  Auditorium: [12.9727, 79.1592],
};

const CAMPUS_CENTER = [12.9716, 79.159];

function severityIcon(severity) {
  const colors = { LOW: "#198754", MEDIUM: "#ffc107", HIGH: "#fd7e14", CRITICAL: "#dc3545" };
  const color = colors[severity] || "#6c757d";
  return L.divIcon({
    html: `<div style="background:${color};width:18px;height:18px;border-radius:50%;border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.5)"></div>`,
    className: "",
    iconSize: [18, 18],
  });
}

const teamIcon = L.divIcon({
  html: `<div style="background:#0d6efd;width:16px;height:16px;border-radius:3px;border:2px solid white;box-shadow:0 0 4px rgba(0,0,0,0.5)"></div>`,
  className: "",
  iconSize: [16, 16],
});

export default function CampusMap() {
  const [incidents, setIncidents] = useState([]);
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
      const [incRes, teamsRes] = await Promise.all([listIncidents(), listTeams()]);
      setIncidents(incRes.data.filter((i) => i.status !== "RESOLVED"));
      setTeams(teamsRes.data);
    } catch (err) {
      setError("Could not load map data. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="text-center py-5">Loading map...</div>;
  if (error) return <div className="alert alert-danger">{error}</div>;

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="fw-bold mb-0">🗺️ Campus Map</h3>
        <button className="btn btn-outline-secondary btn-sm" onClick={load}>↻ Refresh</button>
      </div>
      <p className="text-muted">
        Red/orange/yellow markers show active incidents by severity. Blue square markers show response team locations.
      </p>

      <div className="card shadow-sm">
        <MapContainer center={CAMPUS_CENTER} zoom={16} style={{ height: "60vh", width: "100%" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {incidents.map((inc) => {
            const coords = CAMPUS_LOCATIONS[inc.location];
            if (!coords) return null;
            return (
              <Marker key={`inc-${inc.id}`} position={coords} icon={severityIcon(inc.severity)}>
                <Popup>
                  <div>
                    <strong>Incident #{inc.id}</strong>
                    <div>Type: {inc.incident_type}</div>
                    <div>Severity: <SeverityBadge severity={inc.severity} /></div>
                    <div>Risk Score: {inc.risk_score}</div>
                    <div>Location: {inc.location}</div>
                    <div>Status: <StatusBadge status={inc.status} /></div>
                  </div>
                </Popup>
              </Marker>
            );
          })}

          {teams.map((team) => (
            <Marker key={`team-${team.id}`} position={[team.latitude, team.longitude]} icon={teamIcon}>
              <Popup>
                <div>
                  <strong>{team.name}</strong>
                  <div>{team.capability}</div>
                  <div>Status: {team.availability}</div>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}
