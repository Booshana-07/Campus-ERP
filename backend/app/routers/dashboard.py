import datetime
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_staff, require_admin
from ..metrics import aggregate_metrics, incident_durations

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=schemas.DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    user: models.User = Depends(require_staff),  # Phase 2: not visible to STUDENTs
):
    """
    Same four headline counters as Phase 1, plus real response-time metrics
    (Feature 6) computed from actual timestamps and status history — never from
    a hard-coded demo value. Averages come back as null when there is no data.
    """
    incidents = db.query(models.Incident).all()

    total = len(incidents)
    critical = sum(1 for i in incidents if i.severity == "CRITICAL")
    resolved = [i for i in incidents if i.status == "RESOLVED"]
    active = total - len(resolved)

    m = aggregate_metrics(incidents)

    return schemas.DashboardStats(
        total_incidents=total,
        critical_incidents=critical,
        active_incidents=active,
        resolved_incidents=len(resolved),
        avg_response_time_minutes=m["avg_response_time_minutes"],
        avg_time_to_assignment_minutes=m["avg_time_to_assignment_minutes"],
        avg_resolution_time_minutes=m["avg_resolution_time_minutes"],
        response_sample_size=m["response_sample_size"],
        assignment_sample_size=m["assignment_sample_size"],
        resolution_sample_size=m["resolution_sample_size"],
    )


def _counts(values) -> list:
    """Turn a list of labels into [{name, count}], biggest first."""
    counter = Counter(v for v in values if v)
    return [schemas.CountItem(name=k, count=v) for k, v in counter.most_common()]


@router.get("/analytics", response_model=schemas.AnalyticsOut)
def get_analytics(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),  # Phase 2: analytics are admin-only
):
    """
    Phase 2, Feature 9 — analytics built entirely from real database rows.
    Nothing here is generated or estimated; an empty database produces empty
    arrays and null averages.
    """
    incidents = db.query(models.Incident).all()
    teams = db.query(models.ResponseTeam).all()

    by_category = _counts([i.incident_type for i in incidents])
    by_severity = _counts([i.severity for i in incidents])
    by_priority = _counts([i.priority for i in incidents])
    by_status = _counts([i.status for i in incidents])

    resolved_count = sum(1 for i in incidents if i.status == "RESOLVED")
    active_vs_resolved = [
        schemas.CountItem(name="Active", count=len(incidents) - resolved_count),
        schemas.CountItem(name="Resolved", count=resolved_count),
    ]

    # Incident trend for the last 7 days (including today), oldest day first.
    today = datetime.datetime.utcnow().date()
    trend = []
    for offset in range(6, -1, -1):
        day = today - datetime.timedelta(days=offset)
        count = sum(1 for i in incidents if i.created_at and i.created_at.date() == day)
        trend.append(schemas.CountItem(name=day.strftime("%d %b"), count=count))

    # Team workload — how much each team is actually carrying.
    workload = []
    for team in teams:
        team_incidents = [i for i in incidents if i.assigned_team_id == team.id]
        team_resolved = [i for i in team_incidents if i.status == "RESOLVED"]
        durations = [
            incident_durations(i)["resolution_time_minutes"] for i in team_resolved
        ]
        durations = [d for d in durations if d is not None]
        workload.append(
            schemas.TeamWorkloadItem(
                team_name=team.name,
                availability=team.availability,
                total_assigned=len(team_incidents),
                active_assigned=len(team_incidents) - len(team_resolved),
                resolved_assigned=len(team_resolved),
                avg_resolution_time_minutes=(
                    round(sum(durations) / len(durations), 1) if durations else None
                ),
            )
        )
    workload.sort(key=lambda w: -w.total_assigned)

    m = aggregate_metrics(incidents)

    return schemas.AnalyticsOut(
        by_category=by_category,
        by_severity=by_severity,
        by_priority=by_priority,
        by_status=by_status,
        active_vs_resolved=active_vs_resolved,
        trend_last_7_days=trend,
        team_workload=workload,
        avg_time_to_assignment_minutes=m["avg_time_to_assignment_minutes"],
        avg_response_time_minutes=m["avg_response_time_minutes"],
        avg_resolution_time_minutes=m["avg_resolution_time_minutes"],
    )
