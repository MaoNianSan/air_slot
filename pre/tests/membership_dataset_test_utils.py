from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.observations import schema_fingerprint
from src.input import sha256_file, write_json


def write_observation_partition(
    observations_root: Path,
    frame: pd.DataFrame,
    *,
    source: str,
    observation_date: str,
) -> tuple[str, Path]:
    import pyarrow.parquet as pq

    key = f"source={source}/observation_date={observation_date}"
    path = observations_root / key / "part-00000.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    schema = pq.ParquetFile(path).schema_arrow
    fingerprint = schema_fingerprint(
        list(schema.names), [str(schema.field(name).type) for name in schema.names]
    )
    manifest = {
        "partitions": {
            key: {
                "status": "PASS",
                "relative_path": path.relative_to(observations_root).as_posix(),
                "file_hash": sha256_file(path),
                "schema_fingerprint": fingerprint,
                "source": source,
                "observation_date": observation_date,
                "row_count": len(frame),
            }
        }
    }
    write_json(manifest, observations_root / "observation_partition_manifest.json")
    return key, path


def weather_observation(
    *,
    airport: str = "EHAM",
    observation_id: str = "o1",
    timestamp: str = "2022-05-02 10:00",
) -> pd.DataFrame:
    event_time = pd.Timestamp(timestamp, tz="UTC")
    return pd.DataFrame(
        [
            {
                "observation_id": observation_id,
                "source": "weather",
                "observation_date": event_time.strftime("%Y-%m-%d"),
                "event_time": event_time,
                "availability_time": event_time,
                "airport_id": airport,
                "flight_id": pd.NA,
            }
        ]
    )


def weather_request(*, airport: str = "EHAM", split: str = "train") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "chain_episode_id": "c1",
                "source": "weather",
                "airport": airport,
                "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 11:00", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": split,
            }
        ]
    )
