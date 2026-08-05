from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core_fixtures import core_cfg, matched_flights
from src.core.chain_builder import build_chains
from src.core.column_registry import build_column_registry
from src.core.contracts import CONTRACT_ID, RESEARCH_CODE_REVISION, stable_id
from src.core.event_builder import build_events
from src.core.membership_dataset import (
    MEMBERSHIP_PARTITION_MANIFEST_NAME,
    expected_empty_schema_fingerprint as membership_empty_schema_fingerprint,
)
from src.core.observation_dataset import (
    expected_empty_schema_fingerprint as observation_empty_schema_fingerprint,
    schema_fingerprint,
)
from src.core.observation_membership import (
    build_observation_membership,
    validate_observation_membership,
)
from src.core.observation_validation import validate_observations
from src.core.pipeline import _manifest
from src.core.validation import validate_core
from src.core.writer import write_core_tables
from src.input import object_hash, sha256_file, write_json


def _fingerprint(path: Path) -> str:
    import pyarrow.parquet as pq

    schema = pq.ParquetFile(path).schema_arrow
    return schema_fingerprint(
        list(schema.names), [str(schema.field(name).type) for name in schema.names]
    )


def build_synthetic_bundle(
    root: Path,
    *,
    include_pass_empty: bool = False,
) -> dict[str, Any]:
    cfg = core_cfg()
    flights = matched_flights()
    episodes = build_chains(flights, cfg)
    events = build_events(flights, episodes, cfg)
    observation = pd.DataFrame(
        [
            {
                "observation_id": stable_id("weather", "metar:1"),
                "source": "weather",
                "observation_date": "2022-05-02",
                "observation_time": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "event_time": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "availability_time": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "source_record_id": "metar:1",
                "source_file": "metar.csv",
                "source_hash": "a" * 64,
                "airport_id": "EHAM",
                "aircraft_id": pd.NA,
                "flight_id": pd.NA,
                "wind_speed": 10.0,
                "visibility": 5.0,
                "temperature": 60.0,
            }
        ]
    )
    request = pd.DataFrame(
        [
            {
                "chain_episode_id": episodes.iloc[0].chain_episode_id,
                "source": "weather",
                "airport": "EHAM",
                "icao24": "abc123",
                "request_start": pd.Timestamp("2022-05-02 09:00", tz="UTC"),
                "request_end": pd.Timestamp("2022-05-02 12:00", tz="UTC"),
                "interval_type": "INPUT_HISTORY_AND_ACTIVE_INTERVAL",
                "split": "train",
            }
        ]
    )
    membership = build_observation_membership(observation, request)
    calibration = pd.DataFrame(
        [
            {
                "reference_id": "r1",
                "reference_type": "weather_wind_speed",
                "group_key": "EHAM",
                "statistic": "median",
                "reference_value": 10.0,
                "cell_size": 1,
                "fallback_level": "AIRPORT_TRAIN",
                "fit_start_time": pd.Timestamp("2022-01-01", tz="UTC"),
                "fit_end_time": pd.Timestamp("2022-05-01", tz="UTC"),
                "fit_split": "train",
                "source_hash": "b" * 64,
            }
        ]
    )
    evidence = pd.DataFrame(
        [
            {
                "evidence_id": "e1",
                "table": "observations",
                "entity_id": "o1",
                "variable_name": "wind_speed",
                "raw_source": "metar",
                "raw_field": "sknt",
                "source_record_id": "metar:1",
                "source_file": "metar.csv",
                "source_hash": "a" * 64,
                "event_time": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "availability_time": pd.Timestamp("2022-05-02 10:30", tz="UTC"),
                "transformation": "STANDARDIZED_MAPPING",
                "support_level": "SUPPORTED_PROXY",
                "fallback_level": "NONE",
                "missing_reason": "",
                "future_information_used": False,
            }
        ]
    )
    tables = {
        "episodes": episodes,
        "events": events,
        "calibration": calibration,
        "evidence_audit": evidence,
    }
    registry = build_column_registry(
        {**tables, "observation_membership": membership},
        cfg,
        source_columns={"weather": list(observation.columns)},
    )

    observation_root = root / "observations"
    observation_key = "source=weather/observation_date=2022-05-02"
    observation_path = observation_root / observation_key / "part-00000.parquet"
    observation_path.parent.mkdir(parents=True)
    observation.to_parquet(observation_path, index=False)
    observation_record = {
        "status": "PASS",
        "relative_path": observation_path.relative_to(observation_root).as_posix(),
        "file_hash": sha256_file(observation_path),
        "schema_fingerprint": _fingerprint(observation_path),
        "source": "weather",
        "observation_date": "2022-05-02",
        "row_count": 1,
    }
    observation_records = {observation_key: observation_record}

    membership_root = root / "observation_membership"
    membership_path = membership_root / observation_key / "part-00000.parquet"
    membership_path.parent.mkdir(parents=True)
    membership.to_parquet(membership_path, index=False)
    membership_record = {
        "status": "PASS",
        "relative_path": membership_path.relative_to(membership_root).as_posix(),
        "file_hash": sha256_file(membership_path),
        "schema_fingerprint": _fingerprint(membership_path),
        "source": "weather",
        "observation_date": "2022-05-02",
        "row_count": len(membership),
    }
    membership_records = {observation_key: membership_record}

    if include_pass_empty:
        empty_key = "source=weather/observation_date=2022-05-03"
        observation_records[empty_key] = {
            "status": "PASS_EMPTY",
            "relative_path": None,
            "file_hash": None,
            "schema_fingerprint": observation_empty_schema_fingerprint("weather"),
            "source": "weather",
            "observation_date": "2022-05-03",
            "row_count": 0,
            "empty_reason": "NO_ADMISSIBLE_SOURCE_RECORDS",
        }
        membership_records[empty_key] = {
            "status": "PASS_EMPTY",
            "relative_path": None,
            "file_hash": None,
            "schema_fingerprint": membership_empty_schema_fingerprint("weather"),
            "source": "weather",
            "observation_date": "2022-05-03",
            "row_count": 0,
            "empty_reason": "NO_ADMISSIBLE_SOURCE_RECORDS",
        }

    observation_manifest = {"partitions": observation_records}
    write_json(
        observation_manifest,
        observation_root / "observation_partition_manifest.json",
    )
    membership_manifest = {
        "contract_id": CONTRACT_ID,
        "research_code_revision": RESEARCH_CODE_REVISION,
        "partitions": membership_records,
    }
    membership_manifest_path = membership_root / MEMBERSHIP_PARTITION_MANIFEST_NAME
    write_json(membership_manifest, membership_manifest_path)

    observation_validation = validate_observations(observation)
    observation_validation.update(
        partition_counts={"weather": len(observation_records)},
        pass_empty_count=int(include_pass_empty),
    )
    membership_validation = validate_observation_membership(membership)
    membership_validation.update(
        partition_count=len(membership_records),
        pass_nonempty=1,
        pass_empty=int(include_pass_empty),
    )
    validation = validate_core(
        tables,
        observation_validation,
        registry,
        cfg,
        membership_validation=membership_validation,
    )
    assert validation["status"] == "PASS"

    table_hashes = write_core_tables(root, tables, registry, cfg["core_schema"])
    file_hashes = {
        name: sha256_file(root / f"{name}.parquet") for name in tables
    }
    file_hashes["column_registry"] = sha256_file(root / "column_registry.yaml")
    file_hashes["observation_partition_manifest"] = sha256_file(
        observation_root / "observation_partition_manifest.json"
    )
    file_hashes["membership_partition_manifest"] = sha256_file(
        membership_manifest_path
    )
    observation_hashes = {
        key: (
            record["file_hash"]
            if record["status"] == "PASS"
            else object_hash(record)
        )
        for key, record in observation_records.items()
    }
    membership_logical = {
        key: {
            field: record.get(field)
            for field in (
                "status", "row_count", "relative_path", "file_hash",
                "schema_fingerprint", "empty_reason", "source", "observation_date",
            )
        }
        for key, record in membership_records.items()
    }
    membership_dataset_hash = object_hash(membership_logical)
    inventory = pd.DataFrame(
        [
            {
                "source": "fixture",
                "relative_path": "fixture",
                "sha256": "f" * 64,
                "size_bytes": 1,
            }
        ]
    )
    manifest = _manifest(
        cfg,
        inventory,
        table_hashes["column_registry"],
        table_hashes,
        object_hash(observation_hashes),
        {
            **{name: len(frame) for name, frame in tables.items()},
            "observations": len(observation),
            "observation_membership": len(membership),
        },
        {
            "observations": {"weather": len(observation_records)},
            "observation_membership": len(membership_records),
        },
        membership_dataset_hash,
        sha256_file(membership_manifest_path),
        len(membership_records),
        len(membership),
        int(include_pass_empty),
        file_hashes,
    )
    write_json(manifest, root / "pre_manifest.json")
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    write_json(validation, reports / "core_validation.json")
    return {
        "cfg": cfg,
        "manifest": manifest,
        "validation": validation,
        "observation_path": observation_path,
        "membership_path": membership_path,
        "observation_manifest_path": observation_root / "observation_partition_manifest.json",
        "membership_manifest_path": membership_manifest_path,
    }
