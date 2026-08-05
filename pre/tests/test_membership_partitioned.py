from __future__ import annotations

from pathlib import Path

from core_fixtures import core_cfg
from src.core.membership.partition_plan import partition_path


def test_membership_uses_source_date_partitions() -> None:
    cfg = core_cfg()
    assert cfg["core_schema"]["partitioning"]["observation_membership"] == [
        "source",
        "observation_date",
    ]
    path = partition_path(
        Path("membership"),
        "source=weather/observation_date=2022-05-02",
    )
    assert path.as_posix().endswith(
        "membership/source=weather/observation_date=2022-05-02/part-00000.parquet"
    )
