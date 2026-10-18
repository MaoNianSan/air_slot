from pathlib import Path
import pytest
from pydantic import ValidationError

from model.common.config import ScientificConfig, load_config_layers


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
    assert layers.scientific.parameters["forecast_horizons_minutes"].value == [0,30,60,120,180,240,300,360,420,480]
    assert layers.scientific.parameters["scenario_count"].value == 1000
    assert layers.engineering.device == "cpu"
