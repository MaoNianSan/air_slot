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
    assert layers.scientific.parameters["m1_hidden_size"].value is None
    assert layers.scientific.parameters["m1_hidden_size_candidates"].value == [16,32]
    assert layers.scientific.parameters["scenario_count"].value == 1000
    assert layers.scientific.parameters["weather_max_age_minutes"].value == 60
    assert layers.scientific.parameters["cloud_encoding"].value == "both"
    assert layers.scientific.parameters["m1_r_ib_max_finite_minutes"].value == 360
    assert layers.scientific.parameters["m1_r_ob_max_finite_minutes"].value == 180
    assert layers.scientific.parameters["m1_t_tx_max_finite_minutes"].value == 60
    for name in ("m1_r_ib_max_finite_minutes", "m1_r_ob_max_finite_minutes",
                 "m1_t_tx_max_finite_minutes"):
        provenance = layers.scientific.parameters[name].provenance
        assert provenance["selection_state"] == "DEVELOPMENT_FROZEN"
        assert "Calibration 2019-07" in provenance["excluded_splits"]
    assert layers.engineering.device == "cpu"
    assert resolve_raw_roots(layers.engineering) == {
        "data1": PROJECT_ROOT / "data1", "data2": PROJECT_ROOT / "data2"}
