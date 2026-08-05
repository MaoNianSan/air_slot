from __future__ import annotations

import pytest
from downstream_common import FORMAL_TARGET_COLUMN, SENSITIVITY_TARGET_COLUMN

from src.pipeline import MODELS, validate_m1_target_mapping


def test_all_m1_baselines_use_raw_target() -> None:
    validate_m1_target_mapping({model: FORMAL_TARGET_COLUMN for model in MODELS})


def test_baseline_sensitivity_target_is_rejected() -> None:
    mapping = {model: FORMAL_TARGET_COLUMN for model in MODELS}
    mapping["POINT_OOF"] = SENSITIVITY_TARGET_COLUMN
    with pytest.raises(ValueError, match="PART_ADV_M1_TARGET_MISMATCH"):
        validate_m1_target_mapping(mapping)
