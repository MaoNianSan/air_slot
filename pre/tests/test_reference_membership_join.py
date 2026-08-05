from __future__ import annotations

import pandas as pd

from core_fixtures import core_cfg
from src.core.reference_builder import _observation_rows


def test_reference_uses_train_membership_and_deduplicates_observation(tmp_path) -> None:
    root = tmp_path / "observations"
    part = root / "source=weather" / "observation_date=2022-05-02"
    part.mkdir(parents=True)
    pd.DataFrame([{
        "observation_id": "o1", "airport_id": "EHAM",
        "event_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
        "wind_speed": 10.0, "visibility": 5.0, "temperature": 60.0,
        "source_hash": "a" * 64,
    }]).to_parquet(part / "part.parquet", index=False)
    membership = tmp_path / "observation_membership"
    membership_part = (
        membership / "source=weather" / "observation_date=2022-05-02"
    )
    membership_part.mkdir(parents=True)
    pd.DataFrame([
        {"observation_id": "o1", "source": "weather", "split": "train"},
        {"observation_id": "o1", "source": "weather", "split": "train"},
    ]).to_parquet(membership_part / "part-00000.parquet", index=False)
    rows = _observation_rows(root, "weather", core_cfg(), membership)
    assert rows
    assert all(row["cell_size"] == 1 for row in rows)
