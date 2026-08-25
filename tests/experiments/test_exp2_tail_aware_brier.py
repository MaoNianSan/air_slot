import json
from pathlib import Path

from exp.exp2.tail_aware_brier import materialize


ROOT = Path(__file__).resolve().parents[2]


def test_tail_aware_brier_is_real_and_never_scalar_fills_tail(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))
    assert artifact["principal_event"] == "D_TO_POST_GT_30"
    assert artifact["tail_policy"].endswith("NO_SCALAR_SUBSTITUTION")
    assert artifact["zero_fill"] is False
    assert artifact["synthetic_metrics"] is False
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False
    assert artifact["safety"]["FULL"] is False
    for variant, metrics in artifact["variants"].items():
        assert variant in {"EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT"}
        assert metrics["supported_node_count"] > 0
        assert metrics["episode_balanced_brier"] is not None
        assert metrics["abstain_node_count"] >= 0
