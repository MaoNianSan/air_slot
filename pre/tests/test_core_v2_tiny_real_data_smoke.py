from __future__ import annotations

import re

import pandas as pd

from src.core.contracts import stable_id
from src.core.observation_builder import MEMBERSHIP_ONLY_COLUMNS, _align
from src.core.observations import schema_fingerprint, validate_resumable_partition
from src.core.membership import build_membership
from src.input_sources import iter_csv_tar, sha256_file
from src.pipeline_config import load_config
from src.state import _standardize_chunk


def test_tiny_real_state_partition_smoke(tmp_path) -> None:
    cfg = load_config(mode="fast")
    source_root = cfg["data_root"] / "raw" / "opensky" / "state_vectors" / "2022"
    path = next(source_root.rglob("states_*.csv.tar"))
    raw = next(iter_csv_tar(path, chunksize=2_000))
    date_text = path.name[len("states_"):len("states_") + 10]
    match = re.search(r"states_(\d{4}-\d{2}-\d{2})-(\d{2})", path.name)
    assert match is not None
    hour = int(match.group(2))
    standardized = _standardize_chunk(
        raw,
        cfg["sources"]["state_vectors"],
        path,
        sha256_file(path),
        pd.Timestamp(date_text),
        hour,
        "FORMAL_COMPLETE_DAY",
        cfg,
        0,
    )
    assert {"baroaltitude", "geoaltitude", "callsign", "alert", "spi", "squawk", "lastposupdate", "lastcontact"}.issubset(standardized.columns)
    selected = standardized.dropna(subset=["event_time", "source_record_id"]).head(50).copy()
    selected["source"] = "state"
    selected["observation_time"] = selected["event_time"]
    selected["observation_date"] = pd.to_datetime(selected["event_time"], utc=True).dt.strftime("%Y-%m-%d")
    selected["aircraft_id"] = selected["icao24"]
    selected["flight_id"] = pd.NA
    selected["airport_id"] = pd.NA
    selected["source_file"] = selected["raw_source_file"]
    selected["source_hash"] = selected["raw_source_hash"]
    selected["observation_id"] = [stable_id("state", value) for value in selected["source_record_id"]]
    frame = _align(selected)
    frame = frame.drop(
        columns=[column for column in MEMBERSHIP_ONLY_COLUMNS if column in frame],
        errors="ignore",
    )
    date_value = str(frame.iloc[0].observation_date)
    key = f"source=state/observation_date={date_value}"
    root = tmp_path / "observations"
    partition = root / key / "part-00000.parquet"
    partition.parent.mkdir(parents=True)
    frame.to_parquet(partition, index=False)
    import pyarrow.parquet as pq

    schema = pq.ParquetFile(partition).schema_arrow
    columns = list(schema.names)
    fingerprint = schema_fingerprint(columns, [str(schema.field(name).type) for name in columns])
    manifest = {"partitions": {key: {
        "status": "PASS", "relative_path": partition.relative_to(root).as_posix(),
        "file_hash": sha256_file(partition), "schema_fingerprint": fingerprint,
        "source": "state", "observation_date": date_value, "row_count": len(frame),
    }}}
    reusable, reason, projection, _, _, rows = validate_resumable_partition(partition, key, {key}, manifest)
    assert reusable, reason
    assert rows == len(frame)
    first = projection.iloc[0]
    requests = pd.DataFrame([{
        "chain_episode_id": "real-smoke-chain", "source": "state", "icao24": first.aircraft_id,
        "airport": "", "request_start": first.event_time - pd.Timedelta(minutes=1),
        "request_end": first.event_time + pd.Timedelta(minutes=1),
        "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL", "split": "train",
    }])
    membership = build_membership(projection, requests)
    assert not membership.empty
