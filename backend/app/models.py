"""
SQLAlchemy ORM models for: users, incidents, response_teams, incident_status_history.
"""
import datetime
import json
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base


# ----- Phase 3A: account status values -----
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_SUSPENDED = "SUSPENDED"
ACCOUNT_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED, STATUS_SUSPENDED)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    role = Column(String, nullable=False)  # STUDENT | FACULTY | ADMIN

    # ----- Phase 3A additions -----
    # Securely hashed password (bcrypt or PBKDF2-HMAC-SHA256). Never plaintext.
    # Nullable so that any pre-Phase-3A row stays valid until it is backfilled;
    # a NULL here simply means "this account cannot log in with a password yet".
    password_hash = Column(String, nullable=True)

    # PENDING | APPROVED | REJECTED | SUSPENDED
    # Self-registered Student/Faculty accounts start PENDING. The admin approval
    # interface that moves them along arrives in Phase 3B.
    status = Column(String, nullable=False, default=STATUS_PENDING)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ----- Phase 3B additions -----
    # Who last changed this account's status, when, and why. Populated by the
    # admin approval actions; nullable because pre-3B rows never had a review.
    status_reason = Column(Text, nullable=True)
    status_changed_at = Column(DateTime, nullable=True)
    status_changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Temporary emergency access (Phase 3B, section 5). An account reached
    # through the emergency-access route is flagged here and given an expiry.
    # It is NOT a login bypass: an administrator still has to approve the
    # request, and the account holds the minimum role (STUDENT).
    is_emergency_access = Column(Integer, nullable=False, default=0)  # 0/1 boolean
    access_expires_at = Column(DateTime, nullable=True)

    @property
    def is_access_expired(self) -> bool:
        """True once a time-limited emergency grant has run out."""
        if not self.access_expires_at:
            return False
        return datetime.datetime.utcnow() > self.access_expires_at


class ResponseTeam(Base):
    __tablename__ = "response_teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    capability = Column(String, nullable=False)  # e.g. "Medical", "Fire & Safety"
    members = Column(String, nullable=False)  # comma separated names for simplicity
    availability = Column(String, nullable=False, default="AVAILABLE")  # AVAILABLE | BUSY
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    incidents = relationship(
        "Incident", foreign_keys="Incident.assigned_team_id", back_populates="assigned_team"
    )


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)

    # Reporting details
    reporter_name = Column(String, nullable=False)
    reporter_role = Column(String, nullable=False)
    contact_number = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=False)  # user-selected category at submit time
    location = Column(String, nullable=False)
    image_filename = Column(String, nullable=True)

    # AI classification results
    incident_type = Column(String, nullable=True)
    severity = Column(String, nullable=True)  # LOW | MEDIUM | HIGH | CRITICAL
    risk_score = Column(Integer, nullable=True)  # 0-100
    priority = Column(String, nullable=True)  # P1 | P2 | P3 | P4
    ai_reason = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    analysis_source = Column(String, nullable=True)  # "AI Analysis" | "Fallback Analysis"

    # Workflow
    status = Column(String, nullable=False, default="REPORTED")
    # REPORTED -> ANALYZED -> ASSIGNED -> RESPONDING -> RESOLVED
    assigned_team_id = Column(Integer, ForeignKey("response_teams.id"), nullable=True)

    # ----- Phase 2 additions -----
    # Who reported it (links an incident to the logged-in user, so STUDENTs can
    # see "my incidents" only). Nullable so Phase 1 rows stay valid.
    reporter_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # AI response-team recommendation (Feature 2)
    recommended_team_id = Column(Integer, ForeignKey("response_teams.id"), nullable=True)
    recommendation_reason = Column(Text, nullable=True)

    # AI emergency action plan (Feature 5) — stored as JSON text in the column
    # "action_plan", but exposed to Python/Pydantic as a real list via the
    # `action_plan` property below.
    action_plan_json = Column("action_plan", Text, nullable=True)
    action_plan_source = Column(String, nullable=True)  # "AI Analysis" | "Fallback Analysis"

    # Admin override tracking (Feature 3)
    assigned_by_name = Column(String, nullable=True)
    assignment_overridden = Column(Integer, nullable=False, default=0)  # 0/1 boolean

    # Real response-time tracking (Feature 6)
    analyzed_at = Column(DateTime, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    responding_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Two FKs now point at response_teams, so foreign_keys must be explicit.
    assigned_team = relationship(
        "ResponseTeam", foreign_keys=[assigned_team_id], back_populates="incidents"
    )
    recommended_team = relationship("ResponseTeam", foreign_keys=[recommended_team_id])

    @property
    def action_plan(self) -> list:
        """The stored JSON action plan, as a list of strings (empty list if none)."""
        if not self.action_plan_json:
            return []
        try:
            data = json.loads(self.action_plan_json)
            return [str(s) for s in data] if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []

    def set_action_plan(self, steps: list):
        self.action_plan_json = json.dumps(list(steps or []))
    status_history = relationship(
        "IncidentStatusHistory", back_populates="incident", cascade="all, delete-orphan"
    )


# ===========================================================================
# Phase I (Team Assignment + Reassignment) — assignment history
# ===========================================================================
class IncidentAssignment(Base):
    """
    One row per team "tenure" on an incident. Assigning a team for the first
    time creates one active row; reassigning deactivates the old row (keeping
    it forever, for history) and creates a new active one.

    `incidents.assigned_team_id` remains the fast "current team" pointer used
    everywhere else in the app — this table exists purely to answer "what was
    the history of this incident's team assignment", which no Phase 1/2/3 table
    could answer (assigning a new team used to silently overwrite the old
    value with no trace).
    """

    __tablename__ = "incident_assignments"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False, index=True)

    team_id = Column(Integer, ForeignKey("response_teams.id"), nullable=False)
    team_name = Column(String, nullable=False)  # denormalised so history reads correctly forever

    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_by_name = Column(String, nullable=False)

    is_override = Column(Integer, nullable=False, default=0)  # differed from AI recommendation
    reason = Column(Text, nullable=True)  # why THIS team (esp. for a reassignment)

    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Integer, nullable=False, default=1)  # 1 = current assignment
    deactivated_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", backref="assignment_history")
    team = relationship("ResponseTeam")


class IncidentStatusHistory(Base):
    __tablename__ = "incident_status_history"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    status = Column(String, nullable=False)
    note = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    # ----- Phase 2 additions (Feature 10: richer activity timeline) -----
    actor_name = Column(String, nullable=True)   # who performed the action
    actor_role = Column(String, nullable=True)   # STUDENT | FACULTY | ADMIN | SYSTEM
    event_type = Column(String, nullable=True)   # STATUS | AI | RECOMMENDATION | ASSIGNMENT | OVERRIDE

    incident = relationship("Incident", back_populates="status_history")


class Notification(Base):
    """Phase 2, Feature 7 — simple DB-backed in-app notifications (no Redis/Kafka/Firebase)."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=True)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # CRITICAL | ASSIGNED | STATUS | RESOLVED | AI
    # Who should see it: "ADMIN" (admin console) or "ALL".
    audience_role = Column(String, nullable=False, default="ADMIN")
    # Optionally target one specific user (e.g. the student who reported it).
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_read = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ===========================================================================
# Phase 3B — audit log
# ===========================================================================
class AuditLog(Base):
    """
    An append-only record of security-sensitive events (section 6).

    Nothing in the application ever updates or deletes a row here — events are
    only ever added. Actor details are denormalised (name/role copied in at the
    time of the event) so the log still reads correctly years later even if the
    actor's account is renamed or removed.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # WHO
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = system/anonymous
    actor_name = Column(String, nullable=False, default="System")
    actor_role = Column(String, nullable=False, default="SYSTEM")

    # WHAT
    action = Column(String, nullable=False, index=True)  # see AUDIT_ACTIONS below

    # TO WHAT
    target_type = Column(String, nullable=True)   # USER | EMERGENCY_ACCESS | INCIDENT
    target_id = Column(Integer, nullable=True)
    target_label = Column(String, nullable=True)  # human-readable, e.g. an email

    # WHY / EXTRA
    details = Column(Text, nullable=True)

    # WHEN
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)


# Canonical action names, so the log stays searchable and the UI can label it.
AUDIT_ACTIONS = (
    "USER_REGISTERED",
    "USER_APPROVED",
    "USER_REJECTED",
    "USER_SUSPENDED",
    "USER_REACTIVATED",
    "LOGIN_SUCCESS",
    "LOGIN_BLOCKED",
    "EMERGENCY_ACCESS_REQUESTED",
    "EMERGENCY_ACCESS_APPROVED",
    "EMERGENCY_ACCESS_REJECTED",
    "EMERGENCY_ACCESS_USED",
    "USERS_EXPORTED",
    # ----- Phase I (Team Assignment + Reassignment) -----
    "TEAM_ASSIGNED",
    "TEAM_REASSIGNED",
)


# ===========================================================================
# Phase 3B — emergency access requests
# ===========================================================================
EA_PENDING = "PENDING"
EA_APPROVED = "APPROVED"
EA_REJECTED = "REJECTED"
EA_STATUSES = (EA_PENDING, EA_APPROVED, EA_REJECTED)


class EmergencyAccessRequest(Base):
    """
    Section 5 — a controlled route for someone who is not yet approved but has
    a genuine emergency to report.

    This is explicitly NOT an authentication bypass. Submitting a request grants
    nothing at all. An administrator must approve it, and approval issues only
    a time-limited, minimum-privilege grant.
    """

    __tablename__ = "emergency_access_requests"

    id = Column(Integer, primary_key=True, index=True)

    # What the requester told us
    full_name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    contact_number = Column(String, nullable=True)
    reason = Column(Text, nullable=False)            # why they need access
    emergency_description = Column(Text, nullable=False)
    location = Column(String, nullable=True)
    incident_details = Column(Text, nullable=True)

    # A random code returned to the requester. They need it (together with the
    # email they used) to collect the grant, so an approval can't be picked up
    # by someone who merely guesses the email address.
    reference_code = Column(String, nullable=False, unique=True, index=True)

    status = Column(String, nullable=False, default=EA_PENDING, index=True)

    # Review
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_by_name = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)

    # The grant, once approved
    granted_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    access_expires_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, nullable=True)  # when the grant was picked up

    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
