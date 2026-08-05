from __future__ import annotations

import pandas as pd


def requests_for_day(
    requests: pd.DataFrame,
    source: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    return requests[
        requests["source"].eq(source)
        & requests["request_start"].lt(end)
        & requests["request_end"].ge(start)
    ].copy()


def clip_requests(
    requests: pd.DataFrame,
    source: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    subset = requests_for_day(requests, source, start, end)
    if subset.empty:
        return subset
    subset["request_start"] = subset["request_start"].clip(lower=start)
    subset["request_end"] = subset["request_end"].clip(
        upper=end - pd.Timedelta(nanoseconds=1)
    )
    return subset
