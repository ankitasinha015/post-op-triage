"""
Risk Assessor Agent (Claude Sonnet).

Agentic clinical investigator that autonomously examines patient data through
tool calls — checking symptom trends, vital trajectories, medication masking,
and flagging gaps for the Conversationalist to probe on the next turn.

Runs in background thread after each Conversationalist turn.
"""

import json
import logging
import anthropic
from src import db
from src.red_flags import get_flags_for_session, format_flags_for_prompt
from src.clinical_knowledge import (
    get_surgery_knowledge, get_medication_context,
    get_vital_reasoning, check_med_masking,
)
from src.synthetic_scenarios import get_risk_assessor_examples

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6

SYSTEM_PROMPT = """You are an experienced clinical risk assessor investigating a post-operative patient's chart. \
You think like a nurse with 20 years of experience — you don't just check boxes, you actively INVESTIGATE \
the data, looking for patterns, trajectories, and combinations.

You have TOOLS to examine patient data. Use them to build your clinical picture before making your assessment.

PATIENT OVERVIEW:
{patient_context}

{clinical_knowledge}

{vital_reasoning}

{red_flag_matrix}

{reasoning_examples}

HOW YOU INVESTIGATE:

1. START with trends. Use get_symptom_trend and get_vital_trend to see if things are improving \
or worsening. A trajectory tells you more than a snapshot.

2. CHECK for medication masking. If the patient is on NSAIDs or opioids, use check_med_context \
to see if medications could be hiding the true clinical picture.

3. NOTICE what's missing. Use get_time_since_last to check for gaps — a patient who hasn't \
mentioned mobility in 3 days post-knee may not be moving, which is itself a DVT risk factor.

4. FLAG gaps for follow-up. If you identify questions the Conversationalist should ask next turn, \
use flag_investigation_gap. Be specific: "Ask about wound drainage character — is it serous or purulent?"

5. WRITE your final assessment. When you've gathered enough information, use write_risk_alert \
with your severity level and detailed clinical reasoning.

IMPORTANT:
- You are NOT talking to the patient. You are producing an internal clinical analysis.
- Use 2-5 tools to investigate before writing your final assessment.
- Always end with write_risk_alert to record your findings.
- If tools return unexpected errors, skip and continue investigating with remaining tools."""

# ── Tool definitions for the Risk Assessor ──────────────────────────────────

RISK_ASSESSOR_TOOLS = [
    {
        "name": "get_symptom_trend",
        "description": (
            "Get the trend for a specific symptom over time. Returns a list of "
            "{severity, timestamp} entries showing how this symptom has changed. "
            "Use to detect worsening, improvement, or reversal patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom_name": {
                    "type": "string",
                    "description": "Name of the symptom to check trend for, e.g. 'pain', 'swelling', 'wound_warmth'",
                },
            },
            "required": ["symptom_name"],
        },
    },
    {
        "name": "get_vital_trend",
        "description": (
            "Get the trend for a specific vital sign over time. Returns a list of "
            "{value, unit, timestamp} entries. Use to detect climbing temperature, "
            "sustained tachycardia, or dropping SpO2."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vital_type": {
                    "type": "string",
                    "description": "Type of vital sign: 'temperature', 'heart_rate', 'blood_pressure', 'respiratory_rate', 'spo2'",
                    "enum": ["temperature", "heart_rate", "blood_pressure", "respiratory_rate", "spo2"],
                },
            },
            "required": ["vital_type"],
        },
    },
    {
        "name": "check_med_context",
        "description": (
            "Analyze whether current medications could be masking a symptom. "
            "For example, NSAIDs suppress fever — a 'normal' temperature on ibuprofen "
            "might actually be febrile. Returns a clinical masking analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptom_name": {
                    "type": "string",
                    "description": "The symptom that might be masked, e.g. 'fever', 'pain', 'swelling'",
                },
            },
            "required": ["symptom_name"],
        },
    },
    {
        "name": "get_time_since_last",
        "description": (
            "Check how long since the patient last reported a specific type of event. "
            "Use to detect gaps — e.g., no mobility mention in 3 days post-knee is concerning. "
            "Returns hours since last report, or 'never reported'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Type of event to check: 'symptom', 'vital', 'medication', 'mobility', 'bowel'",
                },
            },
            "required": ["event_type"],
        },
    },
    {
        "name": "flag_investigation_gap",
        "description": (
            "Flag a question for the Conversationalist to ask the patient on the next turn. "
            "Use when your investigation reveals something that needs patient input to resolve. "
            "Be specific about what to ask and why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The specific question to ask, e.g. 'Ask about wound drainage character — is it thin/watery or thick/cloudy?'",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level for this question.",
                    "enum": ["high", "medium", "low"],
                },
            },
            "required": ["question", "priority"],
        },
    },
    {
        "name": "write_risk_alert",
        "description": (
            "Write your final risk assessment after investigating. This records the severity, "
            "reasoning, and triggered signals. ALWAYS call this as your final tool to complete "
            "the assessment."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "score": {
                    "type": "integer",
                    "description": "Risk score 0-100. 0-20=normal, 21-40=note, 41-60=review, 61-80=urgent, 81-100=emergency.",
                    "minimum": 0,
                    "maximum": 100,
                },
                "triggered_signals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of red-flag signal names that apply from the matrix.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "3-5 sentence clinical reasoning. What patterns you found, what concerns you, what's reassuring.",
                },
            },
            "required": ["score", "triggered_signals", "reasoning"],
        },
    },
]


# ── Tool execution ──────────────────────────────────────────────────────────

def _execute_risk_tool(session_id: str, tool_name: str, tool_input: dict) -> str:
    """Execute a Risk Assessor tool call and return a result string."""
    session = db.get_session(session_id)
    if not session:
        return "Error: session not found"

    try:
        if tool_name == "get_symptom_trend":
            symptom_name = tool_input["symptom_name"].lower()
            symptoms = db.get_symptoms(session_id)
            matches = [
                {"severity": s["severity"], "timestamp": s["logged_at"],
                 "free_text": s.get("free_text", "")}
                for s in symptoms if s["name"].lower() == symptom_name
            ]
            if not matches:
                return f"No records found for symptom '{symptom_name}'. It has not been reported."
            trend = "STABLE"
            if len(matches) >= 2:
                delta = matches[-1]["severity"] - matches[0]["severity"]
                if delta > 0:
                    trend = f"WORSENING ({matches[0]['severity']} -> {matches[-1]['severity']})"
                elif delta < 0:
                    trend = f"IMPROVING ({matches[0]['severity']} -> {matches[-1]['severity']})"
            return json.dumps({"entries": matches, "count": len(matches), "trend": trend})

        elif tool_name == "get_vital_trend":
            vital_type = tool_input["vital_type"]
            vitals = db.get_vitals(session_id)
            matches = [
                {"value": v["value"], "unit": v["unit"], "timestamp": v["logged_at"]}
                for v in vitals if v["type"] == vital_type
            ]
            if not matches:
                return f"No records found for vital '{vital_type}'. It has not been measured."
            trend = "STABLE"
            if len(matches) >= 2:
                delta = matches[-1]["value"] - matches[0]["value"]
                if abs(delta) > 0.5:
                    trend = f"{'RISING' if delta > 0 else 'FALLING'} ({matches[0]['value']} -> {matches[-1]['value']})"
            return json.dumps({"entries": matches, "count": len(matches), "trend": trend})

        elif tool_name == "check_med_context":
            symptom_name = tool_input["symptom_name"]
            meds = db.get_meds(session_id)
            med_names = list(set(m["med_name"] for m in meds))
            if not med_names:
                return "No medications recorded for this patient. No masking analysis possible."
            return check_med_masking(symptom_name, med_names)

        elif tool_name == "get_time_since_last":
            event_type = tool_input["event_type"]
            # Check different tables based on event type
            if event_type == "symptom":
                symptoms = db.get_symptoms(session_id)
                if not symptoms:
                    return "No symptoms ever reported in this session."
                last = symptoms[-1]["logged_at"]
                return f"Last symptom reported at {last}. Total symptoms logged: {len(symptoms)}."
            elif event_type == "vital":
                vitals = db.get_vitals(session_id)
                if not vitals:
                    return "No vitals ever recorded in this session."
                last = vitals[-1]["logged_at"]
                return f"Last vital recorded at {last}. Total vitals logged: {len(vitals)}."
            elif event_type == "medication":
                meds = db.get_meds(session_id)
                if not meds:
                    return "No medications recorded. Patient may not be taking prescribed meds — worth asking."
                last = meds[-1]["logged_at"]
                return f"Last medication logged at {last}. Meds on record: {', '.join(set(m['med_name'] for m in meds))}."
            elif event_type in ("mobility", "bowel"):
                # Search symptoms for mobility/bowel mentions
                symptoms = db.get_symptoms(session_id)
                keywords = {
                    "mobility": ["mobility", "walking", "movement", "pt", "physical_therapy", "exercise", "steps"],
                    "bowel": ["bowel", "constipation", "stool", "gas", "flatulence", "bm"],
                }
                relevant = [
                    s for s in symptoms
                    if any(kw in s["name"].lower() for kw in keywords.get(event_type, []))
                ]
                if not relevant:
                    return f"'{event_type}' has NEVER been reported this session. This may be a gap worth investigating."
                last = relevant[-1]["logged_at"]
                return f"Last '{event_type}'-related report at {last}. Found {len(relevant)} related entries."
            else:
                return f"Unknown event type '{event_type}'. Supported: symptom, vital, medication, mobility, bowel."

        elif tool_name == "flag_investigation_gap":
            gap_id = db.write_investigation_gap(
                session_id=session_id,
                question=tool_input["question"],
                priority=tool_input["priority"],
            )
            return f"Investigation gap flagged (ID: {gap_id}, priority: {tool_input['priority']}). Conversationalist will see this on next turn."

        elif tool_name == "write_risk_alert":
            score = max(0, min(100, tool_input["score"]))
            triggered = tool_input.get("triggered_signals", [])
            reasoning = tool_input.get("reasoning", "")

            db.write_risk_score(
                session_id=session_id,
                score=score,
                triggered_signals=triggered,
                reasoning=reasoning,
            )

            return f"Risk assessment recorded: score={score}/100, signals={triggered}. Escalator will generate nurse alert."

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        logger.error(f"Risk Assessor tool error ({tool_name}): {e}")
        return f"Tool error ({tool_name}): {e}"


# ── Main agent loop ─────────────────────────────────────────────────────────

def assess_risk(client: anthropic.Anthropic, session_id: str) -> dict | None:
    """Run agentic risk assessment on the current session state.

    The Risk Assessor autonomously investigates patient data through tool calls,
    decides what to examine, flags gaps for the Conversationalist, and produces
    a final risk score. Returns the assessment dict or None on failure.
    """
    session = db.get_session(session_id)
    if not session:
        return None

    patient_context = db.build_patient_context(session_id)
    flags = get_flags_for_session(session["surgery_type"], session["recovery_day"])
    red_flag_matrix = format_flags_for_prompt(flags)

    surgery_knowledge = get_surgery_knowledge(session["surgery_type"])
    meds = db.get_meds(session_id)
    med_names = list(set(m["med_name"] for m in meds))
    med_context = get_medication_context(med_names)
    vital_reasoning = get_vital_reasoning()
    reasoning_examples = get_risk_assessor_examples()

    clinical_knowledge = surgery_knowledge
    if med_context:
        clinical_knowledge += "\n\n" + med_context

    system_prompt = SYSTEM_PROMPT.format(
        patient_context=patient_context,
        clinical_knowledge=clinical_knowledge,
        vital_reasoning=vital_reasoning,
        red_flag_matrix=red_flag_matrix,
        reasoning_examples=reasoning_examples,
    )

    messages = [
        {
            "role": "user",
            "content": "Investigate the patient's current clinical picture using your tools. "
                       "Check trends, look for masking, identify gaps, then write your risk assessment.",
        }
    ]

    iteration = 0
    tool_errors = 0
    final_assessment = None

    while iteration < MAX_ITERATIONS:
        iteration += 1

        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=RISK_ASSESSOR_TOOLS,
                messages=messages,
            )
        except Exception as e:
            logger.error(f"Risk Assessor API error on iteration {iteration}: {e}")
            break

        tool_calls = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        # No tool calls = agent is done
        if not tool_calls:
            if text_blocks:
                logger.info(f"Risk Assessor finished after {iteration} iterations (text response)")
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tc in tool_calls:
            result = _execute_risk_tool(session_id, tc.name, tc.input)

            if result.startswith("Tool error"):
                tool_errors += 1

            # Check if this was write_risk_alert (final tool)
            if tc.name == "write_risk_alert":
                final_assessment = {
                    "score": max(0, min(100, tc.input.get("score", 0))),
                    "triggered_signals": tc.input.get("triggered_signals", []),
                    "reasoning": tc.input.get("reasoning", ""),
                }

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

        # Abort if too many tool errors
        if tool_errors >= 3:
            logger.warning(f"Risk Assessor aborting: {tool_errors} tool errors. Falling back.")
            break

        # If we got a final assessment, we're done
        if final_assessment:
            logger.info(
                f"Risk Assessor completed: score={final_assessment['score']}, "
                f"iterations={iteration}, tool_errors={tool_errors}"
            )
            return final_assessment

    # Fallback: if agent didn't produce write_risk_alert, do single-shot
    if not final_assessment:
        logger.warning("Risk Assessor did not produce write_risk_alert. Using fallback single-shot.")
        return _fallback_assessment(client, session_id, system_prompt)

    return final_assessment


def _fallback_assessment(client: anthropic.Anthropic, session_id: str, system_prompt: str) -> dict | None:
    """Fallback single-shot assessment if the agent loop fails."""
    fallback_prompt = system_prompt + (
        "\n\nProduce your assessment as JSON only (no tools available):\n"
        '{"score": <0-100>, "triggered_signals": [...], "reasoning": "..."}'
    )
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=512,
            system=[{"type": "text", "text": fallback_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "Assess the patient's current risk based on all available data."}],
        )

        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        assessment = json.loads(text)
        score = max(0, min(100, int(assessment.get("score", 0))))
        triggered = assessment.get("triggered_signals", [])
        reasoning = assessment.get("reasoning", "")

        db.write_risk_score(session_id=session_id, score=score,
                            triggered_signals=triggered, reasoning=reasoning)

        return {"score": score, "triggered_signals": triggered, "reasoning": reasoning}

    except Exception as e:
        logger.error(f"Risk Assessor fallback also failed: {e}")
        return None
