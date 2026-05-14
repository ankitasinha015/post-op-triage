"""
Escalator Agent (Claude Haiku).

Fast, cheap agent that translates Risk Assessor findings into actionable
nurse-facing alerts. Runs in the background thread after Risk Assessor.

Why a separate agent?
- The Risk Assessor thinks like a clinician (analytical, pattern-focused).
- The Escalator thinks like a charge nurse (action-focused, prioritized).
- Using Haiku keeps cost low (~$0.001/call) while adding clinical value.
"""

import anthropic
from src import db
from src.clinical_knowledge import get_surgery_knowledge

SYSTEM_PROMPT = """You are an experienced charge nurse translating a clinical risk assessment into \
an actionable alert for the bedside nurse. You write crisp, prioritized summaries that tell the \
nurse EXACTLY what to check and how urgently.

PATIENT:
- Name: {patient_name}
- Surgery: {surgery_type}, Recovery Day {recovery_day}

RISK ASSESSMENT (from automated clinical analysis):
- Score: {score}/100
- Triggered Signals: {signals}
- Clinical Reasoning: {reasoning}

{investigation_gaps}

SEVERITY GUIDE:
- routine (0-20): Normal recovery. Brief reassurance note.
- monitor (21-40): Worth watching. Note what to monitor and when to re-check.
- urgent (41-60): Nurse should assess soon. Specific exam points + timeline.
- critical (61-80): Nurse should assess NOW. Concrete actions in priority order.
- 911-now (81-100): Potential emergency. Immediate actions + who to call.

OUTPUT FORMAT (respond with ONLY this JSON):
{{
    "severity": "<routine|monitor|urgent|critical|911-now>",
    "headline": "<1 sentence: what's happening, stated plainly>",
    "actions": ["<specific action 1>", "<specific action 2>", ...],
    "reassess_in": "<timeframe, e.g. '2 hours', 'next shift', 'immediately'>",
    "rationale": "<1-2 sentences: why this matters clinically>"
}}

RULES:
- Be SPECIFIC. "Check wound" is useless. "Inspect knee incision for erythema, warmth, drainage" is useful.
- Match urgency to score. Don't escalate routine findings or downplay urgent ones.
- Include the "reassess_in" window — the nurse needs to know WHEN to check back.
- If investigation gaps are flagged, incorporate them into the actions.
- For routine scores, keep it brief and reassuring."""

# Score-to-severity mapping
_SEVERITY_MAP = [
    (81, "911-now"),
    (61, "critical"),
    (41, "urgent"),
    (21, "monitor"),
    (0, "routine"),
]


def _score_to_severity(score: int) -> str:
    for threshold, severity in _SEVERITY_MAP:
        if score >= threshold:
            return severity
    return "routine"


def escalate(client: anthropic.Anthropic, session_id: str, assessment: dict) -> dict | None:
    """Generate a nurse-facing alert from a Risk Assessor's output.

    Args:
        client: Anthropic API client
        session_id: Current session ID
        assessment: Dict with 'score', 'triggered_signals', 'reasoning'

    Returns:
        Parsed alert dict or None on failure
    """
    session = db.get_session(session_id)
    if not session:
        return None

    score = assessment.get("score", 0)

    # Skip Haiku call for very low-risk — save the API cost
    if score <= 15:
        alert = {
            "severity": "routine",
            "headline": "Recovery progressing normally. No concerns identified.",
            "actions": ["Continue routine monitoring"],
            "reassess_in": "next shift",
            "rationale": f"Risk score {score}/100 — all findings within expected range for "
                         f"{session['surgery_type']} Day {session['recovery_day']}.",
        }
        db.write_alert(
            session_id=session_id,
            severity="routine",
            summary=alert["headline"],
            signals=assessment.get("triggered_signals", []),
            recommended_action="; ".join(alert["actions"]),
        )
        return alert

    # Build investigation gaps context
    gaps = db.get_investigation_gaps(session_id, only_unaddressed=True)
    gaps_text = ""
    if gaps:
        gaps_text = "PENDING INVESTIGATION GAPS (Risk Assessor wants these checked):\n"
        for g in gaps:
            gaps_text += f"  [{g['priority'].upper()}] {g['question']}\n"

    signals_text = ", ".join(assessment.get("triggered_signals", [])) or "none"

    system_prompt = SYSTEM_PROMPT.format(
        patient_name=session["patient_name"],
        surgery_type=session["surgery_type"],
        recovery_day=session["recovery_day"],
        score=score,
        signals=signals_text,
        reasoning=assessment.get("reasoning", "No reasoning provided."),
        investigation_gaps=gaps_text,
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": "Generate the nurse alert based on this risk assessment.",
                }
            ],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        import json
        alert = json.loads(text)

    except Exception as e:
        # Fallback: generate a basic alert without LLM
        severity = _score_to_severity(score)
        alert = {
            "severity": severity,
            "headline": f"Risk score {score}/100 — {severity} level. {assessment.get('reasoning', '')[:100]}",
            "actions": [f"Review triggered signals: {signals_text}"],
            "reassess_in": "1 hour" if score >= 61 else "2 hours" if score >= 41 else "next shift",
            "rationale": f"Escalator agent failed ({e}). Displaying raw risk assessment.",
        }

    # Validate severity matches score (don't let Haiku under-escalate)
    expected_severity = _score_to_severity(score)
    severity_order = ["routine", "monitor", "urgent", "critical", "911-now"]
    alert_sev_idx = severity_order.index(alert.get("severity", "routine"))
    expected_sev_idx = severity_order.index(expected_severity)
    if alert_sev_idx < expected_sev_idx:
        alert["severity"] = expected_severity

    # Write to DB
    db.write_alert(
        session_id=session_id,
        severity=alert["severity"],
        summary=alert.get("headline", f"Risk score: {score}/100"),
        signals=assessment.get("triggered_signals", []),
        recommended_action="; ".join(alert.get("actions", [])),
    )

    return alert
