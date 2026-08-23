import json
from pathlib import Path

from exp.m1_v2_current_stage_development_labels import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_current_stage_development_labels_are_evaluation_only_and_tail_aware(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert artifact["artifact_hash"] == manifest["artifact_hash"]
    assert artifact["node_count"] == 69
    assert artifact["row_count"] == 207
    assert artifact["labels_are_model_inputs"] is False
    assert artifact["exact_tail_values_retained"] is True
    assert artifact["truncation"] is False
    assert artifact["deletion"] is False
    assert artifact["winsorization"] is False
    assert {row["split"] for row in artifact["rows"]} == {"development"}
    assert all(row["exact_minutes"] is None for row in artifact["rows"] if not row["active"])
    assert all(
        row["exact_minutes"] > row["q_max_minutes"]
        for row in artifact["rows"]
        if row["class_id"] == "OVERFLOW_TAIL"
    )
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False
    assert artifact["safety"]["FULL"] is False
