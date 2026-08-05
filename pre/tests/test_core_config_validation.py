from __future__ import annotations

from copy import deepcopy

import pytest

from core_fixtures import core_cfg
from src.core.contracts import frozen_config_hash
from src.pipeline_config import validate_core_v2_config, validate_shared_config


def _changed(cfg: dict, *path: str, value: object) -> dict:
    result = deepcopy(cfg)
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return result


def test_operational_settings_do_not_change_frozen_hash() -> None:
    cfg = core_cfg()
    workers = _changed(cfg, "core_membership", "workers", value=5)
    progress = _changed(cfg, "runtime", "progress_level", value="detail")
    assert frozen_config_hash(workers) == frozen_config_hash(cfg)
    assert frozen_config_hash(progress) == frozen_config_hash(cfg)


def test_scientific_and_data_rules_change_frozen_hash() -> None:
    cfg = core_cfg()
    changes = [
        _changed(cfg, "splits", "train", value=["2022-05-01", "2022-05-17"]),
        _changed(
            cfg,
            "event_specs",
            "ATOT_MINUS",
            "support_level",
            value="UNSUPPORTED",
        ),
        _changed(
            cfg,
            "predecessor_matching",
            "gap_threshold_minutes",
            value=float(cfg["predecessor_matching"]["gap_threshold_minutes"]) + 1,
        ),
        _changed(
            cfg,
            "core_schema",
            "retention_rules",
            "preserve_raw_columns_unless_temporary_or_duplicate",
            value=False,
        ),
        _changed(cfg, "core_membership", "many_to_many", value=False),
    ]
    baseline = frozen_config_hash(cfg)
    assert all(frozen_config_hash(changed) != baseline for changed in changes)


def test_split_validators_reject_invalid_v2_contract() -> None:
    cfg = core_cfg()
    validate_shared_config(cfg)
    validate_core_v2_config(cfg)
    invalid = _changed(cfg, "core_membership", "partition_unit", value="single_file")
    with pytest.raises(ValueError, match="CORE_V2_MEMBERSHIP_RULES_INVALID"):
        validate_core_v2_config(invalid)
