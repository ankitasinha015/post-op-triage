"""Tests for the five-layer guardrail system."""

from src.guardrails import (
    check_emergency_bypass, check_output_content,
    sanitize_reply, validate_tool_input,
    run_guardrails_on_risk_assessment,
)
from src import db


class TestEmergencyBypass:
    """Layer 1: Emergency keyword detection."""

    def test_detects_breathing_emergency(self):
        result = check_emergency_bypass("I can't breathe at all")
        assert result is not None
        assert result["severity"] == "911-now"

    def test_detects_chest_pain(self):
        result = check_emergency_bypass("I'm having chest pain")
        assert result is not None

    def test_detects_hemorrhage(self):
        result = check_emergency_bypass("the bleeding won't stop")
        assert result is not None

    def test_ignores_normal_message(self):
        result = check_emergency_bypass("My knee is a bit sore today")
        assert result is None

    def test_ignores_empty_message(self):
        result = check_emergency_bypass("")
        assert result is None

    def test_case_insensitive(self):
        result = check_emergency_bypass("I CAN'T BREATHE")
        assert result is not None


class TestOutputContentFilter:
    """Layer 2: Output content filtering."""

    def test_blocks_diagnosis(self):
        # Must match a DIAGNOSIS_PATTERN: "you have/probably have/likely have [infection/dvt/etc]"
        violation = check_output_content("You probably have an infection in your knee.")
        assert violation is not None
        assert violation.violation_type == "diagnosis"

    def test_blocks_prescription(self):
        violation = check_output_content("You should take more ibuprofen for the pain.")
        assert violation is not None
        assert violation.violation_type == "prescription"

    def test_allows_normal_response(self):
        violation = check_output_content("That sounds like your recovery is going well. How's the swelling?")
        assert violation is None

    def test_allows_symptom_discussion(self):
        violation = check_output_content("Thanks for telling me about the pain. Can you describe where it is?")
        assert violation is None

    def test_blocks_alarm_language(self):
        violation = check_output_content("Go to the ER immediately, this is serious!")
        assert violation is not None
        assert violation.violation_type == "alarm"


class TestSanitizeReply:
    def test_produces_safe_output(self):
        from src.guardrails import GuardrailViolation
        violation = GuardrailViolation("diagnosis", "you have an infection", "You have an infection.")
        result = sanitize_reply("You have an infection.", violation)
        assert "care team" in result.lower() or "nurse" in result.lower()
        assert len(result) > 20


class TestToolInputValidation:
    """Layer 5: Tool input validation."""

    def test_valid_symptom_input(self):
        result = validate_tool_input("log_symptom", {"name": "pain", "severity": 5})
        assert result["valid"] is True

    def test_rejects_extreme_severity(self):
        result = validate_tool_input("log_symptom", {"name": "pain", "severity": 50})
        # Should either clamp or reject
        if result["valid"]:
            assert result["sanitized"]["severity"] <= 10

    def test_valid_vital_input(self):
        result = validate_tool_input("log_vital", {"type": "temperature", "value": 100.2, "unit": "F"})
        assert result["valid"] is True

    def test_unknown_tool_passes_through(self):
        # Validator only validates known tools; unknown tools pass through
        result = validate_tool_input("hack_system", {"payload": "evil"})
        assert result["valid"] is True  # unknown tools aren't blocked at validation layer


class TestRiskAssessmentGuardrails:
    """Layers 3 & 4: Hallucination detection + score sanity."""

    def test_normal_assessment_passes(self, session_with_data):
        assessment = {
            "score": 35,
            "triggered_signals": ["pain_worsening"],
            "reasoning": "Pain has increased from 3 to 5, suggesting reversal of recovery trend.",
        }
        result = run_guardrails_on_risk_assessment(session_with_data, assessment)
        assert result["score"] == 35  # unchanged

    def test_extreme_score_gets_adjusted(self, session_with_data):
        assessment = {
            "score": 95,
            "triggered_signals": ["pain_worsening"],
            "reasoning": "Patient has mild pain increase.",
        }
        result = run_guardrails_on_risk_assessment(session_with_data, assessment)
        # Score should be adjusted down since only 1 mild signal
        # (exact behavior depends on guardrail implementation)
        assert "guardrail_adjustments" in result
