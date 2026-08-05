from __future__ import annotations

from core_fixtures import core_cfg
from membership_dataset_test_utils import (
    weather_observation,
    weather_request,
    write_observation_partition,
)
from src.core.membership import write_membership_dataset


def test_membership_dataset_records_no_matching_identity_as_pass_empty(tmp_path) -> None:
    cfg = core_cfg()
    cfg["core_membership"]["workers"] = 1
    observations_root = tmp_path / "observations"
    key, _ = write_observation_partition(
        observations_root,
        weather_observation(airport="EHAM"),
        source="weather",
        observation_date="2022-05-02",
    )
    root = tmp_path / "observation_membership"
    result = write_membership_dataset(
        root, observations_root, weather_request(airport="EDDF"), cfg, "quiet"
    )
    record = result.partition_manifest["partitions"][key]
    assert record["status"] == "PASS_EMPTY"
    assert record["empty_reason"] == "NO_MATCHING_IDENTITY"
    assert not any((root / key).glob("*.parquet"))
