"""Tests for scenario loading and validation."""

import json
from pathlib import Path

SCENARIOS_DIR = Path(__file__).parent.parent / "src" / "scenarios"

REQUIRED_KEYS = {"name", "surgery_type", "recovery_day", "patient_name", "description"}
VALID_SURGERIES = {"Total Knee Replacement", "Total Hip Replacement", "Laparoscopic Appendectomy"}


class TestScenarioFiles:
    def test_scenarios_exist(self):
        scenarios = list(SCENARIOS_DIR.glob("*.json"))
        assert len(scenarios) >= 7

    def test_all_scenarios_valid_json(self):
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            assert isinstance(data, dict), f"{f.name} is not a JSON object"

    def test_required_keys_present(self):
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            missing = REQUIRED_KEYS - set(data.keys())
            assert not missing, f"{f.name} missing keys: {missing}"

    def test_valid_surgery_types(self):
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["surgery_type"] in VALID_SURGERIES, \
                f"{f.name} has unknown surgery: {data['surgery_type']}"

    def test_recovery_day_positive(self):
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["recovery_day"] >= 1, f"{f.name} has invalid recovery day"

    def test_unique_names(self):
        names = []
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            names.append(data["name"])
        assert len(names) == len(set(names)), "Duplicate scenario names found"

    def test_unique_patient_names(self):
        patients = []
        for f in SCENARIOS_DIR.glob("*.json"):
            data = json.loads(f.read_text())
            patients.append(data["patient_name"])
        assert len(patients) == len(set(patients)), "Duplicate patient names found"
