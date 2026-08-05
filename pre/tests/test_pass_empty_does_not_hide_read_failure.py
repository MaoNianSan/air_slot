from __future__ import annotations

import json

import pandas as pd
import pytest

from src.core.observation_dataset import write_observation_dataset
from src.state import StateStore
from test_staging_resume_contract import _contract


def test_observation_read_failure_is_fail_not_pass_empty(tmp_path, monkeypatch) -> None:
    key = "source=weather/observation_date=2022-05-02"
    contract = _contract()
    requests = pd.DataFrame(
        [
            {
                "chain_episode_id": "c1",
                "source": "weather",
                "airport": "EHAM",
                "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 11:00", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": "train",
            }
        ]
    )

    def fail(*args, **kwargs):
        raise OSError("synthetic read failure")

    monkeypatch.setattr("src.core.observation_dataset.build_weather_observations", fail)
    root = tmp_path / "observations"
    store = StateStore(tmp_path / "candidate", tmp_path / "flow", pd.DataFrame())
    with pytest.raises(OSError):
        write_observation_dataset(
            root,
            requests,
            store,
            pd.DataFrame(),
            pd.DataFrame(),
            "quiet",
            resume_contract=contract,
        )
    manifest = json.loads(
        (root / "observation_partition_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["partitions"][key]["status"] == "FAIL"
