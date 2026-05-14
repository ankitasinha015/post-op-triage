"""Tests for Risk Assessor investigation tools (no API calls)."""

import json
from src import db
from src.agents.risk_assessor import _execute_risk_tool, RISK_ASSESSOR_TOOLS


class TestToolDefinitions:
    def test_six_tools_defined(self):
        assert len(RISK_ASSESSOR_TOOLS) == 6

    def test_all_tools_have_required_fields(self):
        for tool in RISK_ASSESSOR_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_names(self):
        names = {t["name"] for t in RISK_ASSESSOR_TOOLS}
        expected = {
            "get_symptom_trend", "get_vital_trend", "check_med_context",
            "get_time_since_last", "flag_investigation_gap", "write_risk_alert",
        }
        assert names == expected


class TestGetSymptomTrend:
    def test_worsening_trend(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "get_symptom_trend", {"symptom_name": "pain"})
        data = json.loads(result)
        assert data["trend"].startswith("WORSENING")
        assert data["count"] == 2

    def test_no_data(self, session_id):
        result = _execute_risk_tool(session_id, "get_symptom_trend", {"symptom_name": "pain"})
        assert "not been reported" in result

    def test_single_entry(self, session_id):
        db.log_symptom(session_id, "nausea", 4)
        result = _execute_risk_tool(session_id, "get_symptom_trend", {"symptom_name": "nausea"})
        data = json.loads(result)
        assert data["trend"] == "STABLE"
        assert data["count"] == 1


class TestGetVitalTrend:
    def test_single_reading(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "get_vital_trend", {"vital_type": "temperature"})
        data = json.loads(result)
        assert data["count"] == 1
        assert data["entries"][0]["value"] == 100.2

    def test_rising_trend(self, session_id):
        db.log_vital(session_id, "temperature", 99.5, "F")
        db.log_vital(session_id, "temperature", 101.2, "F")
        result = _execute_risk_tool(session_id, "get_vital_trend", {"vital_type": "temperature"})
        data = json.loads(result)
        assert "RISING" in data["trend"]

    def test_no_data(self, session_id):
        result = _execute_risk_tool(session_id, "get_vital_trend", {"vital_type": "spo2"})
        assert "not been measured" in result


class TestCheckMedContext:
    def test_masking_detected(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "check_med_context", {"symptom_name": "fever"})
        assert "WARNING" in result

    def test_no_meds(self, session_id):
        result = _execute_risk_tool(session_id, "check_med_context", {"symptom_name": "fever"})
        assert "No medications recorded" in result


class TestGetTimeSinceLast:
    def test_symptom_reported(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "get_time_since_last", {"event_type": "symptom"})
        assert "Last symptom" in result

    def test_no_vitals(self, session_id):
        result = _execute_risk_tool(session_id, "get_time_since_last", {"event_type": "vital"})
        assert "No vitals" in result

    def test_mobility_never_reported(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "get_time_since_last", {"event_type": "mobility"})
        assert "NEVER been reported" in result

    def test_medication_info(self, session_with_data):
        result = _execute_risk_tool(session_with_data, "get_time_since_last", {"event_type": "medication"})
        assert "ibuprofen" in result or "acetaminophen" in result

    def test_unknown_event_type(self, session_id):
        result = _execute_risk_tool(session_id, "get_time_since_last", {"event_type": "magic"})
        assert "Unknown event type" in result


class TestFlagInvestigationGap:
    def test_creates_gap(self, session_id):
        result = _execute_risk_tool(session_id, "flag_investigation_gap", {
            "question": "Ask about wound drainage",
            "priority": "high",
        })
        assert "flagged" in result
        gaps = db.get_investigation_gaps(session_id)
        assert len(gaps) == 1
        assert gaps[0]["question"] == "Ask about wound drainage"


class TestWriteRiskAlert:
    def test_records_score(self, session_id):
        result = _execute_risk_tool(session_id, "write_risk_alert", {
            "score": 55,
            "triggered_signals": ["pain_worsening", "fever_persistent"],
            "reasoning": "Pain reversed and fever appeared on day 7.",
        })
        assert "recorded" in result
        scores = db.get_risk_scores(session_id)
        assert len(scores) == 1
        assert scores[0]["score"] == 55

    def test_score_clamping(self, session_id):
        _execute_risk_tool(session_id, "write_risk_alert", {
            "score": 150,
            "triggered_signals": [],
            "reasoning": "Test",
        })
        scores = db.get_risk_scores(session_id)
        assert scores[0]["score"] == 100

    def test_nonexistent_session(self):
        result = _execute_risk_tool("fake-session", "get_symptom_trend", {"symptom_name": "pain"})
        assert "error" in result.lower() or "not found" in result.lower()
