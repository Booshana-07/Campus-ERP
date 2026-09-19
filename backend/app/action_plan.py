"""
Phase 2, Feature 5 — AI emergency action plan.

Same architecture as the existing ai_classifier.py: try Groq if a key is
configured, and ALWAYS fall back to a deterministic per-incident-type plan if
the key is missing or the call fails. The app never depends on the network.

Returns (list_of_steps, source) where source is "AI Analysis" or
"Fallback Analysis" — matching the wording already used in Phase 1.
"""
import json
import os
import re

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

ACTION_PLAN_SYSTEM_PROMPT = """You are an emergency response coordinator for a college campus.
Given an incident, produce a SHORT, ordered action plan of 4 to 6 concrete steps
that campus staff should take immediately.

Respond with ONLY a raw JSON array of strings (no markdown, no backticks, no extra text):
["step one", "step two", "step three", "step four"]

Each step must be one short imperative sentence. Prioritise life safety first,
then containment, then dispatch of the right team, then escalation."""


# ---------------------------------------------------------------------------
# Deterministic fallback plans (no external calls, always available)
# ---------------------------------------------------------------------------
FALLBACK_PLANS = {
    "FIRE": [
        "Alert nearby students and staff immediately.",
        "Evacuate the affected area using the nearest safe exit.",
        "Isolate the electrical supply to the area if it is safe to do so.",
        "Dispatch the Fire & Safety Team to the location.",
        "Restrict entry and keep access routes clear for responders.",
        "Escalate to campus security and, if required, the municipal fire service.",
    ],
    "MEDICAL": [
        "Do not move the patient unless they are in immediate danger.",
        "Dispatch the Medical Team with a first-aid kit to the location.",
        "Alert the campus medical centre to prepare for the patient.",
        "Keep the area clear so responders can reach the patient quickly.",
        "Contact the patient's emergency contact once they are stable.",
    ],
    "ACCIDENT": [
        "Secure the accident site and stop any ongoing activity nearby.",
        "Dispatch the Medical Team to provide first aid.",
        "Check the area for further hazards before moving anyone.",
        "Record witness details and photograph the site for the incident report.",
        "Escalate to campus administration if an injury is serious.",
    ],
    "SECURITY": [
        "Alert the Security Team and share the exact location.",
        "Move students and staff away from the affected area.",
        "Lock down or restrict access to the building if the threat is active.",
        "Preserve CCTV footage covering the time of the incident.",
        "Escalate to local police if there is any threat to life.",
    ],
    "ELECTRICAL": [
        "Keep everyone away from the affected equipment and wiring.",
        "Cut power to the affected circuit or area from the main panel.",
        "Dispatch the Electrical Team to inspect and isolate the fault.",
        "Check for smoke or burning smell and escalate to Fire & Safety if present.",
        "Keep the area out of use until an electrician clears it.",
    ],
    "INFRASTRUCTURE": [
        "Cordon off the affected area to prevent access.",
        "Dispatch the Maintenance Team to assess the damage.",
        "Shut off water or utility supply to the area if it is leaking.",
        "Check surrounding structures for related damage.",
        "Schedule repair and log the issue for follow-up.",
    ],
    "OTHER": [
        "Confirm the details of the report with the person who submitted it.",
        "Send campus security to assess the situation on the ground.",
        "Keep bystanders at a safe distance until the situation is understood.",
        "Assign the most suitable response team once the nature is confirmed.",
        "Escalate to campus administration if the situation worsens.",
    ],
}


def fallback_action_plan(incident_type: str, severity: str = "") -> list:
    plan = list(FALLBACK_PLANS.get((incident_type or "OTHER").upper(), FALLBACK_PLANS["OTHER"]))
    if (severity or "").upper() == "CRITICAL":
        plan.append("Treat as CRITICAL: notify the campus emergency coordinator without delay.")
    return plan


# ---------------------------------------------------------------------------
# Groq-backed plan
# ---------------------------------------------------------------------------
def _extract_json_array(raw_text: str):
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)


def groq_action_plan(description: str, incident_type: str, severity: str, location: str = "") -> list:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not configured")

    user_prompt = (
        f"Incident description: {description}\n"
        f"Classified type: {incident_type}\n"
        f"Severity: {severity}\n"
    )
    if location:
        user_prompt += f"Campus location: {location}\n"

    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": ACTION_PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        timeout=8,
    )
    response.raise_for_status()
    raw_text = response.json()["choices"][0]["message"]["content"]
    parsed = _extract_json_array(raw_text)

    # Validate strictly — never trust raw model output.
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("Action plan was not a non-empty JSON array")
    steps = [str(s).strip()[:200] for s in parsed if str(s).strip()]
    if not steps:
        raise ValueError("Action plan contained no usable steps")
    return steps[:8]


def generate_action_plan(description: str, incident_type: str, severity: str, location: str = ""):
    """
    Main entry point. Always returns (steps, source) — never raises.
    """
    if os.getenv("GROQ_API_KEY", "").strip():
        try:
            return groq_action_plan(description, incident_type, severity, location), "AI Analysis"
        except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass  # fall through to the deterministic plan
    return fallback_action_plan(incident_type, severity), "Fallback Analysis"
