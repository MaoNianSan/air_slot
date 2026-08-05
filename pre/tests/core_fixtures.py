from __future__ import annotations

import pandas as pd

from src.pipeline_config import load_config
from src.shared.flight_identity import stable_flight_id


def core_cfg() -> dict:
    cfg = load_config(mode="fast")
    cfg["runtime"]["progress_level"] = "quiet"
    return cfg


def flight(
    code: str,
    origin: str,
    destination: str,
    firstseen: str,
    lastseen: str,
    *,
    seed: bool,
    record: str,
) -> dict:
    start = pd.Timestamp(firstseen, tz="UTC")
    end = pd.Timestamp(lastseen, tz="UTC")
    return {
        "flight_id": stable_flight_id(code, origin, destination, start, end),
        "icao24": code,
        "origin": origin,
        "destination": destination,
        "firstseen_utc": start,
        "lastseen_utc": end,
        "typecode": "A320",
        "registration": "NTEST",
        "is_predecessor_seed": seed,
        "source_record_id": record,
        "raw_source_file": "flightlist.csv.gz",
        "raw_source_hash": "a" * 64,
    }


def matched_flights() -> pd.DataFrame:
    return pd.DataFrame(
        [
            flight("abc123", "EDDF", "EHAM", "2022-05-02 08:00", "2022-05-02 10:00", seed=True, record="pred"),
            flight("abc123", "EHAM", "LEMD", "2022-05-02 11:00", "2022-05-02 13:00", seed=False, record="succ"),
        ]
    )
