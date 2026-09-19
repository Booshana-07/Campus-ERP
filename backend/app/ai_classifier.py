"""
AI incident classification.

Tries the Groq API (free tier, OpenAI-compatible /chat/completions endpoint) if
GROQ_API_KEY is configured. If the key is missing, the request fails, times out,
or the model returns something that doesn't validate, we ALWAYS fall back to a
deterministic local rule/keyword-based classifier so the app keeps working.
"""
import os
import json
import re
import requests
from pydantic import ValidationError
from .schemas import AIAnalysisResult

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ALLOWED_TYPES = ["FIRE", "MEDICAL", "ACCIDENT", "SECURITY", "ELECTRICAL", "INFRASTRUCTURE", "OTHER"]
ALLOWED_SEVERITY = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ALLOWED_PRIORITY = ["P1", "P2", "P3", "P4"]

SYSTEM_PROMPT = f"""You are an emergency triage AI for a college campus emergency response system.
Given an incident description, classify it and respond with ONLY a raw JSON object
(no markdown, no backticks, no extra text) in exactly this shape:

{{
  "incidentType": one of {ALLOWED_TYPES},
  "severity": one of {ALLOWED_SEVERITY},
  "riskScore": integer 0-100,
  "priority": one of {ALLOWED_PRIORITY} (P1 = most urgent),
  "reason": short explanation of the classification,
  "recommendedAction": short recommended first response action
}}

Guidance: fire/smoke/gas leaks with people trapped = CRITICAL/P1/riskScore 90+.
Life-threatening medical (unconscious, bleeding heavily, not breathing) = CRITICAL/P1.
Security threats involving weapons or intruders = HIGH-CRITICAL/P1-P2.
Minor injuries or small electrical issues = MEDIUM/P3.
Non-urgent infrastructure issues = LOW/P4.
"""


# ---------------------------------------------------------------------------
# Deterministic fallback classifier (keyword/rule based, no external calls)
# ---------------------------------------------------------------------------
KEYWORD_RULES = [
    # (keywords, incidentType, severity, riskScore, priority)
    (["smoke", "fire", "burning", "flames", "burnt smell"], "FIRE", "CRITICAL", 92, "P1"),
    (["spark", "electrocut", "shock", "wire", "electricity", "electrical"], "ELECTRICAL", "HIGH", 70, "P2"),
    (["unconscious", "not breathing", "bleeding", "collapsed", "cardiac", "seizure"], "MEDICAL", "CRITICAL", 95, "P1"),
    (["injury", "injured", "fell", "fracture", "sprain", "accident"], "ACCIDENT", "MEDIUM", 55, "P3"),
    (["weapon", "gun", "knife", "threat", "intruder", "fight", "assault", "unauthorized person"], "SECURITY", "HIGH", 80, "P1"),
    (["leak", "flood", "water", "ceiling", "structural", "collapse", "gas leak"], "INFRASTRUCTURE", "MEDIUM", 50, "P3"),
]


def fallback_classify(description: str) -> AIAnalysisResult:
    text = description.lower()

    for keywords, incident_type, severity, risk_score, priority in KEYWORD_RULES:
        if any(kw in text for kw in keywords):
            # Bump severity if description also mentions people trapped / students inside
            if any(w in text for w in ["trapped", "still inside", "can't get out", "stuck"]):
                risk_score = min(100, risk_score + 8)
                severity = "CRITICAL"
                priority = "P1"

            reason = (
                f"Fallback rule matched keyword(s) related to '{incident_type.title()}' "
                f"in the description. Classified as {severity} severity."
            )
            recommended_action = _recommended_action_for(incident_type, severity)
            return AIAnalysisResult(
                incidentType=incident_type,
                severity=severity,
                riskScore=risk_score,
                priority=priority,
                reason=reason,
                recommendedAction=recommended_action,
                source="Fallback Analysis",
            )

    # No keyword matched — default to a conservative, moderate-priority OTHER case
    return AIAnalysisResult(
        incidentType="OTHER",
        severity="MEDIUM",
        riskScore=40,
        priority="P3",
        reason="No specific high-risk keywords detected by the fallback classifier; "
        "flagged for manual review by campus staff.",
        recommendedAction="Route to campus security/admin desk for manual assessment.",
        source="Fallback Analysis",
    )


def _recommended_action_for(incident_type: str, severity: str) -> str:
    mapping = {
        "FIRE": "Evacuate the area immediately and dispatch Fire & Safety Team.",
        "MEDICAL": "Dispatch Medical Team immediately and alert campus medical centre.",
        "ACCIDENT": "Send Medical Team for first aid and assess the location for hazards.",
        "SECURITY": "Alert Security Team immediately and lock down the affected area.",
        "ELECTRICAL": "Cut power to the affected area and dispatch Electrical Team.",
        "INFRASTRUCTURE": "Dispatch Maintenance Team to inspect and secure the area.",
        "OTHER": "Route to Admin for manual triage and assignment.",
    }
    return mapping.get(incident_type, "Route to Admin for manual triage and assignment.")


# ---------------------------------------------------------------------------
# Groq-backed classifier
# ---------------------------------------------------------------------------
def _extract_json(raw_text: str) -> dict:
    """Groq sometimes wraps JSON in markdown fences — strip those before parsing."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def groq_classify(description: str, category: str = "", location: str = "") -> AIAnalysisResult:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured")

    user_prompt = f"Incident description: {description}\n"
    if category:
        user_prompt += f"Reported category: {category}\n"
    if location:
        user_prompt += f"Location: {location}\n"

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["choices"][0]["message"]["content"]
    parsed = _extract_json(raw_text)

    # Validate strictly — never let arbitrary AI output through unchecked
    incident_type = parsed.get("incidentType", "OTHER").upper()
    severity = parsed.get("severity", "MEDIUM").upper()
    priority = parsed.get("priority", "P3").upper()
    risk_score = int(parsed.get("riskScore", 40))

    if incident_type not in ALLOWED_TYPES:
        incident_type = "OTHER"
    if severity not in ALLOWED_SEVERITY:
        severity = "MEDIUM"
    if priority not in ALLOWED_PRIORITY:
        priority = "P3"
    risk_score = max(0, min(100, risk_score))

    return AIAnalysisResult(
        incidentType=incident_type,
        severity=severity,
        riskScore=risk_score,
        priority=priority,
        reason=str(parsed.get("reason", "AI classification based on description."))[:500],
        recommendedAction=str(parsed.get("recommendedAction", "Dispatch appropriate team."))[:500],
        source="AI Analysis",
    )


def classify_incident(description: str, category: str = "", location: str = "") -> AIAnalysisResult:
    """
    Main entry point used by the API layer.
    Always returns a valid AIAnalysisResult — never raises.
    """
    if GROQ_API_KEY:
        try:
            return groq_classify(description, category, location)
        except (requests.RequestException, json.JSONDecodeError, KeyError,
                ValueError, ValidationError, TypeError):
            # Any failure (network, bad JSON, invalid fields) -> silently fall back
            pass

    return fallback_classify(description)
