from pathlib import Path

from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.data_usage_contract_audit import run


def _raw(result, adapter_id, column):
    return next(
        row for row in result["raw_column_audit"]
        if row["adapter_id"] == adapter_id and row["raw_column"] == column
    )


def test_audit_is_deterministic_and_keeps_scientific_gates_closed(tmp_path: Path):
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")

    assert first["artifact_hash"] == second["artifact_hash"]
    assert first["authority"] == "CONTRACT_VALIDATION_AFTER_HUMAN_DECISIONS"
    assert first["status"] == "DATA_USAGE_CONTRACT_AUDIT_PASS"
    assert first["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "GATE_B_ENTERED": False,
    }
    assert all(path.is_file() for path in (tmp_path / "first").iterdir())
    assert (tmp_path / "first" / "AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.yaml").is_file()


def test_audit_closes_active_gaps_and_preserves_nonfailure_classifications(tmp_path: Path):
    result = run(tmp_path)

    assert _raw(result, "D2-ONTIME", "Reporting_Airline")["status"] == "COVERED_ACTIVE"
    assert _raw(result, "D2-ONTIME", "Tail_Number")["status"] == "COVERED_ACTIVE"
    assert _raw(result, "D2-ONTIME", "DepDelay")["declared_role"] == "SIGNED_TIME_OFFSET"
    assert _raw(result, "D2-ONTIME", "ArrDelay")["declared_role"] == "SIGNED_TIME_OFFSET"
    assert _raw(result, "D2-ONTIME", "DepDelayMinutes")["declared_role"] == "NONNEGATIVE_DELAY_REPORTING_ONLY"
    assert _raw(result, "D2-ONTIME", "ArrDelayMinutes")["declared_role"] == "NONNEGATIVE_DELAY_REPORTING_ONLY"
    assert _raw(result, "D2-T100", "CLASS")["status"] == "REFERENCE_BUILD_ONLY"
    assert _raw(result, "D1-METAR", "mslp")["status"] == "EXPLICITLY_UNUSED"
    assert _raw(result, "D1-EUROSTAT", "id")["status"] == "SOURCE_SCHEMA_METADATA"
    assert _raw(result, "D2-ISD", "REPORT_TYPE")["status"] == "DIAGNOSTIC_ONLY"
    assert result["missing_runtime_rule_registrations"] == []
    assert result["pre_bypass_findings"] == []
    for key in (
        "PRE_BYPASS",
        "RUNTIME_USED_NO_CONTRACT",
        "AMBIGUOUS_ACTIVE_COLUMN",
        "ACTIVE_SEMANTIC_CONFLICT",
        "ACTIVE_REGISTRY_CONFLICT",
        "ACTIVE_PRE_OUTPUT_CONFLICT",
    ):
        assert result["counts"][key] == 0
    assert len(result["m1_feature_audit"]) == len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES)
    assert {row["status"] for row in result["m1_feature_audit"]} == {"COVERED_ACTIVE"}
