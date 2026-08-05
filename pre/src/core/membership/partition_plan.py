from __future__ import annotations

from pathlib import Path

import pandas as pd

from .interval_join import IDENTITY_COLUMNS


def partition_path(root: Path, partition_key: str) -> Path:
    return root / partition_key / "part-00000.parquet"


def requests_for_partition(
    requests: pd.DataFrame,
    source: str,
    observation_date: str,
) -> pd.DataFrame:
    day_start = pd.Timestamp(observation_date, tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    return requests[
        requests["source"].eq(source)
        & pd.to_datetime(requests["request_start"], utc=True).lt(day_end)
        & pd.to_datetime(requests["request_end"], utc=True).ge(day_start)
    ].copy()


def empty_reason(
    observations: pd.DataFrame,
    requests: pd.DataFrame,
    source: str,
) -> str:
    if observations.empty:
        return "NO_SOURCE_RECORDS"
    if requests.empty:
        return "NO_REQUEST_OVERLAP"
    observation_identity, request_identity = IDENTITY_COLUMNS[source]
    observation_values = set(
        observations[observation_identity].dropna().astype(str)
    )
    request_values = set(requests[request_identity].dropna().astype(str))
    return (
        "NO_MATCHING_IDENTITY"
        if observation_values.isdisjoint(request_values)
        else "NO_REQUEST_OVERLAP"
    )
