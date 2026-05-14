"""Tests for clinical knowledge base and medication masking."""

from src.clinical_knowledge import (
    get_surgery_knowledge, get_medication_context,
    get_vital_reasoning, check_med_masking,
    RECOVERY_TIMELINES, MEDICATION_KNOWLEDGE, VITAL_RANGES,
)


class TestSurgeryKnowledge:
    def test_known_surgery(self):
        result = get_surgery_knowledge("Total Knee Replacement")
        assert "Knee Replacement" in result
        assert "pain trajectory" in result.lower() or "pain" in result.lower()
        assert "milestones" in result.lower() or "Milestones" in result

    def test_all_surgery_types(self):
        for surgery_type in RECOVERY_TIMELINES:
            result = get_surgery_knowledge(surgery_type)
            assert len(result) > 100  # meaningful content
            assert surgery_type in result

    def test_unknown_surgery(self):
        result = get_surgery_knowledge("Brain Transplant")
        assert "No specific" in result or "general" in result.lower()


class TestMedicationContext:
    def test_known_meds(self):
        result = get_medication_context(["ibuprofen", "oxycodone"])
        assert "NSAID" in result
        assert "Opioid" in result

    def test_empty_meds(self):
        assert get_medication_context([]) == ""

    def test_unknown_med(self):
        result = get_medication_context(["unobtanium"])
        assert "No specific knowledge" in result

    def test_case_insensitive(self):
        result = get_medication_context(["Ibuprofen"])
        assert "NSAID" in result


class TestVitalReasoning:
    def test_returns_content(self):
        result = get_vital_reasoning()
        assert "Temperature" in result or "temperature" in result
        assert "Heart Rate" in result or "heart_rate" in result.lower()

    def test_all_vitals_covered(self):
        result = get_vital_reasoning()
        for vital_type in VITAL_RANGES:
            assert vital_type.replace("_", " ") in result.lower()


class TestMedMasking:
    def test_nsaid_masks_fever(self):
        result = check_med_masking("fever", ["ibuprofen"])
        assert "WARNING" in result
        assert "suppress" in result.lower()

    def test_nsaid_masks_wound_warmth(self):
        result = check_med_masking("wound_warmth", ["ibuprofen"])
        assert "WARNING" in result

    def test_opioid_masks_pain(self):
        result = check_med_masking("pain", ["oxycodone"])
        assert "WARNING" in result
        assert "mask" in result.lower() or "Opioid" in result

    def test_opioid_masks_confusion(self):
        result = check_med_masking("confusion", ["oxycodone"])
        assert "WARNING" in result

    def test_acetaminophen_masks_fever(self):
        result = check_med_masking("fever", ["acetaminophen"])
        assert "WARNING" in result
        assert "NOT inflammation" in result or "not inflammation" in result.lower()

    def test_no_masking_interaction(self):
        result = check_med_masking("swelling", ["acetaminophen"])
        assert "No significant masking" in result

    def test_no_meds(self):
        result = check_med_masking("pain", [])
        assert "No significant masking" in result

    def test_unknown_med(self):
        result = check_med_masking("fever", ["unobtanium"])
        assert "No significant masking" in result

    def test_multiple_meds(self):
        result = check_med_masking("fever", ["ibuprofen", "acetaminophen"])
        assert result.count("WARNING") >= 2  # both mask fever


class TestKnowledgeBaseIntegrity:
    def test_all_surgeries_have_required_keys(self):
        for name, info in RECOVERY_TIMELINES.items():
            assert "expected_pain_curve" in info, f"{name} missing pain curve"
            assert "milestones" in info, f"{name} missing milestones"
            assert "red_flags_context" in info, f"{name} missing red flags"

    def test_all_meds_have_required_keys(self):
        for name, info in MEDICATION_KNOWLEDGE.items():
            assert "class" in info, f"{name} missing class"
            assert "onset" in info, f"{name} missing onset"
            assert "clinical_notes" in info, f"{name} missing notes"

    def test_all_vitals_have_reasoning(self):
        for name, info in VITAL_RANGES.items():
            assert "clinical_reasoning" in info, f"{name} missing reasoning"
