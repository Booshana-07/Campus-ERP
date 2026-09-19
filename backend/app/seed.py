"""
Seeds the database with realistic Indian-college demo data:
demo users, response teams, and a handful of sample incidents
(run through the AI classifier / fallback so they have real analysis data).
"""
import datetime
import os

from sqlalchemy.orm import Session
from . import models
from .ai_classifier import classify_incident
from .action_plan import fallback_action_plan
from .team_recommender import recommend_team
from .security import hash_password

# Phase 3A: demo accounts now carry a real, hashed password and an APPROVED
# status so the platform is usable straight after a fresh install. The password
# is read from DEMO_USER_PASSWORD (backend/.env) and is documented in
# PHASE3A.md — it is never written into the frontend or shown in the UI.
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "Campus@2025").strip() or "Campus@2025"

DEMO_USERS = [
    {"name": "Harish Kumar", "email": "student@campus.edu", "role": "STUDENT"},
    {"name": "Priya Sharma", "email": "faculty@campus.edu", "role": "FACULTY"},
    {"name": "Arjun Kumar", "email": "admin@campus.edu", "role": "ADMIN"},
]

# Approximate campus layout used purely for the demo map (fictional coordinates
# centered around a generic campus so the map has a realistic spread).
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

RESPONSE_TEAMS = [
    {
        "name": "Medical Team",
        "capability": "Medical / First Aid",
        "members": "Dr. Kavitha Rao, Nurse Suresh Babu",
        "availability": "AVAILABLE",
        "latitude": 12.9722, "longitude": 79.1570,  # near Medical Centre
    },
    {
        "name": "Fire & Safety Team",
        "capability": "Fire Suppression / Evacuation",
        "members": "Ramesh Iyer, Vignesh Pillai",
        "availability": "AVAILABLE",
        "latitude": 12.9712, "longitude": 79.1601,  # near Electrical Lab
    },
    {
        "name": "Security Team",
        "capability": "Campus Security / Law & Order",
        "members": "Head Guard Muthu Krishnan, Guard Selvam",
        "availability": "AVAILABLE",
        "latitude": 12.9695, "longitude": 79.1580,  # near Security Gate
    },
    {
        "name": "Electrical Team",
        "capability": "Electrical Repair / Power Isolation",
        "members": "Karthik Raja, Dinesh Babu",
        "availability": "AVAILABLE",
        "latitude": 12.9712, "longitude": 79.1601,
    },
    {
        "name": "Maintenance Team",
        "capability": "General Maintenance / Infrastructure",
        "members": "Manoj Kumar, Saravanan G",
        "availability": "AVAILABLE",
        "latitude": 12.9716, "longitude": 79.1590,
    },
]

SEED_INCIDENTS = [
    {
        "reporter_name": "Harish Kumar",
        "reporter_role": "STUDENT",
        "contact_number": "9876543210",
        "description": "Student collapsed near the cafeteria and needs immediate medical assistance.",
        "category": "MEDICAL",
        "location": "Cafeteria",
    },
    {
        "reporter_name": "Priya Sharma",
        "reporter_role": "FACULTY",
        "contact_number": "9876501234",
        "description": "Smoke detected inside the electrical laboratory.",
        "category": "FIRE",
        "location": "Electrical Lab",
    },
    {
        "reporter_name": "Deepak Nair",
        "reporter_role": "STUDENT",
        "contact_number": "9845012345",
        "description": "Unauthorized person reported near the hostel entrance.",
        "category": "SECURITY",
        "location": "Hostel",
    },
    {
        "reporter_name": "Meena Iyer",
        "reporter_role": "STUDENT",
        "contact_number": "9789054321",
        "description": "Electrical spark and burning smell near the computer lab.",
        "category": "ELECTRICAL",
        "location": "Computer Lab",
    },
    {
        "reporter_name": "Suresh Babu",
        "reporter_role": "FACULTY",
        "contact_number": "9900123456",
        "description": "Student injured during sports activity on the playground, possible fracture.",
        "category": "ACCIDENT",
        "location": "Playground",
    },
]


# Phase 2: two already-closed incidents from "earlier this week". These exist so
# that the response-time metrics (Feature 6) and team-workload analytics
# (Feature 9) have genuine history to calculate from on a fresh database —
# the numbers shown are computed from these timestamps, not hard-coded.
RESOLVED_SEED_INCIDENTS = [
    {
        "reporter_name": "Ananya Krishnan",
        "reporter_role": "STUDENT",
        "contact_number": "9791234567",
        "description": "Water leaking heavily from the ceiling near the library reading hall.",
        "category": "INFRASTRUCTURE",
        "location": "Library",
        "team_name": "Maintenance Team",
        "hours_ago": 30,
        "assign_after_min": 9,
        "respond_after_min": 14,
        "resolve_after_min": 65,
    },
    {
        "reporter_name": "Vikram Ranganathan",
        "reporter_role": "FACULTY",
        "contact_number": "9840567890",
        "description": "Student collapsed during the morning assembly in the auditorium.",
        "category": "MEDICAL",
        "location": "Auditorium",
        "team_name": "Medical Team",
        "hours_ago": 22,
        "assign_after_min": 3,
        "respond_after_min": 5,
        "resolve_after_min": 38,
    },
]


def _seed_resolved_incident(db: Session, spec: dict, teams_by_name: dict, users_by_name: dict):
    """Create one fully-closed incident with a realistic timestamp trail."""
    result = classify_incident(spec["description"], spec["category"], spec["location"])
    team = teams_by_name.get(spec["team_name"])

    reported_at = datetime.datetime.utcnow() - datetime.timedelta(hours=spec["hours_ago"])
    analyzed_at = reported_at + datetime.timedelta(minutes=1)
    assigned_at = reported_at + datetime.timedelta(minutes=spec["assign_after_min"])
    responding_at = reported_at + datetime.timedelta(minutes=spec["respond_after_min"])
    resolved_at = reported_at + datetime.timedelta(minutes=spec["resolve_after_min"])

    recommended, reason = recommend_team(
        list(teams_by_name.values()), result.incidentType, result.severity,
        result.riskScore, result.priority, spec["location"],
    )

    incident = models.Incident(
        reporter_name=spec["reporter_name"],
        reporter_role=spec["reporter_role"],
        contact_number=spec["contact_number"],
        description=spec["description"],
        category=spec["category"],
        location=spec["location"],
        incident_type=result.incidentType,
        severity=result.severity,
        risk_score=result.riskScore,
        priority=result.priority,
        ai_reason=result.reason,
        recommended_action=result.recommendedAction,
        analysis_source=result.source,
        status="RESOLVED",
        assigned_team_id=team.id if team else None,
        assigned_by_name="Arjun Kumar",
        assignment_overridden=0,
        reporter_user_id=(users_by_name.get(spec["reporter_name"]).id
                          if users_by_name.get(spec["reporter_name"]) else None),
        recommended_team_id=recommended.id if recommended else None,
        recommendation_reason=reason,
        action_plan_source="Fallback Analysis",
        created_at=reported_at,
        analyzed_at=analyzed_at,
        assigned_at=assigned_at,
        responding_at=responding_at,
        resolved_at=resolved_at,
        updated_at=resolved_at,
    )
    incident.set_action_plan(fallback_action_plan(result.incidentType, result.severity))
    db.add(incident)
    db.flush()

    trail = [
        ("REPORTED", reported_at, f"Incident reported by {spec['reporter_name']}.",
         spec["reporter_name"], spec["reporter_role"], "STATUS"),
        ("ANALYZED", analyzed_at, f"{result.source} completed.", "AI Engine", "SYSTEM", "AI"),
        ("ANALYZED", analyzed_at, f"AI recommended {recommended.name}." if recommended else "No team available.",
         "AI Engine", "SYSTEM", "RECOMMENDATION"),
        ("ASSIGNED", assigned_at, f"Assigned to {spec['team_name']} by Arjun Kumar",
         "Arjun Kumar", "ADMIN", "ASSIGNMENT"),
        ("RESPONDING", responding_at, f"{spec['team_name']} reached the location.",
         "Arjun Kumar", "ADMIN", "STATUS"),
        ("RESOLVED", resolved_at, "Situation handled and area declared safe.",
         "Arjun Kumar", "ADMIN", "STATUS"),
    ]
    for status, ts, note, actor, role, event_type in trail:
        db.add(models.IncidentStatusHistory(
            incident_id=incident.id, status=status, note=note, timestamp=ts,
            actor_name=actor, actor_role=role, event_type=event_type,
        ))


def seed_if_empty(db: Session):
    if db.query(models.User).count() > 0:
        return  # already seeded

    user_objs = []
    for u in DEMO_USERS:
        user = models.User(
            **u,
            password_hash=hash_password(DEMO_USER_PASSWORD),
            status=models.STATUS_APPROVED,
            created_at=datetime.datetime.utcnow(),
        )
        db.add(user)
        user_objs.append(user)

    team_objs = []
    for t in RESPONSE_TEAMS:
        team = models.ResponseTeam(**t)
        db.add(team)
        team_objs.append(team)
    db.flush()  # get IDs

    users_by_name = {u.name: u for u in user_objs}
    teams_by_name = {t.name: t for t in team_objs}

    now = datetime.datetime.utcnow()
    for idx, inc in enumerate(SEED_INCIDENTS):
        result = classify_incident(inc["description"], inc["category"], inc["location"])
        # Phase 2: seeded incidents also get a team recommendation and action plan.
        recommended, reason = recommend_team(
            team_objs, result.incidentType, result.severity,
            result.riskScore, result.priority, inc["location"],
        )
        reporter = users_by_name.get(inc["reporter_name"])
        incident = models.Incident(
            reporter_name=inc["reporter_name"],
            reporter_role=inc["reporter_role"],
            contact_number=inc["contact_number"],
            description=inc["description"],
            category=inc["category"],
            location=inc["location"],
            incident_type=result.incidentType,
            severity=result.severity,
            risk_score=result.riskScore,
            priority=result.priority,
            ai_reason=result.reason,
            recommended_action=result.recommendedAction,
            analysis_source=result.source,
            status="ANALYZED",
            reporter_user_id=reporter.id if reporter else None,
            recommended_team_id=recommended.id if recommended else None,
            recommendation_reason=reason,
            action_plan_source="Fallback Analysis",
            created_at=now - datetime.timedelta(hours=(len(SEED_INCIDENTS) - idx)),
            analyzed_at=now - datetime.timedelta(hours=(len(SEED_INCIDENTS) - idx)),
            updated_at=now - datetime.timedelta(hours=(len(SEED_INCIDENTS) - idx)),
        )
        incident.set_action_plan(fallback_action_plan(result.incidentType, result.severity))
        db.add(incident)
        db.flush()
        db.add(models.IncidentStatusHistory(
            incident_id=incident.id, status="REPORTED", note="Incident reported.",
            actor_name=inc["reporter_name"], actor_role=inc["reporter_role"], event_type="STATUS",
        ))
        db.add(models.IncidentStatusHistory(
            incident_id=incident.id, status="ANALYZED", note=f"{result.source} completed.",
            actor_name="AI Engine", actor_role="SYSTEM", event_type="AI",
        ))
        if recommended:
            db.add(models.IncidentStatusHistory(
                incident_id=incident.id, status="ANALYZED",
                note=f"AI recommended {recommended.name}.",
                actor_name="AI Engine", actor_role="SYSTEM", event_type="RECOMMENDATION",
            ))

    # Phase 2: closed incidents from earlier in the week, so the response-time
    # metrics and team workload analytics have real history to work from.
    for spec in RESOLVED_SEED_INCIDENTS:
        _seed_resolved_incident(db, spec, teams_by_name, users_by_name)

    db.commit()
