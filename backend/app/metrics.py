"""
Phase 2, Feature 6 — real response-time tracking.

Nothing here is hard-coded or invented. Every number comes from either the
incident's own timestamp columns or its `incident_status_history` rows. If an
incident never reached a stage, that stage contributes nothing to the average,
and if no incident has reached it at all the average is returned as None so the
UI can show a clean "no data yet" state instead of a fake number.
"""
from typing import List, Optional

from . import models


def incident_timestamps(incident: models.Incident) -> dict:
    """
    Resolve the five workflow timestamps for one incident.

    Prefers the dedicated columns added in Phase 2, and falls back to the
    existing status-history rows so that incidents created during Phase 1
    (which have no analyzed_at/assigned_at/responding_at) still produce real
    numbers.
    """
    history = sorted(incident.status_history or [], key=lambda h: h.timestamp)

    def first_history(status: str):
        for h in history:
            if h.status == status:
                return h.timestamp
        return None

    reported = incident.created_at or first_history("REPORTED")
    return {
        "REPORTED": reported,
        "ANALYZED": incident.analyzed_at or first_history("ANALYZED"),
        "ASSIGNED": incident.assigned_at or first_history("ASSIGNED"),
        "RESPONDING": incident.responding_at or first_history("RESPONDING"),
        "RESOLVED": incident.resolved_at or first_history("RESOLVED"),
    }


def _minutes_between(start, end) -> Optional[float]:
    if not start or not end:
        return None
    delta = (end - start).total_seconds() / 60.0
    return round(delta, 1) if delta >= 0 else None


def incident_durations(incident: models.Incident) -> dict:
    """Per-incident durations in minutes (None where the stage wasn't reached)."""
    ts = incident_timestamps(incident)
    reported = ts["REPORTED"]

    # "Response" = the first moment a team was actually put on it. RESPONDING if
    # we have it, otherwise ASSIGNED.
    response_point = ts["RESPONDING"] or ts["ASSIGNED"]

    return {
        "time_to_assignment_minutes": _minutes_between(reported, ts["ASSIGNED"]),
        "time_to_response_minutes": _minutes_between(reported, response_point),
        "resolution_time_minutes": _minutes_between(reported, ts["RESOLVED"]),
    }


def _average(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 1)


def aggregate_metrics(incidents: List[models.Incident]) -> dict:
    """Averages across all incidents, plus the sample size behind each average."""
    assignment, response, resolution = [], [], []

    for inc in incidents:
        d = incident_durations(inc)
        if d["time_to_assignment_minutes"] is not None:
            assignment.append(d["time_to_assignment_minutes"])
        if d["time_to_response_minutes"] is not None:
            response.append(d["time_to_response_minutes"])
        if d["resolution_time_minutes"] is not None:
            resolution.append(d["resolution_time_minutes"])

    return {
        "avg_time_to_assignment_minutes": _average(assignment),
        "avg_response_time_minutes": _average(response),
        "avg_resolution_time_minutes": _average(resolution),
        "assignment_sample_size": len(assignment),
        "response_sample_size": len(response),
        "resolution_sample_size": len(resolution),
    }
