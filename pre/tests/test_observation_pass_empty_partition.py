from __future__ import annotations

import pandas as pd

from src.core.observation_dataset import write_observation_dataset
from src.state import StateStore
from test_core_v2_synthetic_resume_smoke import _resume_contract


def test_observation_dataset_records_legal_empty_partition_without_file(tmp_path) -> None:
    requests = pd.DataFrame(
        [
            {
                "chain_episode_id": f"c{day}",
                "source": "weather",
                "airport": "EHAM",
                "request_start": pd.Timestamp(f"2022-05-0{day} 09:00", tz="UTC"),
                "request_end": pd.Timestamp(f"2022-05-0{day} 11:00", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": "train",
            }
            for day in (2, 3)
        ]
    )
    metar = pd.DataFrame(
        [
            {
                "airport": "EHAM",
                "observation_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                "availability_time": pd.Timestamp("2022-05-02 10:00", tz="UTC"),
                "source_record_id": "metar:2",
                "raw_source_file": "metar.csv",
                "raw_source_hash": "9" * 64,
            }
        ]
    )
    store = StateStore(tmp_path / "candidate", tmp_path / "flow", pd.DataFrame())
    root = tmp_path / "observations"
    result = write_observation_dataset(
        root,
        requests,
        store,
        metar,
        pd.DataFrame(),
        "quiet",
        resume_contract=_resume_contract(),
    )
    empty_key = "source=weather/observation_date=2022-05-03"
    assert result.partition_manifest["partitions"][empty_key]["status"] == "PASS_EMPTY"
    assert not (root / empty_key / "part-00000.parquet").exists()
    assert sum(result.partition_counts.values()) == 2
