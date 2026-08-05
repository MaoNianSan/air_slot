from __future__ import annotations

import pandas as pd
import pytest

from overall_run.src.m1.adapter.timeline import (
    deterministic_validation_split,
    episode_partition_integrity,
)


def test_validation_is_split_by_episode_in_time_order() -> None:
    episodes = pd.DataFrame(
        {
            "chain_episode_id": [f"ep-{index}" for index in range(6)],
            "episode_start_time": pd.date_range("2026-01-01", periods=6, tz="UTC"),
            "split": ["validation"] * 6,
        }
    )
    split = deterministic_validation_split(episodes, tail_fraction=0.5, minimum_episodes=2)
    assert split["validation_model"] == ("ep-0", "ep-1", "ep-2")
    assert split["calibration"] == ("ep-3", "ep-4", "ep-5")
    assert not set(split["validation_model"]) & set(split["calibration"])


def test_calibration_never_falls_back_to_test() -> None:
    episodes = pd.DataFrame(
        {
            "chain_episode_id": ["test-1", "test-2", "test-3", "test-4"],
            "episode_start_time": pd.date_range("2026-01-01", periods=4, tz="UTC"),
            "split": ["test"] * 4,
        }
    )
    with pytest.raises(ValueError, match="M1_CALIBRATION_SPLIT_UNAVAILABLE"):
        deterministic_validation_split(episodes)


def test_snapshot_partitions_cannot_cross_episode_boundaries() -> None:
    rows = pd.DataFrame(
        {"episode_id": ["a", "a", "b"], "partition": ["train", "test", "test"]}
    )
    assert not episode_partition_integrity(rows)
