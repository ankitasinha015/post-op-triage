"""
Tool definitions for the Conversationalist agent.
Single source of truth: these schemas are passed via the Anthropic SDK tools parameter.
"""

from src import db

TOOL_DEFINITIONS = [
    {
        "name": "log_symptom",
        "description": (
            "Log a symptom the patient reported. Use this whenever the patient describes "
            "a physical sensation, complaint, or observable sign (pain, nausea, swelling, "
            "wound appearance, mental status change, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short symptom name, e.g. 'pain', 'nausea', 'wound_warmth', 'confusion', 'shortness_of_breath'",
                },
                "severity": {
                    "type": "integer",
                    "description": "Severity on a 0-10 scale. 0 = absent, 5 = moderate, 10 = worst imaginable.",
                    "minimum": 0,
                    "maximum": 10,
                },
                "free_text": {
                    "type": "string",
                    "description": "Patient's own words describing the symptom.",
                },
            },
            "required": ["name", "severity"],
        },
    },
    {
        "name": "log_vital",
        "description": (
            "Log a vital sign measurement the patient reported. "
            "ONLY use this when the patient gives you a SPECIFIC NUMBER — e.g. 'my temp is 99.2' or "
            "'my heart rate was 88'. Do NOT log vitals based on vague descriptions like 'I feel warm' "
            "or 'I think I had a fever' — those are symptoms, not vital measurements. "
            "Do NOT invent or estimate vital values."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Vital type: 'temperature', 'heart_rate', 'blood_pressure', 'respiratory_rate', 'spo2'",
                    "enum": ["temperature", "heart_rate", "blood_pressure", "respiratory_rate", "spo2"],
                },
                "value": {
                    "type": "number",
                    "description": "Numeric value of the measurement.",
                },
                "unit": {
                    "type": "string",
                    "description": "Unit of measurement, e.g. 'F', 'C', 'bpm', 'mmHg', '%'",
                },
            },
            "required": ["type", "value", "unit"],
        },
    },
    {
        "name": "log_med_taken",
        "description": (
            "Log a medication the patient has taken. Use when the patient mentions "
            "taking a pill, injection, or any prescribed/OTC medication. "
            "You MUST call this whenever the patient mentions taking any medication, "
            "even if they don't specify the exact dose or time — use 'unknown' for missing details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "med_name": {
                    "type": "string",
                    "description": "Name of the medication, e.g. 'ibuprofen', 'acetaminophen', 'oxycodone'",
                },
                "dose": {
                    "type": "string",
                    "description": "Dose taken, e.g. '400mg', '5mg', '2 tablets'. Use 'unknown' if patient didn't specify.",
                },
                "time": {
                    "type": "string",
                    "description": "When the medication was taken, e.g. '2 hours ago', '8:00 AM', 'this morning'. Use 'recently' if patient didn't specify.",
                },
            },
            "required": ["med_name"],
        },
    },
    {
        "name": "ask_clarifying",
        "description": (
            "Ask the patient a follow-up question to clarify a vague or ambiguous symptom. "
            "Use when the patient says something like 'I feel weird' or 'it hurts a bit' — "
            "probe for specifics before logging."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The clarifying question to ask the patient.",
                },
            },
            "required": ["question"],
        },
    },
]


def execute_tool(session_id: str, tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return a result string for the agent."""
    try:
        if tool_name == "log_symptom":
            row_id = db.log_symptom(
                session_id=session_id,
                name=tool_input["name"],
                severity=tool_input["severity"],
                free_text=tool_input.get("free_text", ""),
            )
            return f"Logged symptom '{tool_input['name']}' (severity {tool_input['severity']}/10). Record ID: {row_id}"

        elif tool_name == "log_vital":
            row_id = db.log_vital(
                session_id=session_id,
                vital_type=tool_input["type"],
                value=tool_input["value"],
                unit=tool_input["unit"],
            )
            return f"Logged vital '{tool_input['type']}': {tool_input['value']} {tool_input['unit']}. Record ID: {row_id}"

        elif tool_name == "log_med_taken":
            dose = tool_input.get("dose", "unknown")
            taken_at = tool_input.get("time", "recently")
            row_id = db.log_med_taken(
                session_id=session_id,
                med_name=tool_input["med_name"],
                dose=dose,
                taken_at=taken_at,
            )
            return f"Logged medication '{tool_input['med_name']}' ({dose}) taken at {taken_at}. Record ID: {row_id}"

        elif tool_name == "ask_clarifying":
            return f"Clarifying question noted: {tool_input['question']}"

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Tool error ({tool_name}): {e}"
