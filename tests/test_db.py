"""Tests for the database layer."""

from src import db


class TestSessionCRUD:
    def test_create_and_get_session(self):
        sid = db.create_session("Total Knee Replacement", 3, "Alex")
        session = db.get_session(sid)
        assert session is not None
        assert session["surgery_type"] == "Total Knee Replacement"
        assert session["recovery_day"] == 3
        assert session["patient_name"] == "Alex"

    def test_get_nonexistent_session(self):
        assert db.get_session("nonexistent-id") is None

    def test_default_patient_name(self):
        sid = db.create_session("Total Hip Replacement", 1)
        session = db.get_session(sid)
        assert session["patient_name"] == "Patient"


class TestSymptoms:
    def test_log_and_retrieve(self, session_id):
        row_id = db.log_symptom(session_id, "pain", 5, "aching")
        assert row_id > 0
        symptoms = db.get_symptoms(session_id)
        assert len(symptoms) == 1
        assert symptoms[0]["name"] == "pain"
        assert symptoms[0]["severity"] == 5

    def test_severity_clamping(self, session_id):
        db.log_symptom(session_id, "pain", 15)  # over max
        db.log_symptom(session_id, "pain", -5)  # under min
        symptoms = db.get_symptoms(session_id)
        assert symptoms[0]["severity"] == 10
        assert symptoms[1]["severity"] == 0

    def test_chronological_order(self, session_id):
        db.log_symptom(session_id, "pain", 3)
        db.log_symptom(session_id, "nausea", 5)
        db.log_symptom(session_id, "pain", 7)
        symptoms = db.get_symptoms(session_id)
        assert len(symptoms) == 3
        assert symptoms[0]["name"] == "pain"
        assert symptoms[2]["severity"] == 7


class TestVitals:
    def test_log_and_retrieve(self, session_id):
        db.log_vital(session_id, "temperature", 100.2, "F")
        vitals = db.get_vitals(session_id)
        assert len(vitals) == 1
        assert vitals[0]["type"] == "temperature"
        assert vitals[0]["value"] == 100.2


class TestMeds:
    def test_log_and_retrieve(self, session_id):
        db.log_med_taken(session_id, "ibuprofen", "400mg", "2 hours ago")
        meds = db.get_meds(session_id)
        assert len(meds) == 1
        assert meds[0]["med_name"] == "ibuprofen"


class TestMessages:
    def test_save_and_retrieve(self, session_id):
        db.save_message(session_id, "user", "My knee hurts")
        db.save_message(session_id, "assistant", "Tell me more about that.")
        msgs = db.get_messages(session_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_message_limit(self, session_id):
        for i in range(25):
            db.save_message(session_id, "user", f"Message {i}")
        msgs = db.get_messages(session_id, limit=10)
        assert len(msgs) == 10


class TestAlerts:
    def test_write_and_retrieve(self, session_id):
        db.write_alert(session_id, "urgent", "Possible infection",
                       signals=["fever_persistent", "wound_warmth"],
                       recommended_action="Check wound")
        alerts = db.get_alerts(session_id)
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "urgent"
        assert "fever_persistent" in alerts[0]["signals"]


class TestRiskScores:
    def test_write_and_retrieve(self, session_id):
        db.write_risk_score(session_id, 55, ["pain_worsening"], "Pain reversed")
        scores = db.get_risk_scores(session_id)
        assert len(scores) == 1
        assert scores[0]["score"] == 55
        assert "pain_worsening" in scores[0]["triggered_signals"]


class TestInvestigationGaps:
    def test_write_and_retrieve(self, session_id):
        gap_id = db.write_investigation_gap(session_id, "Ask about wound drainage", "high")
        gaps = db.get_investigation_gaps(session_id)
        assert len(gaps) == 1
        assert gaps[0]["question"] == "Ask about wound drainage"
        assert gaps[0]["priority"] == "high"
        assert gaps[0]["addressed"] == 0

    def test_mark_addressed(self, session_id):
        gap_id = db.write_investigation_gap(session_id, "Check mobility", "medium")
        db.mark_gap_addressed(gap_id)
        unaddressed = db.get_investigation_gaps(session_id, only_unaddressed=True)
        assert len(unaddressed) == 0
        all_gaps = db.get_investigation_gaps(session_id, only_unaddressed=False)
        assert len(all_gaps) == 1
        assert all_gaps[0]["addressed"] == 1

    def test_priority_ordering(self, session_id):
        db.write_investigation_gap(session_id, "Low priority", "low")
        db.write_investigation_gap(session_id, "High priority", "high")
        db.write_investigation_gap(session_id, "Medium priority", "medium")
        gaps = db.get_investigation_gaps(session_id)
        assert gaps[0]["priority"] == "high"
        assert gaps[1]["priority"] == "medium"
        assert gaps[2]["priority"] == "low"


class TestPatientContext:
    def test_build_with_data(self, session_with_data):
        ctx = db.build_patient_context(session_with_data)
        assert "TestPatient" in ctx
        assert "Total Knee Replacement" in ctx
        assert "WORSENING" in ctx  # pain trend 3->5
        assert "ibuprofen" in ctx

    def test_build_empty_session(self, session_id):
        ctx = db.build_patient_context(session_id)
        assert "None reported yet" in ctx or "None recorded yet" in ctx

    def test_nonexistent_session(self):
        ctx = db.build_patient_context("fake-id")
        assert ctx == ""


class TestPatientHistory:
    def test_save_and_retrieve(self, session_id):
        db.save_patient_history(
            session_id, "TestPatient", "Total Knee Replacement", 3,
            key_findings=["pain improving"],
            risk_level="low",
            unresolved_concerns=["mild swelling"],
            resolved_concerns=[],
            session_summary="Routine recovery"
        )
        history = db.get_patient_history("TestPatient")
        assert len(history) == 1
        assert history[0]["risk_level"] == "low"

    def test_excludes_current_session(self, session_id):
        db.save_patient_history(
            session_id, "TestPatient", "Total Knee Replacement", 3,
            key_findings=[], risk_level="low",
            unresolved_concerns=[], resolved_concerns=[],
            session_summary="Test"
        )
        history = db.get_patient_history("TestPatient", exclude_session_id=session_id)
        assert len(history) == 0


class TestWorklist:
    def test_get_all_sessions_with_risk_empty(self):
        sessions = db.get_all_sessions_with_risk()
        # At minimum returns sessions created by other tests (in-memory DB shared)
        assert isinstance(sessions, list)

    def test_get_all_sessions_with_risk_ordered(self):
        sid1 = db.create_session("Total Knee Replacement", 3, "LowRisk")
        sid2 = db.create_session("Total Hip Replacement", 5, "HighRisk")
        db.write_risk_score(sid1, 15, [], "routine recovery")
        db.write_risk_score(sid2, 75, ["dvt_leg_swelling"], "urgent DVT concern")

        sessions = db.get_all_sessions_with_risk()
        # HighRisk (75) should come before LowRisk (15)
        names = [s["patient_name"] for s in sessions]
        assert names.index("HighRisk") < names.index("LowRisk")
        # Check fields present
        high = next(s for s in sessions if s["patient_name"] == "HighRisk")
        assert high["risk_score"] == 75
        assert high["risk_reasoning"] == "urgent DVT concern"
        assert "dvt_leg_swelling" in high["triggered_signals"]

    def test_get_all_sessions_no_risk_score(self):
        sid = db.create_session("Laparoscopic Appendectomy", 1, "NewPatient")
        sessions = db.get_all_sessions_with_risk()
        new = next(s for s in sessions if s["patient_name"] == "NewPatient")
        assert new["risk_score"] == 0
        assert new["triggered_signals"] == []

    def test_get_session_conclusion_none(self):
        sid = db.create_session("Total Knee Replacement", 3, "NoConclude")
        assert db.get_session_conclusion(sid) is None

    def test_get_session_conclusion_returns_data(self):
        sid = db.create_session("Total Knee Replacement", 3, "Concluded")
        db.save_patient_history(
            session_id=sid, patient_name="Concluded",
            surgery_type="Total Knee Replacement", recovery_day=3,
            key_findings=["pain", "swelling"],
            risk_level="moderate",
            unresolved_concerns=["check wound drainage"],
            resolved_concerns=[],
            session_summary="Patient reports moderate pain and swelling.",
        )
        result = db.get_session_conclusion(sid)
        assert result is not None
        assert result["risk_level"] == "moderate"
        assert "pain" in result["key_findings"]
        assert "check wound drainage" in result["unresolved_concerns"]
        assert result["session_summary"] == "Patient reports moderate pain and swelling."

    def test_critical_severity_in_alerts(self):
        """Verify that 'critical' severity is now accepted by the alerts table."""
        sid = db.create_session("Total Knee Replacement", 7, "CritTest")
        alert_id = db.write_alert(sid, "critical", "Critical severity test",
                                  signals=["test"], recommended_action="Test")
        assert alert_id > 0
        alerts = db.get_alerts(sid)
        assert any(a["severity"] == "critical" for a in alerts)
