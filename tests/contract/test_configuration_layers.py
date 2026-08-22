from pathlib import Path
import pytest
from pydantic import ValidationError

from model.common.config import ScientificConfig, load_config_layers, resolve_raw_roots
from model.common.paths import PROJECT_ROOT


def test_development_frozen_parameter_has_no_implicit_value():
    cfg = ScientificConfig.model_validate({"schema_version": "1.0.0", "parameters": {
        "weather_max_age_minutes": {"freeze_state": "DEVELOPMENT_FROZEN", "value": None}}})
    assert cfg.parameters["weather_max_age_minutes"].value is None
    with pytest.raises(ValidationError):
        ScientificConfig.model_validate({"schema_version": "1.0.0", "parameters": {
            "weather_max_age_minutes": {"freeze_state": "DEVELOPMENT_FROZEN", "value": 120}}})


def test_machine_path_not_allowed_in_scientific_config(tmp_path: Path):
    with pytest.raises(ValidationError):
        ScientificConfig.model_validate({"schema_version": "1.0.0", "parameters": {},
                                         "raw_root": "D:/raw"})


def test_layers_load_separately():
    layers = load_config_layers(Path("configs"))
    assert layers.scientific.schema_version == "1.0.0"
    assert layers.scientific.parameters["replay_lag_minutes"].value == 0
    assert layers.scientific.parameters["forecast_horizons_minutes"].value == [0,15,60]
    assert layers.scientific.parameters["delay_thresholds_minutes"].value == [15,30,60]
    hidden_size = layers.scientific.parameters["m1_hidden_size"]
    assert hidden_size.freeze_state.value == "DEVELOPMENT_CANDIDATE"
    assert hidden_size.value == 32
    assert hidden_size.provenance["selection_state"] == "DEVELOPMENT_CANDIDATE"
    assert hidden_size.provenance["target_contract"] == [
        "T_IB_REMAINING_HAZARD", "D_OB", "D_TX"]
    assert "historical evidence is not V2 selection evidence" in (
        hidden_size.provenance["legacy_v1_provenance"])
    assert hidden_size.provenance["final_test_access_count"] == 0
    assert layers.scientific.parameters["m1_hidden_size_candidates"].value == [16,32]
    fixed_window = layers.scientific.parameters["m1_fixed_history_window_minutes"]
    assert fixed_window.freeze_state.value == "SENSITIVITY_ONLY"
    assert fixed_window.value == 30
    assert fixed_window.provenance["role"] == "HISTORICAL_V1_SENSITIVITY_ONLY"
    assert fixed_window.provenance["decision_id"] == "D3_SIGNED_M1_H_W_REFREEZE"
    assert fixed_window.provenance["target_contract"] == ["R_IB", "DELTA_OB", "T_TX"]
    assert fixed_window.provenance["evidence"].endswith("m1_signed_wstar_evidence.json")
    assert fixed_window.provenance["final_test_access_count"] == 0
    stochastic = layers.scientific.parameters["m1_stochastic_targets"]
    assert stochastic.value == ["R_IB", "DELTA_OB", "T_TX"]
    assert stochastic.provenance["role"] == "LEGACY_V1"
    v2_contract = layers.scientific.parameters["m1_state_estimator_v2"]
    assert v2_contract.freeze_state.value == "FROZEN"
    assert v2_contract.value == "M1_STATE_ESTIMATOR_V2"
    assert v2_contract.provenance["primitive_targets"] == ["T_IB_A00", "D_OB", "D_TX"]
    assert v2_contract.provenance["derived_targets"] == ["R_IB", "D_TO"]
    assert v2_contract.provenance["predecessor_head"] == "DISCRETE_HAZARD"
    assert v2_contract.provenance["history"] == "FULL_ADAPTIVE_CAUSAL_PREFIX"
    assert v2_contract.provenance["final_test_access_count"] == 0
    quantile_levels = layers.scientific.parameters["m1_v2_quantile_levels"]
    assert quantile_levels.freeze_state.value == "DEVELOPMENT_ONLY"
    assert quantile_levels.value == [0.1, 0.3, 0.5, 0.7, 0.9]
    assert quantile_levels.provenance["final_test_access_count"] == 0
    tail_policy = layers.scientific.parameters["m1_v2_positive_tail_policy"]
    assert tail_policy.freeze_state.value == "HUMAN_DECISION_REQUIRED"
    assert tail_policy.value == "UNRESOLVED"
    assert tail_policy.provenance["human_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED"
    assert tail_policy.provenance["selection_state"] == "NOT_FROZEN"
    formal_contract = layers.scientific.parameters["m1_formal_output_contract"]
    assert formal_contract.freeze_state.value == "FROZEN"
    assert formal_contract.value == ["R_IB", "D_OB", "D_TX", "D_TO"]
    assert formal_contract.provenance["decision_id"] == (
        "AIR_SLOT_MODEL_MANUSCRIPT_RECONCILIATION_2026-08-19")
    assert formal_contract.provenance["final_test_access_count"] == 0
    assert layers.scientific.parameters["scenario_count"].value == 1000
    assert layers.scientific.parameters["weather_max_age_minutes"].value == 60
    assert layers.scientific.parameters["cloud_encoding"].value == "both"
    assert layers.scientific.parameters["m1_r_ib_max_finite_minutes"].value == 360
    assert layers.scientific.parameters["m1_delta_ob_min_finite_minutes"].value == -180
    assert layers.scientific.parameters["m1_delta_ob_max_finite_minutes"].value == 180
    assert layers.scientific.parameters["m1_t_tx_max_finite_minutes"].value == 60
    for name in ("m1_r_ib_max_finite_minutes", "m1_delta_ob_min_finite_minutes",
                 "m1_delta_ob_max_finite_minutes", "m1_t_tx_max_finite_minutes"):
        provenance = layers.scientific.parameters[name].provenance
        assert provenance["role"] == "LEGACY_V1_PROVENANCE_ONLY"
        assert provenance["controls_principal_v2_pipeline"] is False
    v2_supports = {
        "m1_v2_t_ib_remaining_max_finite_minutes": (360, "EPISODE_MAX_ACTIVE_REMAINING"),
        "m1_v2_d_ob_max_finite_minutes": (210, "UNIQUE_EPISODE_OUTCOME"),
        "m1_v2_d_tx_max_finite_minutes": (60, "UNIQUE_EPISODE_OUTCOME"),
    }
    for name, (value, statistic) in v2_supports.items():
        parameter = layers.scientific.parameters[name]
        assert parameter.freeze_state.value == "FROZEN"
        assert parameter.value == value
        assert parameter.provenance["support_provenance"] == (
            "V2_SUPPORT_REFROZEN_AFTER_A2_B2")
        assert parameter.provenance["selection_unit"] == "TRAIN_EPISODE_BALANCED"
        assert parameter.provenance["statistic"] == statistic
        assert parameter.provenance["final_test_access_count"] == 0
    warning_artifact = layers.scientific.parameters["m1_warning_model_artifact"]
    assert warning_artifact.value.endswith("M1_SIGNED_WARNING_MODEL_V1.pt")
    assert warning_artifact.provenance["selection_rule"] == "FIRST_PRE_REGISTERED_W_SEED"
    assert warning_artifact.provenance["training_seed"] == 20260813
    assert warning_artifact.provenance["final_test_access_count"] == 0
    assert layers.engineering.device == "cpu"
    assert resolve_raw_roots(layers.engineering) == {
        "data1": PROJECT_ROOT / "data1", "data2": PROJECT_ROOT / "data2"}
