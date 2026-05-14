"""Tests for the red-flag matrix."""

from src.red_flags import RED_FLAGS, get_flags_for_session, format_flags_for_prompt


class TestRedFlagMatrix:
    def test_total_flag_count(self):
        assert len(RED_FLAGS) == 21

    def test_all_flags_have_valid_urgency(self):
        valid = {"routine", "monitor", "urgent", "911-now"}
        for flag in RED_FLAGS:
            assert flag.urgency in valid, f"{flag.signal_name} has invalid urgency"

    def test_all_flags_have_valid_weight(self):
        for flag in RED_FLAGS:
            assert 0 <= flag.base_weight <= 100, f"{flag.signal_name} weight out of range"

    def test_unique_signal_names(self):
        names = [f.signal_name for f in RED_FLAGS]
        assert len(names) == len(set(names)), "Duplicate signal names found"


class TestFlagFiltering:
    def test_knee_day3(self):
        flags = get_flags_for_session("Total Knee Replacement", 3)
        names = [f.signal_name for f in flags]
        assert "dvt_leg_swelling" in names  # applies to knee
        assert "fever_persistent" in names  # day 3 >= day 2
        assert "no_bowel_function" not in names  # appendectomy only

    def test_appendix_day1(self):
        flags = get_flags_for_session("Laparoscopic Appendectomy", 1)
        names = [f.signal_name for f in flags]
        assert "dvt_leg_swelling" not in names  # not applicable
        assert "fever_persistent" not in names  # day_range starts at 2
        assert "fever_high" in names  # always applies

    def test_hip_day5(self):
        flags = get_flags_for_session("Total Hip Replacement", 5)
        names = [f.signal_name for f in flags]
        assert "dvt_leg_swelling" in names
        assert "dvt_calf_pain" in names
        assert "inability_to_bear_weight" in names  # day 5 >= day 3

    def test_unknown_surgery_gets_universal_flags(self):
        flags = get_flags_for_session("Unknown Surgery", 5)
        names = [f.signal_name for f in flags]
        assert "fever_persistent" in names  # applies to all
        assert "chest_pain" in names
        assert "dvt_leg_swelling" not in names  # surgery-specific


class TestFlagFormatting:
    def test_format_includes_categories(self):
        flags = get_flags_for_session("Total Knee Replacement", 7)
        formatted = format_flags_for_prompt(flags)
        assert "RED FLAG MATRIX" in formatted
        assert "INFECTION" in formatted or "CARDIOVASCULAR" in formatted

    def test_format_includes_signal_names(self):
        flags = get_flags_for_session("Total Knee Replacement", 7)
        formatted = format_flags_for_prompt(flags)
        for flag in flags:
            assert flag.signal_name in formatted
