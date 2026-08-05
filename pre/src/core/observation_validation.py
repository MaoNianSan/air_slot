from __future__ import annotations

import pandas as pd


def validate_observations(observations: pd.DataFrame) -> dict[str, object]:
    duplicate_ids = int(observations["observation_id"].duplicated().sum())
    missing_hash = int(observations["source_hash"].fillna("").astype(str).str.len().eq(0).sum())
    outside_interval = int(
        (
            observations["request_start"].notna()
            & (
                observations["event_time"].lt(observations["request_start"])
                | observations["event_time"].gt(observations["request_end"])
            )
        ).sum()
    )
    availability_before_event = int(
        observations["availability_time"].lt(observations["event_time"]).sum()
    )
    ratio_columns = [column for column in observations.columns if "ratio" in column.lower()]
    missing_time = int(
        observations[["observation_time", "event_time", "availability_time"]]
        .isna()
        .any(axis=1)
        .sum()
    )
    status = (
        "PASS"
        if not any(
            [duplicate_ids, missing_hash, outside_interval, availability_before_event, ratio_columns, missing_time]
        )
        else "FAIL"
    )
    counts = observations.groupby("source").size().to_dict()
    return {
        "status": status,
        "observation_rows": len(observations),
        "rows_by_source": {str(key): int(value) for key, value in counts.items()},
        "duplicate_observation_ids": duplicate_ids,
        "missing_source_hash": missing_hash,
        "outside_request_interval": outside_interval,
        "availability_before_event": availability_before_event,
        "missing_required_time": missing_time,
        "ratio_dependency_columns": ratio_columns,
        "native_resolution_preserved": not ratio_columns,
        "on_demand_evidence_supported": status == "PASS",
    }
