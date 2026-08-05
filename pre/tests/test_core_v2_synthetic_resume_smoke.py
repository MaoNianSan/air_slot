from __future__ import annotations

import pandas as pd

from src.core.contracts import ResumeContract
from src.core.observation_dataset import write_observation_dataset
from src.state import StateStore


def _resume_contract() -> ResumeContract:
    return ResumeContract(
        contract_id="AIR_CHAIN_CORE_V2",
        schema_version="air-chain-core-2.0",
        research_code_revision="AIR_CHAIN_CORE_V2_R2",
        frozen_config_hash="a" * 64,
        source_manifest_hash="b" * 64,
        source_schema_hash="c" * 64,
        request_contract_hash="d" * 64,
        request_rows_hash="e" * 64,
        episode_interval_hash="f" * 64,
        implementation_hash="3" * 64,
        implementation_hash_status="PASS",
        implementation_file_count=3,
        git_commit="1" * 40,
        cache_key="4" * 64,
        expected_partitions=(
            "source=weather/observation_date=2022-05-02",
            "source=weather/observation_date=2022-05-03",
        ),
    )


def test_two_partition_synthetic_resume_smoke(tmp_path) -> None:
    requests = pd.DataFrame([
        {
            "chain_episode_id": f"c{day}", "source": "weather", "airport": "EHAM",
            "icao24": "abc123", "request_start": pd.Timestamp(f"2022-05-0{day} 09:00", tz="UTC"),
            "request_end": pd.Timestamp(f"2022-05-0{day} 11:00", tz="UTC"),
            "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL", "split": "train",
        }
        for day in [2, 3]
    ])
    metar = pd.DataFrame([
        {
            "airport": "EHAM", "observation_time": pd.Timestamp(f"2022-05-0{day} 10:00", tz="UTC"),
            "availability_time": pd.Timestamp(f"2022-05-0{day} 10:00", tz="UTC"),
            "source_record_id": f"metar:{day}", "raw_source_file": "metar.csv",
            "raw_source_hash": "9" * 64, "skyc1": "BKN", "metar": "REALISTIC SYNTHETIC METAR",
        }
        for day in [2, 3]
    ])
    store = StateStore(tmp_path / "candidate", tmp_path / "flow", pd.DataFrame())
    root = tmp_path / "observations"
    first = write_observation_dataset(root, requests, store, metar, pd.DataFrame(), "quiet", resume_contract=_resume_contract())
    assert first.validation["status"] == "PASS"
    assert sum(first.partition_counts.values()) == 2
    second = write_observation_dataset(root, requests, store, metar, pd.DataFrame(), "quiet", resume_contract=_resume_contract())
    assert second.validation["status"] == "PASS"
    statuses = {item["resume_status"] for item in second.partition_manifest["partitions"].values()}
    assert statuses == {"REUSED"}
