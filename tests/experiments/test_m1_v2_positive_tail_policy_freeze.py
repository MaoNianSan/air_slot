"""Focused validation for the frozen explicit positive-tail representation."""

import json
from pathlib import Path

from exp.workflows.m1_v2_positive_tail_policy_freeze import freeze_positive_tail_policy


ROOT = Path(__file__).resolve().parents[2]


def test_positive_tail_freeze_preserves_observable_tail_and_frozen_bindings(tmp_path):
    outputs = freeze_positive_tail_policy(root=ROOT, output_root=tmp_path)
    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    support = json.loads(outputs["support"].read_text(encoding="utf-8"))
    lineage = json.loads(outputs["lineage"].read_text(encoding="utf-8"))

    assert manifest["status"] == "M1_POSITIVE_TAIL_POLICY_FROZEN"
    assert manifest["representation"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    assert manifest["next_gate"] == "M1_CURRENT_STAGE_JOINT_SCENARIO_ARTIFACT_REQUIRED"
    assert support["target_contracts"]["T_IB_A00"]["q_max_minutes"] == 360
    assert support["target_contracts"]["D_OB"]["q_max_minutes"] == 210
    assert support["target_contracts"]["D_TX"]["q_max_minutes"] == 60
    for target in ("T_IB_A00", "D_OB", "D_TX"):
        tail = support["target_contracts"][target]["tail_class"]
        assert tail["class_id"] == "OVERFLOW_TAIL"
        assert tail["observable"] is True
        assert tail["raw_value_preserved"] is True
        assert tail["overflow_flag_preserved"] is True
    assert support["observation_policy"]["continuous_quantile_above_q_max"] == "ABSTAIN_EXPLICIT_TAIL_CLASS_REQUIRED"
    assert support["observation_policy"]["continuous_tail_extrapolation"] is False
    assert support["observation_policy"]["no_deletion"] is True
    assert support["observation_policy"]["no_truncation"] is True
    assert support["observation_policy"]["no_winsorization"] is True
    assert support["threshold_tuning"]["development_based_threshold_tuning"] is False
    assert lineage["checkpoint_unchanged"] is True
    assert lineage["feature_schema_unchanged"] is True
    assert lineage["support_boundaries_unchanged"] is True
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
    assert manifest["safety"]["FULL"] is False
