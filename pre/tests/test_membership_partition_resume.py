from __future__ import annotations

from core_fixtures import core_cfg
from membership_dataset_test_utils import (
    weather_observation,
    weather_request,
    write_observation_partition,
)
from src.core.membership_dataset import write_membership_dataset


def test_membership_partition_resume_reuses_valid_file(tmp_path) -> None:
    cfg = core_cfg()
    cfg["core_membership"]["workers"] = 1
    observations_root = tmp_path / "observations"
    write_observation_partition(
        observations_root,
        weather_observation(),
        source="weather",
        observation_date="2022-05-02",
    )
    membership_root = tmp_path / "observation_membership"
    first = write_membership_dataset(
        membership_root, observations_root, weather_request(), cfg, "quiet"
    )
    partition = next(membership_root.rglob("*.parquet"))
    first_mtime = partition.stat().st_mtime_ns
    second = write_membership_dataset(
        membership_root, observations_root, weather_request(), cfg, "quiet"
    )
    assert second.dataset_hash == first.dataset_hash
    assert partition.stat().st_mtime_ns == first_mtime
    assert {
        record["resume_status"]
        for record in second.partition_manifest["partitions"].values()
    } == {"REUSED"}
