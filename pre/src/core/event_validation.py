from __future__ import annotations

import pandas as pd

from .contracts import EventName, SupportLevel


def validate_events(events: pd.DataFrame) -> dict[str, object]:
    valid_events = {value.value for value in EventName}
    valid_support = {value.value for value in SupportLevel}
    invalid_names = int((~events["event_name"].isin(valid_events)).sum())
    invalid_support = int((~events["support_level"].isin(valid_support)).sum())
    official_proxy_confusion = int(
        (
            events["source_field"].isin(["firstseen", "lastseen"])
            & events["support_level"].eq(SupportLevel.OFFICIAL_OBSERVED.value)
        ).sum()
    )
    unsupported_nonnull = int(
        (
            events["support_level"].eq(SupportLevel.UNSUPPORTED.value)
            & events["event_time"].notna()
        ).sum()
    )
    missing_source_hash = int(
        events["source_hash"].fillna("").astype(str).str.len().eq(0).sum()
    )
    supported = events[events["support_level"].ne(SupportLevel.UNSUPPORTED.value)]
    order_errors = int(
        (
            pd.to_datetime(supported["availability_time"], utc=True)
            < pd.to_datetime(supported["event_time"], utc=True)
        ).sum()
    )
    denominator = max(1, len(supported))
    status = (
        "PASS"
        if not any(
            [invalid_names, invalid_support, official_proxy_confusion, unsupported_nonnull, missing_source_hash, order_errors]
        )
        else "FAIL"
    )
    support = (
        events.groupby(["event_name", "support_level"], dropna=False)
        .size()
        .rename("rows")
        .reset_index()
        .to_dict("records")
    )
    return {
        "status": status,
        "event_rows": len(events),
        "invalid_event_names": invalid_names,
        "invalid_support_levels": invalid_support,
        "official_proxy_confusion": official_proxy_confusion,
        "unsupported_nonnull_event_time": unsupported_nonnull,
        "missing_source_hash": missing_source_hash,
        "event_order_errors": order_errors,
        "event_order_error_rate": order_errors / denominator,
        "support": support,
    }
