"""
Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


# ---------- Users ----------
class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    # Phase 3A. Defaulted so older callers that build a UserOut without a
    # status still work. Note there is deliberately no password field here —
    # the hash must never leave the backend.
    status: str = "APPROVED"

    # Phase 3B. Lets the UI show a "temporary access" banner and hide menu
    # items the backend would refuse anyway. Purely cosmetic — the backend
    # enforces the limits itself via require_permanent_account.
    is_emergency_access: bool = False
    access_expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Phase 3A: authentication ----------
class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str
    password: str
    confirm_password: str
    role: str  # STUDENT | FACULTY only — ADMIN self-registration is rejected


class TokenResponse(BaseModel):
    """What a successful login returns. Contains no password material."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class SignupResponse(BaseModel):
    """
    Signup does NOT return a token — the new account is PENDING and cannot be
    used until an administrator approves it (Phase 3B).
    """
    message: str
    user: UserOut


# ---------- Response Teams ----------
class TeamOut(BaseModel):
    id: int
    name: str
    capability: str
    members: str
    availability: str
    latitude: float
    longitude: float

    class Config:
        from_attributes = True


# ---------- Incidents ----------
class IncidentCreate(BaseModel):
    reporter_name: str
    reporter_role: str
    contact_number: str
    description: str
    category: str
    location: str
    image_filename: Optional[str] = None


class StatusHistoryOut(BaseModel):
    status: str
    note: Optional[str] = None
    timestamp: datetime
    # Phase 2 — richer activity timeline
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    event_type: Optional[str] = None

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    reporter_name: str
    reporter_role: str
    contact_number: str
    description: str
    category: str
    location: str
    image_filename: Optional[str] = None

    incident_type: Optional[str] = None
    severity: Optional[str] = None
    risk_score: Optional[int] = None
    priority: Optional[str] = None
    ai_reason: Optional[str] = None
    recommended_action: Optional[str] = None
    analysis_source: Optional[str] = None

    status: str
    assigned_team_id: Optional[int] = None
    assigned_team_name: Optional[str] = None

    # ----- Phase 2 -----
    reporter_user_id: Optional[int] = None
    recommended_team_id: Optional[int] = None
    recommended_team_name: Optional[str] = None
    recommendation_reason: Optional[str] = None
    action_plan: List[str] = []
    action_plan_source: Optional[str] = None
    assigned_by_name: Optional[str] = None
    assignment_overridden: bool = False

    analyzed_at: Optional[datetime] = None
    assigned_at: Optional[datetime] = None
    responding_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IncidentDetailOut(IncidentOut):
    status_history: List[StatusHistoryOut] = []


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None


class AssignTeamRequest(BaseModel):
    team_id: int


class AIAnalyzeRequest(BaseModel):
    description: str
    category: Optional[str] = None
    location: Optional[str] = None


class AIAnalysisResult(BaseModel):
    incidentType: str
    severity: str
    riskScore: int = Field(ge=0, le=100)
    priority: str
    reason: str
    recommendedAction: str
    source: str  # "AI Analysis" | "Fallback Analysis"


class DashboardStats(BaseModel):
    total_incidents: int
    critical_incidents: int
    active_incidents: int
    resolved_incidents: int
    # Phase 1 field kept for compatibility. From Phase 2 it is computed from real
    # status history: time from report to the first RESPONDING/ASSIGNED event.
    avg_response_time_minutes: Optional[float] = None

    # ----- Phase 2, Feature 6: real response-time metrics -----
    avg_time_to_assignment_minutes: Optional[float] = None
    avg_resolution_time_minutes: Optional[float] = None
    # How many incidents each average is actually based on (0 = no data yet).
    response_sample_size: int = 0
    assignment_sample_size: int = 0
    resolution_sample_size: int = 0


# ---------- Phase 2: assignment / recommendation ----------
class AssignTeamRequestV2(BaseModel):
    team_id: int
    override_reason: Optional[str] = None


class TeamRecommendationOut(BaseModel):
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    capability: Optional[str] = None
    availability: Optional[str] = None
    reason: str


# ---------- Phase I: assignment history ----------
class AssignmentHistoryOut(BaseModel):
    id: int
    team_id: int
    team_name: str
    assigned_by_name: str
    is_override: bool
    reason: Optional[str] = None
    assigned_at: datetime
    is_active: bool
    deactivated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Phase 2: notifications ----------
class NotificationOut(BaseModel):
    id: int
    incident_id: Optional[int] = None
    title: str
    message: str
    kind: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationSummary(BaseModel):
    unread_count: int
    notifications: List[NotificationOut] = []


# ---------- Phase 2: analytics ----------
class CountItem(BaseModel):
    name: str
    count: int


class TeamWorkloadItem(BaseModel):
    team_name: str
    availability: str
    total_assigned: int
    active_assigned: int
    resolved_assigned: int
    avg_resolution_time_minutes: Optional[float] = None


class AnalyticsOut(BaseModel):
    by_category: List[CountItem] = []
    by_severity: List[CountItem] = []
    by_priority: List[CountItem] = []
    by_status: List[CountItem] = []
    active_vs_resolved: List[CountItem] = []
    trend_last_7_days: List[CountItem] = []
    team_workload: List[TeamWorkloadItem] = []
    avg_time_to_assignment_minutes: Optional[float] = None
    avg_response_time_minutes: Optional[float] = None
    avg_resolution_time_minutes: Optional[float] = None


# ===========================================================================
# Phase 3B — admin user management
# ===========================================================================
class AdminUserOut(BaseModel):
    """
    The richer user view the admin console needs. Note there is still no
    password field of any kind — the hash never leaves the backend.
    """
    id: int
    name: str
    email: str
    role: str
    status: str
    created_at: Optional[datetime] = None

    status_reason: Optional[str] = None
    status_changed_at: Optional[datetime] = None
    status_changed_by_name: Optional[str] = None

    is_emergency_access: bool = False
    access_expires_at: Optional[datetime] = None

    # Handy context for the reviewer
    incident_count: int = 0

    class Config:
        from_attributes = True


class UserListOut(BaseModel):
    total: int
    pending_count: int
    users: List[AdminUserOut] = []


class StatusChangeRequest(BaseModel):
    """Body for approve / reject / suspend / reactivate."""
    reason: Optional[str] = None


# ---------- Audit log ----------
class AuditLogOut(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_name: str
    actor_role: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[int] = None
    target_label: Optional[str] = None
    details: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogListOut(BaseModel):
    total: int
    entries: List[AuditLogOut] = []


# ===========================================================================
# Phase 3B — emergency access
# ===========================================================================
class EmergencyAccessCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str
    contact_number: Optional[str] = None
    reason: str = Field(min_length=5)
    emergency_description: str = Field(min_length=10)
    location: Optional[str] = None
    incident_details: Optional[str] = None


class EmergencyAccessSubmitted(BaseModel):
    """
    What the requester gets back. Deliberately contains no token and no access
    of any kind — only a reference code for checking the decision later.
    """
    reference_code: str
    status: str
    message: str


class EmergencyAccessOut(BaseModel):
    """Admin-facing view of a request."""
    id: int
    full_name: str
    email: str
    contact_number: Optional[str] = None
    reason: str
    emergency_description: str
    location: Optional[str] = None
    incident_details: Optional[str] = None
    status: str
    reference_code: str

    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None

    granted_user_id: Optional[int] = None
    access_expires_at: Optional[datetime] = None
    collected_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EmergencyAccessListOut(BaseModel):
    total: int
    pending_count: int
    requests: List[EmergencyAccessOut] = []


class EmergencyAccessDecision(BaseModel):
    note: Optional[str] = None
    # How long the temporary grant lasts. Bounded server-side.
    duration_minutes: int = 120


class EmergencyAccessStatusOut(BaseModel):
    """
    Returned when a requester checks their reference code. A token is included
    ONLY when the request was approved and the grant has not expired.
    """
    status: str
    message: str
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None
    access_expires_at: Optional[datetime] = None
    user: Optional[UserOut] = None
