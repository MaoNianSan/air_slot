from __future__ import annotations

import pandas as pd

from ..observation_builder import MEMBERSHIP_ONLY_COLUMNS, _align


def retain_source_global_rows(frame: pd.DataFrame) -> pd.DataFrame:
    output = _align(frame)
    output = output.drop(
        columns=[column for column in MEMBERSHIP_ONLY_COLUMNS if column in output],
        errors="ignore",
    ).sort_values("observation_id", kind="mergesort")
    for column in ["observation_time", "event_time", "availability_time"]:
        output[column] = pd.to_datetime(output[column], utc=True, errors="coerce")
    return output.drop_duplicates("observation_id", keep="last")
