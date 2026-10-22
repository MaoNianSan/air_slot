"""Formal H16 training authority must not be the fast configuration."""

from __future__ import annotations

from validation.model.m1_frozen_h16_artifact_materialization import (
    formal_training_authority,
)


def test_h16_formal_training_authority_is_not_fast_config():
    contract = formal_training_authority()
    assert contract["source"] == "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG"
    assert contract["training"]["epochs"] == 8
    assert contract["training_seed"] == 20260813
    assert contract["optional_robustness_seeds"] == [
        20260814,
        20260815,
        20260816,
        20260817,
    ]
    assert contract["splits"]["calibration"] == ["2019-07-01", "2019-07-31"]
