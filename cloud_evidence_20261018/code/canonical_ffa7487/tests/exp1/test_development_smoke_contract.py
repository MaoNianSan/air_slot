from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from exp.exp1 import development_smoke


def test_partition_lock_rejects_final_test_dates():
    development_smoke.require_development_date(date(2019, 9, 30))
    with pytest.raises(ValueError, match="FINAL_TEST_DATE_REJECTED"):
        development_smoke.require_development_date(date(2019, 10, 1))


def test_smoke_uses_only_formal_h16_artifact_paths():
    assert development_smoke.HISTORY_ROOT.name == "M1_H16_HISTORY_PRIMARY"
    assert development_smoke.CURRENT_ROOT.name == "M1_H16_CURRENT_COMPARATOR"
    assert development_smoke.COHORT_PATH.name == "M1_FORMAL_TRAINING_COHORT_V1.json"


def test_smoke_source_has_no_training_calibration_or_raw_reconstruction():
    source = Path(development_smoke.__file__).read_text(encoding="utf-8")
    for forbidden in (
        ".train(",
        ".calibrate(",
        "ontime_paths(",
        "weather_index(",
        "materialize_preselected_cohorts(",
        "smoke_reference_payloads(",
        "data2/raw",
    ):
        assert forbidden not in source


def test_gate_a_passes_and_final_test_access_is_zero():
    result = development_smoke.validate_gate_a()
    assert result["status"] == "PASS"
    assert all(result["checks"].values())


def test_missing_formal_prestate_fails_closed(tmp_path):
    result = development_smoke.run(tmp_path)
    assert result["status"] == "BLOCKED"
    assert result["gates"]["A_artifacts"] == "PASS"
    assert result["gates"]["B_m1_history_current"] == "BLOCKED"
    assert result["prestate_availability"]["formal_reservoir_ids_exact"] is True
    assert result["prestate_availability"]["formal_pre_state_available"] is False
    assert result["final_test_access_count"] == 0
    assert result["formal_exp1_execution"] is False
