import json
from pathlib import Path

import yaml

from model.common.config import load_config_layers


PREFLIGHT = Path(
    "artifacts/diagnostics/m1_v2_paper_model_closure/M1_V2_TUNING_PREFLIGHT.json"
)


def test_h_candidate_update_is_ready_and_bounded():
    manifest = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    scientific = load_config_layers(Path("configs")).scientific
    evaluation = yaml.safe_load(
        Path("configs/evaluation/exp1.yaml").read_text(encoding="utf-8")
    )
    cross_contract = json.loads(
        Path("EXPERIMENT_CROSS_CONTRACT.json").read_text(encoding="utf-8")
    )

    assert manifest["status"] == "M1_V2_TUNING_PREFLIGHT_H_READY"
    assert manifest["tuning_authorized"] is False
    assert manifest["candidate_update"] == {
        "decision_id": "AIR_SLOT_M1_V2_TUNING_PREFLIGHT_H_CANDIDATES_UPDATE",
        "decision_date": "2026-08-22",
        "scope": "CANDIDATE_CONFIGURATION_ONLY",
        "previous_hidden_size_candidates": [16, 32],
        "current_hidden_size_candidates": [8, 16, 32],
    }
    assert manifest["candidate_space"]["hidden_size"] == [8, 16, 32]
    assert scientific.parameters["m1_hidden_size_candidates"].value == [8, 16, 32]
    assert evaluation["hidden_size_candidates"] == [8, 16, 32]
    assert cross_contract["hidden_size_candidates"] == [8, 16, 32]
    assert manifest["bounded_protocol"]["stage_1_hidden_size"]["candidates"] == [
        8, 16, 32,
    ]
    assert manifest["bounded_protocol"][
        "maximum_unique_candidate_configurations_per_seed"
    ] == 7


def test_h_candidate_update_preserves_fixed_contract_and_zero_run_counters():
    manifest = json.loads(PREFLIGHT.read_text(encoding="utf-8"))

    assert manifest["final_feature_contract"] == {
        "dynamic": 39,
        "static": 4,
        "total": 43,
        "history": "FULL_ADAPTIVE_CAUSAL_PREFIX",
    }
    assert manifest["final_target_support"] == {
        "T_IB_REMAINING_HAZARD": 360,
        "D_OB": 210,
        "D_TX": 60,
        "bin_width_minutes": 5,
        "support_provenance": "V2_SUPPORT_REFROZEN_AFTER_A2_B2",
    }
    assert manifest["candidate_space"]["learning_rate"] == [0.001, 0.003, 0.01]
    assert manifest["candidate_space"]["weight_decay"] == [0.0, 0.0001]
    assert manifest["candidate_space"]["optimization_duration_epochs"] == [4, 8]
    assert manifest["split_roles"] == {
        "Train": "fit candidate model",
        "Development": "select H/LR/regularization/duration using principal metric",
        "Calibration": "post-selection probability calibration and diagnostics only",
        "Final Test": "locked",
    }
    assert manifest["safety"]["M1_TRAINING_RUNS"] == 0
    assert manifest["safety"]["TUNING_RUNS"] == 0
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
