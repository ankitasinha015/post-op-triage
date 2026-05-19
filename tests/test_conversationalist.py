"""Tests for Conversationalist agent (no API calls)."""

from src import db
from src.agents.conversationalist import (
    _build_investigation_gaps_section, build_system_prompt, _strip_internal_reasoning,
)
from src.tools import TOOL_DEFINITIONS, execute_tool


class TestInvestigationGapsInjection:
    def test_no_gaps_returns_empty(self, session_id):
        result = _build_investigation_gaps_section(session_id)
        assert result == ""

    def test_gaps_included_in_output(self, session_id):
        db.write_investigation_gap(session_id, "Ask about wound drainage", "high")
        db.write_investigation_gap(session_id, "Check PT exercises", "medium")
        result = _build_investigation_gaps_section(session_id)
        assert "RISK ASSESSOR REQUESTS" in result
        assert "wound drainage" in result
        assert "PT exercises" in result
        assert "[!]" in result  # high priority marker
        assert "[-]" in result  # medium priority marker

    def test_addressed_gaps_excluded(self, session_id):
        gap_id = db.write_investigation_gap(session_id, "Old question", "low")
        db.mark_gap_addressed(gap_id)
        db.write_investigation_gap(session_id, "New question", "high")
        result = _build_investigation_gaps_section(session_id)
        assert "New question" in result
        assert "Old question" not in result

    def test_gaps_in_system_prompt(self, session_id):
        db.write_investigation_gap(session_id, "Check mobility status", "high")
        session = db.get_session(session_id)
        ctx = db.build_patient_context(session_id)
        prompt = build_system_prompt(session, ctx)
        assert "RISK ASSESSOR REQUESTS" in prompt
        assert "mobility status" in prompt


class TestToolDefinitions:
    def test_four_tools_defined(self):
        assert len(TOOL_DEFINITIONS) == 4

    def test_tool_names(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert names == {"log_symptom", "log_vital", "log_med_taken", "ask_clarifying"}


class TestToolExecution:
    def test_log_symptom(self, session_id):
        result = execute_tool(session_id, "log_symptom", {"name": "pain", "severity": 5})
        assert "Logged symptom" in result
        symptoms = db.get_symptoms(session_id)
        assert len(symptoms) == 1

    def test_log_vital(self, session_id):
        result = execute_tool(session_id, "log_vital", {"type": "temperature", "value": 100.5, "unit": "F"})
        assert "Logged vital" in result

    def test_log_med(self, session_id):
        result = execute_tool(session_id, "log_med_taken", {"med_name": "ibuprofen", "dose": "400mg", "time": "now"})
        assert "Logged medication" in result

    def test_ask_clarifying(self, session_id):
        result = execute_tool(session_id, "ask_clarifying", {"question": "Where is the pain?"})
        assert "Clarifying question" in result

    def test_unknown_tool(self, session_id):
        result = execute_tool(session_id, "hack_system", {})
        assert "Unknown tool" in result


class TestStripInternalReasoning:
    def test_clean_reply_unchanged(self):
        reply = "Thanks for sharing that, Jordan. Can you tell me where exactly the redness is?"
        assert _strip_internal_reasoning(reply) == reply

    def test_strips_my_thinking_prefix(self):
        reply = (
            "My thinking: On Day 1, redness is expected from surgical trauma. "
            "But spreading redness could signal infection.\n\n"
            "Thanks for telling me about that, Jordan. Can you describe where "
            "exactly the redness is — is it right at the incision sites, or has "
            "it spread beyond them?"
        )
        result = _strip_internal_reasoning(reply)
        assert "My thinking" not in result
        assert "Thanks for telling me" in result

    def test_strips_clinical_reasoning_prefix(self):
        reply = (
            "Clinical reasoning: DVT risk is elevated post-hip surgery.\n\n"
            "I hear you about the swelling. Can you tell me — is it in one leg or both?"
        )
        result = _strip_internal_reasoning(reply)
        assert "Clinical reasoning" not in result
        assert "I hear you" in result

    def test_strips_assessment_prefix(self):
        reply = (
            "My assessment: This pattern suggests possible infection.\n\n"
            "That's important to know. How long has the drainage been happening?"
        )
        result = _strip_internal_reasoning(reply)
        assert "My assessment" not in result
        assert "important to know" in result

    def test_empty_string(self):
        assert _strip_internal_reasoning("") == ""

    def test_none_returns_none(self):
        assert _strip_internal_reasoning(None) is None

    def test_no_conversational_content_returns_original(self):
        # If stripping would leave nothing, return original
        reply = "My thinking: just a note about clinical patterns."
        result = _strip_internal_reasoning(reply)
        assert result  # Should return something, not empty
