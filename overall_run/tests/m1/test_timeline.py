from __future__ import annotations

import pandas as pd

from overall_run.src.m1.adapter.timeline import build_timeline


def test_five_minute_timeline_and_stop_time() -> None:
    timeline = build_timeline(
        "2026-01-01T10:00:00Z", maximum_minutes=20, stop_time="2026-01-01T10:12:00Z"
    )
    assert timeline == (
        pd.Timestamp("2026-01-01 10:00", tz="UTC"),
        pd.Timestamp("2026-01-01 10:05", tz="UTC"),
        pd.Timestamp("2026-01-01 10:10", tz="UTC"),
    )
