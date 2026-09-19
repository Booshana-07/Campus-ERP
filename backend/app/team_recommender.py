"""
Phase 2, Feature 2 — AI response-team recommendation.

Given an analyzed incident (type / severity / risk / priority) and the current
response teams, this picks the most appropriate team and explains why in one
sentence.

It is deliberately deterministic scoring rather than an LLM call, because:
  * it must never fail or hang during the demo,
  * the reasoning stays explainable to judges,
  * the team list lives in our own database anyway.

The AI part of the platform (Groq classification + the AI action plan) still
drives the *inputs* to this — the incident type, severity and risk score all
come out of the classifier.
"""
from typing import List, Optional, Tuple

from . import models

# Which capability handles which incident type, best match first.
# Matching is done on lower-cased substrings of the team's name + capability,
# so it keeps working even if team names are edited later.
TYPE_PREFERENCES = {
    "FIRE": ["fire", "electrical", "security"],
    "ELECTRICAL": ["electrical", "fire", "maintenance"],
    "MEDICAL": ["medical", "security"],
    "ACCIDENT": ["medical", "security", "maintenance"],
    "SECURITY": ["security", "medical"],
    "INFRASTRUCTURE": ["maintenance", "electrical", "security"],
    "OTHER": ["security", "maintenance", "medical"],
}

# Campus coordinates, kept in sync with seed.py / the frontend map.
CAMPUS_LOCATIONS = {
    "Main Block": (12.9716, 79.1590),
    "AI & DS Lab": (12.9721, 79.1598),
    "Computer Lab": (12.9719, 79.1585),
    "Electrical Lab": (12.9712, 79.1601),
    "Library": (12.9725, 79.1580),
    "Hostel": (12.9705, 79.1610),
    "Cafeteria": (12.9718, 79.1575),
    "Playground": (12.9700, 79.1595),
    "Parking Area": (12.9730, 79.1605),
    "Medical Centre": (12.9722, 79.1570),
    "Security Gate": (12.9695, 79.1580),
    "Auditorium": (12.9727, 79.1592),
}


def _team_text(team: models.ResponseTeam) -> str:
    return f"{team.name} {team.capability}".lower()


def _distance_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Good-enough flat-earth distance for a single campus (a few hundred metres)."""
    lat_km = (a[0] - b[0]) * 111.0
    lon_km = (a[1] - b[1]) * 111.0 * 0.97  # cos(lat) at ~13°N
    return (lat_km ** 2 + lon_km ** 2) ** 0.5


def score_team(
    team: models.ResponseTeam,
    incident_type: str,
    severity: str,
    risk_score: Optional[int],
    location: Optional[str],
) -> Tuple[float, str]:
    """Return (score, short capability-match label) for one team."""
    prefs = TYPE_PREFERENCES.get((incident_type or "OTHER").upper(), TYPE_PREFERENCES["OTHER"])
    text = _team_text(team)

    score = 0.0
    match_label = "general support"
    for rank, keyword in enumerate(prefs):
        if keyword in text:
            # Best match = 100, each step down the preference list loses 25.
            score += max(10.0, 100.0 - rank * 25.0)
            match_label = "primary responder" if rank == 0 else "secondary responder"
            break

    # Availability matters a lot — a busy team can't actually respond.
    if team.availability == "AVAILABLE":
        score += 40.0
    else:
        score -= 60.0

    # Proximity: up to 15 points for being close to the incident location.
    if location and location in CAMPUS_LOCATIONS:
        dist = _distance_km(CAMPUS_LOCATIONS[location], (team.latitude, team.longitude))
        score += max(0.0, 15.0 - dist * 40.0)

    # For CRITICAL / very high risk, weight the specialist match even harder.
    if (severity or "").upper() == "CRITICAL" or (risk_score or 0) >= 85:
        if match_label == "primary responder":
            score += 20.0

    return score, match_label


def recommend_team(
    teams: List[models.ResponseTeam],
    incident_type: str,
    severity: str,
    risk_score: Optional[int] = None,
    priority: Optional[str] = None,
    location: Optional[str] = None,
):
    """
    Pick the best team. Returns (team_or_None, reason_string).

    Never raises — if there are no teams at all it returns (None, explanation).
    """
    if not teams:
        return None, "No response teams are configured in the system."

    scored = []
    for t in teams:
        s, label = score_team(t, incident_type, severity, risk_score, location)
        scored.append((s, label, t))
    scored.sort(key=lambda x: (-x[0], x[2].id))

    best_score, best_label, best_team = scored[0]

    # Was the ideal specialist skipped because it is busy?
    prefs = TYPE_PREFERENCES.get((incident_type or "OTHER").upper(), TYPE_PREFERENCES["OTHER"])
    ideal = next((t for t in teams if prefs and prefs[0] in _team_text(t)), None)
    busy_note = ""
    if ideal is not None and ideal.id != best_team.id and ideal.availability != "AVAILABLE":
        busy_note = f" The usual first responder ({ideal.name}) is currently BUSY."

    availability_note = (
        "and this team is currently available"
        if best_team.availability == "AVAILABLE"
        else "though this team is currently BUSY, so confirm before dispatch"
    )

    severity_text = (severity or "unclassified").lower()
    type_text = (incident_type or "OTHER").lower()
    priority_text = f" ({priority})" if priority else ""

    reason = (
        f"{best_team.name} is recommended because the incident is classified as a "
        f"{severity_text} {type_text} emergency{priority_text}, this team's capability is "
        f"'{best_team.capability}' ({best_label}), {availability_note}."
        + busy_note
    )

    if location and location in CAMPUS_LOCATIONS:
        dist_m = int(
            _distance_km(CAMPUS_LOCATIONS[location], (best_team.latitude, best_team.longitude)) * 1000
        )
        reason += f" Approx. {dist_m} m from {location}."

    return best_team, reason
