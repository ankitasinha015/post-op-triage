"""
Guardrails for the triage pipeline.

Five layers of protection that validate agent outputs BEFORE they reach
the patient or the database. Prompts are suggestions — guardrails are enforcement.

Layer 1: Emergency keyword bypass — catches life-threatening phrases regardless of agent output
Layer 2: Output content filter — blocks diagnosis/prescription language in patient-facing replies
Layer 3: Hallucination detector — verifies Risk Assessor signals against actual patient data
Layer 4: Score sanity check — catches wildly inappropriate risk scores
Layer 5: Tool input validator — sanitizes and rejects bad tool call inputs
"""

import re
from src import db
from src.clinical_knowledge import check_symptoms_vs_expected


# ──────────────────────────────────────────────
# LAYER 1: Emergency Keyword Bypass
# ──────────────────────────────────────────────
# These phrases bypass the entire agent pipeline.
# If a patient says any of these, we immediately create a 911-now alert
# regardless of what the Conversationalist or Risk Assessor think.

EMERGENCY_PHRASES = [
    r"\bcan'?t\s+breathe?\b",
    r"\bcan'?t\s+catch\s+(my\s+)?breath\b",
    r"\bchest\s+pain\b",
    r"\bchest\s+tight(ness)?\b",
    r"\bheart\s+attack\b",
    r"\bstroke\b",
    r"\bseizure\b",
    r"\bpass(ed|ing)\s+out\b",
    r"\bfaint(ed|ing)\b",
    r"\bunconscious\b",
    r"\buncontrolled\s+bleed(ing)?\b",
    r"\bbleed(ing)?\b.{0,20}\b(won'?t|wont|doesn'?t|doesnt|does\s+not|will\s+not|not)\s+stop\b",
    r"\bsoaked?\s+(through|in)\s+blood\b",
    r"\bcall\s+911\b",
    r"\bsuicid(e|al)\b",
    r"\bwant\s+to\s+(die|hurt\s+myself|kill\s+myself)\b",
    r"\boverdos(e|ed|ing)\b",
    r"\bblue\s+(lips?|fingers?|skin)\b",
    r"\bcoughing\s+(up\s+)?blood\b",
    r"\bvomiting\s+blood\b",
    r"\bsevere\s+allergic\b",
    r"\banaphy?lax(is|tic)\b",
    r"\bthroat\s+(is\s+)?(closing|swelling|swollen)\b",
]

_EMERGENCY_PATTERNS = [re.compile(p, re.IGNORECASE) for p in EMERGENCY_PHRASES]


def check_emergency_bypass(user_message: str) -> dict | None:
    """Check if the patient's message contains emergency phrases.
    Returns an alert dict if triggered, None otherwise.
    This runs BEFORE any agent — it's the fastest path to escalation."""
    matched = []
    for pattern in _EMERGENCY_PATTERNS:
        if pattern.search(user_message):
            matched.append(pattern.pattern)

    if not matched:
        return None

    return {
        "severity": "911-now",
        "summary": f"EMERGENCY KEYWORDS DETECTED in patient message. Matched: {', '.join(matched[:3])}",
        "signals": ["emergency_bypass"] + matched[:5],
        "recommended_action": (
            "This alert was triggered by emergency keywords in the patient's message, "
            "bypassing normal risk assessment. Immediate clinical review required. "
            "If patient is experiencing a life-threatening emergency, instruct them to call 911."
        ),
    }


# ──────────────────────────────────────────────
# LAYER 2: Output Content Filter
# ──────────────────────────────────────────────
# Catches when the Conversationalist crosses the line from
# data collection into diagnosis or prescription.

DIAGNOSIS_PATTERNS = [
    r"\byou\s+(have|probably\s+have|likely\s+have|might\s+have|could\s+have)\s+(an?\s+)?(infection|dvt|blood\s+clot|sepsis|pneumonia|pe\b|pulmonary\s+embolism)",
    r"\bI\s+think\s+(you|this)\s+(have|is|could\s+be|might\s+be)\b",
    r"\bmy\s+diagnosis\b",
    r"\bI('m|\s+am)\s+diagnos(ing|e)\b",
    r"\bthis\s+(is|looks\s+like|sounds\s+like)\s+(an?\s+)?(infection|dvt|clot|sepsis)\b",
]

PRESCRIPTION_PATTERNS = [
    r"\byou\s+should\s+take\b",
    r"\btake\s+\d+\s*mg\b",
    r"\bI('d|'ll|\s+would)\s+recommend\s+(taking|starting|increasing)\b",
    r"\bincrease\s+your\s+(dose|dosage|medication)\b",
    r"\bstop\s+taking\b",
    r"\bI('m|\s+am)\s+prescrib(ing|e)\b",
    r"\bstart\s+(taking|a\s+course\s+of)\b",
]

ALARM_PATTERNS = [
    r"\bgo\s+to\s+(the\s+)?(ER|emergency\s+room|hospital)\s+(right\s+)?(now|immediately)\b",
    r"\bcall\s+(911|an?\s+ambulance|emergency)\s+(right\s+)?(now|immediately)\b",
    r"\bthis\s+is\s+(an?\s+)?emergency\b",
    r"\byou('re|\s+are)\s+in\s+danger\b",
]

_DIAGNOSIS_COMPILED = [re.compile(p, re.IGNORECASE) for p in DIAGNOSIS_PATTERNS]
_PRESCRIPTION_COMPILED = [re.compile(p, re.IGNORECASE) for p in PRESCRIPTION_PATTERNS]
_ALARM_COMPILED = [re.compile(p, re.IGNORECASE) for p in ALARM_PATTERNS]


class GuardrailViolation:
    def __init__(self, violation_type: str, matched_text: str, original_reply: str):
        self.violation_type = violation_type
        self.matched_text = matched_text
        self.original_reply = original_reply


def check_output_content(reply: str) -> GuardrailViolation | None:
    """Check the Conversationalist's reply for diagnosis, prescription, or alarm language.
    Returns a violation if found, None if clean."""
    for pattern in _DIAGNOSIS_COMPILED:
        match = pattern.search(reply)
        if match:
            return GuardrailViolation("diagnosis", match.group(), reply)

    for pattern in _PRESCRIPTION_COMPILED:
        match = pattern.search(reply)
        if match:
            return GuardrailViolation("prescription", match.group(), reply)

    for pattern in _ALARM_COMPILED:
        match = pattern.search(reply)
        if match:
            return GuardrailViolation("alarm", match.group(), reply)

    return None


def sanitize_reply(reply: str, violation: GuardrailViolation) -> str:
    """Replace a violating reply with a safe alternative that still
    acknowledges the patient's concern without crossing the line."""
    safe_replies = {
        "diagnosis": (
            "I want to make sure your care team has all the details about what you're experiencing. "
            "I've logged everything you've told me, and a nurse will review it carefully. "
            "Is there anything else you'd like me to note?"
        ),
        "prescription": (
            "I'm not able to make medication recommendations — that's something your care team "
            "will handle based on the information I've collected. I've noted everything you've "
            "shared. Is there anything else about how you're feeling?"
        ),
        "alarm": (
            "I can hear this is concerning, and I want you to know I've recorded everything "
            "you've described. Your care team will be reviewing this information. "
            "If you feel this is a true emergency, please call 911 directly."
        ),
    }
    return safe_replies.get(violation.violation_type, reply)


# ──────────────────────────────────────────────
# LAYER 3: Hallucination Detector
# ──────────────────────────────────────────────
# Verifies that the Risk Assessor's triggered signals
# actually correspond to symptoms/vitals the patient reported.

SIGNAL_TO_DATA_MAP = {
    "fever_persistent": {"requires": "vitals", "vital_type": "temperature", "min_value": 101.5},
    "fever_high": {"requires": "vitals", "vital_type": "temperature", "min_value": 103.0},
    "tachycardia": {"requires": "vitals", "vital_type": "heart_rate", "min_value": 100},
    "low_spo2": {"requires": "vitals", "vital_type": "spo2", "max_value": 92},
    "dvt_leg_swelling": {"requires": "symptoms", "symptom_names": ["swelling", "leg_swelling", "edema"]},
    "dvt_calf_pain": {"requires": "symptoms", "symptom_names": ["calf_pain", "leg_pain", "calf_tenderness"]},
    "wound_redness_spreading": {"requires": "symptoms", "symptom_names": ["redness", "wound_redness", "erythema"]},
    "wound_discharge_purulent": {"requires": "symptoms", "symptom_names": ["discharge", "drainage", "wound_discharge", "pus"]},
    "wound_warmth": {"requires": "symptoms", "symptom_names": ["wound_warmth", "warmth", "hot_to_touch"]},
    "chest_pain": {"requires": "symptoms", "symptom_names": ["chest_pain", "chest_tightness", "chest_pressure"]},
    "shortness_of_breath": {"requires": "symptoms", "symptom_names": ["shortness_of_breath", "dyspnea", "breathing_difficulty", "breathlessness"]},
    "confusion": {"requires": "symptoms", "symptom_names": ["confusion", "disorientation", "altered_mental_status"]},
    "pain_worsening": {"requires": "symptom_trend", "symptom_name": "pain", "trend": "worsening"},
    "vomiting_persistent": {"requires": "symptoms", "symptom_names": ["vomiting", "emesis", "throwing_up"]},
    "bleeding_uncontrolled": {"requires": "symptoms", "symptom_names": ["bleeding", "hemorrhage", "uncontrolled_bleeding"]},
}


def check_hallucination(session_id: str, triggered_signals: list[str]) -> list[str]:
    """Check each triggered signal against actual patient data.
    Returns a list of signals that appear to be hallucinated
    (triggered without supporting data)."""
    if not triggered_signals:
        return []

    symptoms = db.get_symptoms(session_id)
    vitals = db.get_vitals(session_id)

    symptom_names = {s["name"].lower().replace(" ", "_") for s in symptoms}
    symptom_texts = " ".join(s.get("free_text", "") for s in symptoms).lower()

    hallucinated = []

    for signal in triggered_signals:
        check = SIGNAL_TO_DATA_MAP.get(signal)
        if not check:
            continue

        if check["requires"] == "vitals":
            matching_vitals = [v for v in vitals if v["type"] == check["vital_type"]]
            if not matching_vitals:
                hallucinated.append(signal)
                continue

            if "min_value" in check:
                if not any(v["value"] >= check["min_value"] for v in matching_vitals):
                    hallucinated.append(signal)
            elif "max_value" in check:
                if not any(v["value"] <= check["max_value"] for v in matching_vitals):
                    hallucinated.append(signal)

        elif check["requires"] == "symptoms":
            expected_names = check["symptom_names"]
            found = any(name in symptom_names for name in expected_names)
            if not found:
                found = any(name.replace("_", " ") in symptom_texts for name in expected_names)
            if not found:
                hallucinated.append(signal)

        elif check["requires"] == "symptom_trend":
            name = check["symptom_name"]
            matching = [s for s in symptoms if s["name"].lower() == name]
            if len(matching) < 2:
                hallucinated.append(signal)
            elif check["trend"] == "worsening":
                if matching[-1]["severity"] <= matching[0]["severity"]:
                    hallucinated.append(signal)

    return hallucinated


# ──────────────────────────────────────────────
# LAYER 4: Score Sanity Check
# ──────────────────────────────────────────────
# Catches wildly inappropriate risk scores.

EMERGENCY_SYMPTOM_NAMES = {
    "chest_pain", "chest_tightness", "shortness_of_breath",
    "breathing_difficulty", "uncontrolled_bleeding", "seizure",
}


def check_score_sanity(session_id: str, score: int, triggered_signals: list[str]) -> dict:
    """Validate risk score against the actual data.
    Returns adjustment dict: {adjusted_score, reason, was_adjusted}"""
    session = db.get_session(session_id)
    symptoms = db.get_symptoms(session_id)
    vitals = db.get_vitals(session_id)

    symptom_names = {s["name"].lower().replace(" ", "_") for s in symptoms}
    max_severity = max((s["severity"] for s in symptoms), default=0)

    has_emergency_symptom = bool(symptom_names & EMERGENCY_SYMPTOM_NAMES)
    has_high_fever = any(
        v["type"] == "temperature" and v["value"] >= 103.0
        for v in vitals
    )

    # Floor check: emergency symptoms should never score below 60
    if (has_emergency_symptom or has_high_fever) and score < 60:
        return {
            "adjusted_score": max(70, score),
            "reason": f"Score {score} too low for emergency-level symptoms. Raised to floor of 70.",
            "was_adjusted": True,
        }

    # Ceiling check: no symptoms or only mild ones shouldn't score above 40
    if not symptoms and not vitals and score > 30:
        return {
            "adjusted_score": min(20, score),
            "reason": f"Score {score} too high with no reported symptoms or vitals. Capped at 20.",
            "was_adjusted": True,
        }

    # Expected-symptom cap: if all symptoms are within expected ranges for
    # this surgery+day, the score should not exceed 25. This is the key
    # guardrail that prevents Day 1 normal inflammatory responses from
    # being scored as "urgent."
    if session and symptoms and score > 25 and not has_emergency_symptom and not has_high_fever:
        comparison = check_symptoms_vs_expected(
            session["surgery_type"], session["recovery_day"], symptoms
        )
        if comparison["all_expected"]:
            return {
                "adjusted_score": min(25, score),
                "reason": (
                    f"Score {score} too high — all reported symptoms are within expected "
                    f"ranges for {session['surgery_type']} Day {session['recovery_day']}. "
                    f"Capped at 25 (normal recovery)."
                ),
                "was_adjusted": True,
            }
        elif comparison["above_expected"] and not any(
            item["over_by"] >= 3 for item in comparison["above_expected"]
        ):
            cap = 40
            if score > cap:
                names = ", ".join(item["name"] for item in comparison["above_expected"])
                return {
                    "adjusted_score": cap,
                    "reason": (
                        f"Score {score} reduced — symptoms ({names}) are only slightly "
                        f"above expected for Day {session['recovery_day']}. Capped at {cap}."
                    ),
                    "was_adjusted": True,
                }

    # Consistency check: high score with no triggered signals
    if score > 60 and not triggered_signals:
        return {
            "adjusted_score": 40,
            "reason": f"Score {score} with no triggered signals. Reduced to 40 pending review.",
            "was_adjusted": True,
        }

    # Consistency check: low score with many triggered signals
    if score < 30 and len(triggered_signals) >= 3:
        return {
            "adjusted_score": max(45, score),
            "reason": f"Score {score} too low for {len(triggered_signals)} triggered signals. Raised to 45.",
            "was_adjusted": True,
        }

    return {"adjusted_score": score, "reason": "", "was_adjusted": False}


# ──────────────────────────────────────────────
# LAYER 5: Tool Input Validator
# ──────────────────────────────────────────────
# Sanitizes and validates tool call inputs before execution.

VALID_SYMPTOM_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\s\-]{0,99}$")
VALID_VITAL_TYPES = {"temperature", "heart_rate", "blood_pressure", "respiratory_rate", "spo2"}
VALID_MED_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\s\-\.]{0,99}$")


def validate_tool_input(tool_name: str, tool_input: dict) -> dict:
    """Validate and sanitize tool inputs.
    Returns {valid: bool, sanitized: dict, errors: list[str]}"""
    errors = []
    sanitized = dict(tool_input)

    if tool_name == "log_symptom":
        name = sanitized.get("name", "")
        if not name or not VALID_SYMPTOM_PATTERN.match(name):
            errors.append(f"Invalid symptom name: '{name}'")

        severity = sanitized.get("severity")
        if severity is None:
            errors.append("Missing severity")
        else:
            severity = int(severity)
            sanitized["severity"] = max(0, min(10, severity))
            if severity != sanitized["severity"]:
                errors.append(f"Severity {severity} clamped to {sanitized['severity']}")

        free_text = sanitized.get("free_text", "")
        if len(free_text) > 1000:
            sanitized["free_text"] = free_text[:1000]
            errors.append("free_text truncated to 1000 chars")

    elif tool_name == "log_vital":
        vital_type = sanitized.get("type", "")
        if vital_type not in VALID_VITAL_TYPES:
            errors.append(f"Invalid vital type: '{vital_type}'. Must be one of {VALID_VITAL_TYPES}")

        value = sanitized.get("value")
        if value is None:
            errors.append("Missing vital value")
        else:
            value = float(value)
            if value < 0 or value > 500:
                errors.append(f"Vital value {value} outside plausible range (0-500)")

    elif tool_name == "log_med_taken":
        med_name = sanitized.get("med_name", "")
        if not med_name or not VALID_MED_PATTERN.match(med_name):
            errors.append(f"Invalid medication name: '{med_name}'")

        dose = sanitized.get("dose", "unknown")
        if not dose:
            sanitized["dose"] = "unknown"
        if len(dose) > 100:
            sanitized["dose"] = dose[:100]

        if not sanitized.get("time"):
            sanitized["time"] = "recently"

    elif tool_name == "ask_clarifying":
        question = sanitized.get("question", "")
        if not question:
            errors.append("Missing clarifying question")
        if len(question) > 500:
            sanitized["question"] = question[:500]

    has_blocking_errors = any(
        "Invalid" in e or "Missing" in e
        for e in errors
        if "clamped" not in e and "truncated" not in e
    )

    return {
        "valid": not has_blocking_errors,
        "sanitized": sanitized,
        "errors": errors,
    }


# ──────────────────────────────────────────────
# Pipeline integration helper
# ──────────────────────────────────────────────

def run_guardrails_on_risk_assessment(session_id: str, assessment: dict) -> dict:
    """Run layers 3 and 4 on a risk assessment result.
    Returns the assessment with any adjustments applied."""
    if not assessment:
        return assessment

    score = assessment.get("score", 0)
    triggered = assessment.get("triggered_signals", [])
    reasoning = assessment.get("reasoning", "")

    # Layer 3: Hallucination check
    hallucinated = check_hallucination(session_id, triggered)
    if hallucinated:
        triggered = [s for s in triggered if s not in hallucinated]

    # Layer 4: Score sanity
    sanity = check_score_sanity(session_id, score, triggered)
    if sanity["was_adjusted"]:
        score = sanity["adjusted_score"]

    return {
        "score": score,
        "triggered_signals": triggered,
        "reasoning": reasoning,
        "guardrail_adjustments": {
            "hallucinated_signals": hallucinated,
            "score_adjusted": sanity["was_adjusted"],
            "original_score": assessment.get("score", 0),
            "sanity_reason": sanity.get("reason", ""),
        },
    }
