import json
from pathlib import Path

from exp.exp2.tail_aware_calibration import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_tail_aware_calibration_preserves_support_and_safety(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))

    assert artifact["status"] == "EXP2A_TAIL_AWARE_CALIBRATION_MATERIALIZED"
    assert artifact["development_bin_tuning"] is False
    assert artifact["zero_fill"] is False
    assert artifact["synthetic_metrics"] is False
    assert set(artifact["variants"]) == {"EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT"}
    for record in artifact["variants"].values():
        assert record["supported_node_count"] == 63
        assert record["supported_episode_count"] == 5
        assert len(record["bins"]) == 10
        assert abs(sum(row["episode_balanced_mass"] for row in record["bins"]) - 1.0) < 1e-12
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
