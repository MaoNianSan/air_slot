from pathlib import Path

from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from validation.data_usage_contract_audit import run


def _raw(result, adapter_id, column):
    return next(
        row for row in result["raw_column_audit"]
        if row["adapter_id"] == adapter_id and row["raw_column"] == column
    )


def test_audit_is_non_authoritative_deterministic_and_keeps_scientific_gates_closed(tmp_path: Path):
    first = run(tmp_path / "first")
    second = run(tmp_path / "second")

    assert first["artifact_hash"] == second["artifact_hash"]
    assert first["authority"] == "NON_AUTHORITATIVE_DIAGNOSTIC_DRAFT"
    assert first["status"] == "DATA_USAGE_CONTRACT_HUMAN_REVIEW_REMAINS"
    assert first["safety"] == {
        "M1_TRAINING_RUNS": 0,
        "TUNING_RUNS": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "GATE_B_ENTERED": False,
    }
    assert all(path.is_file() for path in (tmp_path / "first").iterdir())
    assert (tmp_path / "first" / "AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.yaml").is_file()


def test_audit_exposes_mapping_gaps_conflicts_and_complete_m1_lineage(tmp_path: Path):
    result = run(tmp_path)

    assert _raw(result, "D2-ONTIME", "Reporting_Airline")["status"] == "MISSING"
    assert _raw(result, "D2-ONTIME", "Tail_Number")["status"] == "SEMANTIC_CONFLICT"
    assert _raw(result, "D2-T100", "CLASS")["status"] == "SEMANTIC_CONFLICT"
    assert {item["rule_id"] for item in result["missing_runtime_rule_registrations"]} == {
        "D2-BTS-FACTUAL-REPLAY"
    }
    assert {(item["raw_column"], item["path"]) for item in result["pre_bypass_findings"]} == {
        ("iata", "model/M2/freeze.py"),
        ("timezone", "model/M2/freeze.py"),
    }
    assert len(result["m1_feature_audit"]) == len(FEATURE_NAMES_V2) + len(STATIC_FEATURE_NAMES)
    assert {row["status"] for row in result["m1_feature_audit"]} == {"COVERED"}
