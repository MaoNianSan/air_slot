from __future__ import annotations

import pandas as pd

from src.core.observation_builder import _align


def test_source_specific_columns_survive_alignment() -> None:
    frame = pd.DataFrame(
        {
            "observation_id": ["o1"],
            "source": ["state"],
            "source_record_id": ["r1"],
            "source_hash": ["a" * 64],
            "geoaltitude": [1234.0],
            "callsign": ["TEST123"],
        }
    )
    aligned = _align(frame)
    assert aligned.loc[0, "geoaltitude"] == 1234.0
    assert aligned.loc[0, "callsign"] == "TEST123"

