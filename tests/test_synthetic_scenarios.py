"""Tests for synthetic reasoning examples."""

from src.synthetic_scenarios import (
    CONVERSATIONALIST_REASONING_EXAMPLES,
    RISK_ASSESSOR_REASONING_EXAMPLES,
    RISK_ASSESSOR_INVESTIGATION_EXAMPLES,
    get_conversationalist_examples,
    get_risk_assessor_examples,
)


class TestConversationalistExamples:
    def test_has_examples(self):
        assert len(CONVERSATIONALIST_REASONING_EXAMPLES) >= 4

    def test_example_structure(self):
        for ex in CONVERSATIONALIST_REASONING_EXAMPLES:
            assert "scenario" in ex
            assert "patient_says" in ex
            assert "bad_response" in ex
            assert "good_response" in ex
            assert "reasoning" in ex

    def test_formatter_produces_output(self):
        result = get_conversationalist_examples()
        assert "CLINICAL REASONING EXAMPLES" in result
        assert len(result) > 200


class TestRiskAssessorExamples:
    def test_has_reasoning_examples(self):
        assert len(RISK_ASSESSOR_REASONING_EXAMPLES) >= 3

    def test_has_investigation_examples(self):
        assert len(RISK_ASSESSOR_INVESTIGATION_EXAMPLES) >= 2

    def test_reasoning_example_structure(self):
        for ex in RISK_ASSESSOR_REASONING_EXAMPLES:
            assert "scenario" in ex
            assert "patient_data" in ex
            assert "bad_assessment" in ex
            assert "good_assessment" in ex

    def test_investigation_example_structure(self):
        for ex in RISK_ASSESSOR_INVESTIGATION_EXAMPLES:
            assert "scenario" in ex
            assert "investigation_sequence" in ex
            assert "reasoning" in ex
            assert len(ex["investigation_sequence"]) >= 4

    def test_formatter_includes_both(self):
        result = get_risk_assessor_examples()
        assert "CLINICAL REASONING EXAMPLES" in result
        assert "INVESTIGATION EXAMPLES" in result
