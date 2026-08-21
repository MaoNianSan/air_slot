from pathlib import Path

from validation.data_usage_review import run


def test_human_review_packet_records_applied_decisions_and_closed_gate(tmp_path: Path):
    packet = run(output_dir=tmp_path)
    assert packet["status"] == "DATA_USAGE_DECISIONS_APPLIED_AUDIT_PASS"
    assert packet["authority"] == "HUMAN_DECISION_CLOSURE_PACKET"
    assert packet["counts"] == {
        "raw_columns_human_review": 0,
        "semantic_conflicts_human_review": 0,
        "registry_conflicts_human_review": 0,
        "pre_output_conflicts_human_review": 0,
        "decisions": 7,
    }
    assert {item["id"]: item["selected"] for item in packet["decisions"]} == {
        "DUC-01":"A", "DUC-02":"A", "DUC-03":"A", "DUC-04":"A",
        "DUC-05":"A", "DUC-06":"B", "DUC-07":"A",
    }
    assert packet["pre_bypass"]["m2_raw_read"] is False
    assert packet["runtime_rule_registration"]["entry"]["source_outcome_role_preserved"] is True
    assert packet["audit_counts"]["RUNTIME_USED_NO_CONTRACT"] == 0
    assert packet["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert (tmp_path / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.md").is_file()
    assert (tmp_path / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.json").is_file()


def test_human_review_packet_is_deterministic(tmp_path: Path):
    first = run(output_dir=tmp_path / "first")
    second = run(output_dir=tmp_path / "second")
    assert first["artifact_hash"] == second["artifact_hash"]
