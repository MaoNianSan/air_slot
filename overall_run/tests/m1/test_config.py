from __future__ import annotations

from pathlib import Path

import pytest

from overall_run.src.config import ConfigError, load_config
from overall_run.src.m1.config import M1ConfigError, validate_m1_config


ROOT = Path(__file__).resolve().parents[2]


def test_repository_config_selects_the_single_gru() -> None:
    config = load_config(ROOT, "fast")
    settings = validate_m1_config(config.scientific["m1"])
    assert settings.hidden_size == 8
    assert settings.hidden_size_sensitivity == (16,)
    assert config.scientific["paths"]["pre_output"].endswith(
        "output_core/{mode}/AIR_CHAIN_CORE_V2"
    )


def test_retired_m1_key_is_rejected() -> None:
    config = load_config(ROOT, "fast").scientific["m1"].copy()
    config["quant" + "iles"] = [0.5]
    with pytest.raises(M1ConfigError, match="RETIRED_M1_CONFIG_KEY"):
        validate_m1_config(config)


def test_top_level_retired_tuning_key_is_rejected(tmp_path) -> None:
    override = tmp_path / "override.yaml"
    override.write_text("m1_tuning: {}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="RETIRED_M1_CONFIG_KEY"):
        load_config(ROOT, "fast", override=override)
