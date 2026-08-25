import json
from pathlib import Path

from exp.exp2.formal_development import VARIANTS, run_formal_development


ROOT = Path(__file__).resolve().parents[2]


def test_formal_development_records_all_variants_and_preserves_guards(tmp_path):
    paths = run_formal_development(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    lineage = json.loads(paths["lineage"].read_text(encoding="utf-8"))

    assert manifest["status"] == "EXP2_FORMAL_EXECUTION_COMPLETE"
    assert tuple(manifest["variants"]) == VARIANTS
    assert manifest["m1_binding"]["model_id"] == "M1_V2_GRU_H32"
    assert manifest["safety"] == {
        "M1_TRAINING_RUNS_THIS_EXECUTION": 0,
        "TUNING_RUNS_THIS_EXECUTION": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "FULL": False,
        "PAPER_FULL_RUN": False,
    }
    assert set(metrics["variants"]) == set(VARIANTS)
    assert all(
        metrics["variants"][variant]["execution_status"] == "PARTIAL_TAIL_AWARE_BRIER_AND_CALIBRATION_COMPLETE_OTHER_STATE_AND_DECISION_METRICS_BLOCKED"
        for variant in ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")
    )
    assert metrics["variants"]["EXP2B_7COMP"]["execution_status"] == "READY_TYPED_VECTOR_ASSUMPTION_GROUNDED"
    assert metrics["variants"]["EXP2B_3CHANNEL"]["execution_status"] == "READY_ASSUMPTION_GROUNDED"
    assert metrics["variants"]["EXP2B_SCALAR"]["execution_status"] == "READY_ASSUMPTION_GROUNDED_RANKING_GATED"
    assert lineage["gates"]["M1_COHORT_BINDING"]["intersection_nodes"] == 0
    assert lineage["gates"]["M1_COHORT_BINDING"]["status"] == "PASS_CURRENT_STAGE_COHORT_REFROZEN"
    assert lineage["gates"]["M1_COHORT_BINDING"]["current_stage_node_count"] == 69
    assert lineage["gates"]["M1_COHORT_BINDING"]["changed_node_count_from_historical_parent"] == 3
    assert lineage["gates"]["M1_COHORT_BINDING"]["feature_compatibility"] == "PASS_FROZEN_M1_FEATURE_TENSOR_COMPATIBILITY"
    assert lineage["gates"]["M1_POSITIVE_TAIL"]["policy"] == "FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS"
    assert lineage["gates"]["M1_POSITIVE_TAIL"]["status"] == "PASS_M1_POSITIVE_TAIL_POLICY_FROZEN"
    assert lineage["gates"]["M1_SCENARIOS"]["status"] == "PASS_M1_V2_TYPED_JOINT_SCENARIO_ARTIFACT_MATERIALIZED"
    assert lineage["gates"]["M1_DEVELOPMENT_LABELS"]["status"] == "PASS_CURRENT_STAGE_DEVELOPMENT_LABEL_ARTIFACT_MATERIALIZED"
    assert lineage["gates"]["M1_TAIL_AWARE_PROPER_SCORES"]["status"] == "PASS_TAIL_AWARE_SCALAR_CRPS_ASSUMPTION_GROUNDED_DUAL_SCHEME"
    assert lineage["gates"]["M1_TAIL_AWARE_BRIER"]["status"] == "PASS_THRESHOLD_EVENT_BRIER_MATERIALIZED"
    assert lineage["gates"]["M1_TAIL_AWARE_CALIBRATION"]["status"] == "PASS_THRESHOLD_EVENT_CALIBRATION_MATERIALIZED"
    metrics = json.loads(paths["metrics"].read_text(encoding="utf-8"))
    assert metrics["variants"]["EXP2A_JOINT"]["state_metrics"]["STATE_BRIER"]["support_status"] == "SUPPORTED"
    assert metrics["variants"]["EXP2A_JOINT"]["state_metrics"]["STATE_BRIER"]["supported_node_count"] == 63
    assert metrics["variants"]["EXP2A_JOINT"]["state_metrics"]["STATE_CALIBRATION"]["support_status"] == "SUPPORTED"
    assert lineage["gates"]["M1_SCENARIOS"]["scenario_count_per_node"] == 250
    assert lineage["gates"]["M1_SCENARIOS"]["row_count"] == 17250
    assert lineage["gates"]["M2_SEVEN_COMPONENT"]["status"] == "PASS_M2_TYPED_SEVEN_COMPONENT_VECTOR_MATERIALIZED_ASSUMPTION_GROUNDED"
    assert lineage["gates"]["M2_SEVEN_COMPONENT"]["seven_component_status_counts"] == {"ABSTAIN": 1684, "SUPPORTED": 15566}
    assert lineage["FINAL_TEST_ACCESS_COUNT"] == 0
    assert lineage["PAPER_FULL_RUN"] is False
