import json
from pathlib import Path

from exp.exp4.formal_preparation import FORMAL_BASELINES, prepare_formal_execution
from exp.exp4.protocol import EVALUATION_LEAD_MINUTES


ROOT = Path(__file__).resolve().parents[3]


def test_formal_preparation_binds_frozen_m1_and_preserves_all_exp4_gates(tmp_path):
    paths = prepare_formal_execution(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    baselines = json.loads(paths["baseline_contracts"].read_text(encoding="utf-8"))
    schema = json.loads(paths["lineage_schema"].read_text(encoding="utf-8"))
    readiness = json.loads(paths["readiness"].read_text(encoding="utf-8"))

    assert manifest["status"] == "EXP4_FORMAL_EXECUTION_READY"
    assert tuple(manifest["baselines"]) == FORMAL_BASELINES
    assert manifest["m1_binding"]["model_id"] == "M1_V2_GRU_H32"
    assert manifest["m1_binding"]["hidden_size"] == 32
    assert tuple(manifest["evaluation_lead_minutes"]) == EVALUATION_LEAD_MINUTES
    assert manifest["datasets"]["primary"]["dataset_instance_id"] == "data2_2019"
    assert manifest["datasets"]["generalization"]["dataset_instance_id"] == "data1_2019"
    assert manifest["datasets"]["generalization"]["pooling"] == "FORBIDDEN"

    assert tuple(baselines["baselines"]) == FORMAL_BASELINES
    assert baselines["baselines"]["HISTORICAL"]["fallback_to_legacy_v1"] == "FORBIDDEN"
    assert baselines["baselines"]["LIGHTGBM_FAST"]["status"] == "BLOCKED_M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED"
    assert baselines["baselines"]["RANDOM_FOREST"]["zero_fill"] is False
    assert baselines["baselines"]["STATE_AWARE_FULL"]["model_id"] == "M1_V2_GRU_H32"

    assert "NO_DATA1_DATA2_POOLING_OR_SILENT_SUBSTITUTION" in schema["required_invariants"]
    assert "UNAVAILABLE_BASELINE_OR_TARGET_IS_NOT_RUN_NOT_ZERO" in schema["required_invariants"]
    assert readiness["preparation_status"] == "READY"
    assert readiness["execution_status"] == "BLOCKED_CURRENT_ARTIFACT_AND_BASELINE_GATES"
    assert readiness["baseline_readiness"]["HISTORICAL"]["metrics"] == "NOT_RUN_NO_SYNTHETIC_OR_ZERO_FILLED_VALUES"
    assert readiness["safety"] == {
        "M1_TRAINING_RUNS_THIS_PREPARATION": 0,
        "TUNING_RUNS_THIS_PREPARATION": 0,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "FULL": False,
        "PAPER_FULL_RUN": False,
    }
