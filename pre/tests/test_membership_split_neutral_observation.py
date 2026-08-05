from __future__ import annotations

import pandas as pd

from core_fixtures import core_cfg
from membership_dataset_test_utils import (
    weather_observation,
    weather_request,
    write_observation_partition,
)
from src.core.membership import write_membership_dataset


def test_membership_keeps_observations_split_neutral(tmp_path) -> None:
    cfg = core_cfg()
    cfg["core_membership"]["workers"] = 1
    observations_root = tmp_path / "observations"
    _, observation_path = write_observation_partition(
        observations_root,
        weather_observation(),
        source="weather",
        observation_date="2022-05-02",
    )
    result = write_membership_dataset(
        tmp_path / "observation_membership",
        observations_root,
        weather_request(split="validation"),
        cfg,
        "quiet",
    )
    persisted_observation = pd.read_parquet(observation_path)
    persisted_membership = pd.read_parquet(
        next((tmp_path / "observation_membership").rglob("*.parquet"))
    )
    assert "split" not in persisted_observation.columns
    assert result.row_count == 1
    assert persisted_membership["split"].tolist() == ["validation"]
