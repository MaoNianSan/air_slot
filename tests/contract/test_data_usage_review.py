from pathlib import Path

from validation.data_usage_review import run


def test_human_review_packet_is_bounded_and_ready(tmp_path: Path):
    packet = run(output_dir=tmp_path)
    assert packet["status"] == "DATA_USAGE_REVIEW_PACKET_READY"
    assert packet["authority"] == "NON_AUTHORITATIVE_HUMAN_REVIEW_PACKET"
    assert packet["counts"] == {
        "raw_columns_human_review": 8,
        "semantic_conflicts_human_review": 10,
        "registry_conflicts_human_review": 6,
        "pre_output_conflicts_human_review": 4,
        "decisions": 7,
    }
    assert packet["pre_bypass"]["classification"] == "C"
    assert packet["runtime_rule_registration"]["candidate_entry"]["source_outcome_role_preserved"] is True
    assert packet["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert (tmp_path / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.md").is_file()
    assert (tmp_path / "AIR_SLOT_DATA_USAGE_HUMAN_REVIEW_PACKET.json").is_file()


def test_human_review_packet_is_deterministic(tmp_path: Path):
    first = run(output_dir=tmp_path / "first")
    second = run(output_dir=tmp_path / "second")
    assert first["artifact_hash"] == second["artifact_hash"]
