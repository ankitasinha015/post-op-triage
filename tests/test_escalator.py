"""Tests for the Escalator agent (no API calls)."""

from src import db
from src.agents.escalator import _score_to_severity, escalate


class TestSeverityMapping:
    def test_routine(self):
        assert _score_to_severity(10) == "routine"
        assert _score_to_severity(0) == "routine"
        assert _score_to_severity(20) == "routine"

    def test_monitor(self):
        assert _score_to_severity(21) == "monitor"
        assert _score_to_severity(40) == "monitor"

    def test_urgent(self):
        assert _score_to_severity(41) == "urgent"
        assert _score_to_severity(60) == "urgent"

    def test_critical(self):
        assert _score_to_severity(61) == "critical"
        assert _score_to_severity(80) == "critical"

    def test_emergency(self):
        assert _score_to_severity(81) == "911-now"
        assert _score_to_severity(100) == "911-now"


class TestLowScoreShortcut:
    def test_skips_api_for_low_score(self, session_id):
        assessment = {"score": 12, "triggered_signals": [], "reasoning": "Normal recovery"}
        # client=None works because we skip the API call for score <= 15
        result = escalate(None, session_id, assessment)
        assert result is not None
        assert result["severity"] == "routine"
        assert "normally" in result["headline"].lower() or "normal" in result["headline"].lower()

    def test_writes_alert_to_db(self, session_id):
        assessment = {"score": 10, "triggered_signals": [], "reasoning": "All clear"}
        escalate(None, session_id, assessment)
        alerts = db.get_alerts(session_id)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "routine"

    def test_threshold_boundary(self, session_id):
        # Score of 15 should still skip API
        result = escalate(None, session_id, {"score": 15, "triggered_signals": [], "reasoning": "Fine"})
        assert result is not None
        assert result["severity"] == "routine"

    def test_score_16_would_need_api(self, session_id):
        # Score of 16 should try API (will fail with None client)
        # But fallback should still produce an alert
        result = escalate(None, session_id, {"score": 16, "triggered_signals": [], "reasoning": "Mild"})
        assert result is not None  # fallback kicks in
        assert result["severity"] == "routine"  # 16 maps to routine


class TestNonexistentSession:
    def test_returns_none(self):
        result = escalate(None, "fake-session-id", {"score": 10, "triggered_signals": [], "reasoning": ""})
        assert result is None


class TestInvestigationGapsInEscalator:
    def test_gaps_available_for_escalator(self, session_id):
        db.write_investigation_gap(session_id, "Check wound drainage", "high")
        gaps = db.get_investigation_gaps(session_id)
        assert len(gaps) == 1
        # Escalator reads these when building its prompt (tested via integration)
