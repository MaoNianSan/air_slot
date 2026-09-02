import json
from pathlib import Path

import yaml

from model.common.config import load_config_layers


PREFLIGHT = Path(
    "artifacts/diagnostics/model/m1_v2_model_closure/M1_V2_TUNING_PREFLIGHT.json"
)


def test_historical_tuning_preflight_is_not_active_authority():
    manifest = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    scientific = load_config_layers(Path("configs")).scientific
    engineering = yaml.safe_load(
        Path("configs/engineering/m1_data2_development_fast.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["status"] == "M1_V2_TUNING_PREFLIGHT_H_READY"
    assert manifest["tuning_authorized"] is False
    assert manifest["candidate_update"]["decision_date"] == "2026-08-22"
    assert scientific.parameters["m1_hidden_size"].value == 8
    assert scientific.parameters["m1_sensitivity_hidden_size"].value == 16
    assert engineering["development_selection"]["runtime_hidden_size"] == 8
    assert engineering["development_selection"][
        "predefined_sensitivity_hidden_size"
    ] == 16


def test_current_freeze_supersedes_historical_preflight_without_running_it():
    manifest = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    scientific = load_config_layers(Path("configs")).scientific

    assert manifest["final_feature_contract"] == {
        "dynamic": 39,
        "static": 4,
        "total": 43,
        "history": "FULL_ADAPTIVE_CAUSAL_PREFIX",
    }
    assert scientific.parameters["m1_v2_t_ib_remaining_max_finite_minutes"].value == 360
    assert scientific.parameters["m1_v2_d_ob_max_finite_minutes"].value == 180
    assert scientific.parameters["m1_v2_d_tx_max_finite_minutes"].value == 60
    assert scientific.parameters["scenario_count"].value == 64
    assert manifest["safety"]["M1_TRAINING_RUNS"] == 0
    assert manifest["safety"]["TUNING_RUNS"] == 0
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
