from __future__ import annotations

from copy import deepcopy

from core_fixtures import core_cfg
from src.core.contracts import frozen_config_hash


def test_worker_count_does_not_change_frozen_config_hash() -> None:
    cfg = core_cfg()
    changed = deepcopy(cfg)
    changed["core_membership"]["workers"] = 6
    assert frozen_config_hash(changed) == frozen_config_hash(cfg)


def test_split_and_chain_rules_change_frozen_config_hash() -> None:
    cfg = core_cfg()
    split_changed = deepcopy(cfg)
    split_changed["splits"]["train"][1] = "2022-04-30"
    chain_changed = deepcopy(cfg)
    chain_changed["predecessor_matching"]["gap_threshold_minutes"] += 1
    assert frozen_config_hash(split_changed) != frozen_config_hash(cfg)
    assert frozen_config_hash(chain_changed) != frozen_config_hash(cfg)
