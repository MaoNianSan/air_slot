from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from overall_run.src.m1.adapter import load_published_bundle
from overall_run.src.m1.contracts import (
    FlightChainStage,
    M1SnapshotNode,
    OperationalReferences,
    PreBundleIdentity,
    SupportedOperationalValue,
    TargetContract,
)


UTC = timezone.utc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def build_published_bundle(tmp_path: Path) -> Path:
    root = tmp_path / "output_core" / "fast" / "AIR_CHAIN_CORE_V2"
    root.mkdir(parents=True)
    episodes = pd.DataFrame(
        [
            {
                "chain_episode_id": "ep-1",
                "predecessor_flight_id": "flight-minus",
                "successor_flight_id": "flight-plus",
                "chain_support_level": "OFFICIAL_ROTATION",
                "successor_sobt": pd.Timestamp("2026-01-01 11:00", tz="UTC"),
                "turnaround_floor_minutes": 30.0,
                "turnaround_reference_type": "OFFICIAL_FLOOR",
                "turnaround_reference_support": "OFFICIAL_OBSERVED",
                "turnaround_reference_version": "turn-v1",
                "successor_sobt_support_level": "OFFICIAL_OBSERVED",
                "successor_sobt_reference_version": "sobt-v1",
                "taxi_reference_minutes": 15.0,
                "taxi_reference_support": "SUPPORTED_PROXY",
                "taxi_reference_version": "taxi-v1",
                "episode_start_time": pd.Timestamp("2026-01-01 10:00", tz="UTC"),
                "episode_end_time": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
                "split": "train",
                "airport": "EHAM",
            },
            {
                "chain_episode_id": "ep-2",
                "predecessor_flight_id": "flight-minus-2",
                "successor_flight_id": "flight-plus-2",
                "chain_support_level": "OBSERVED_CHAIN_PROXY",
                "successor_sobt": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
                "turnaround_floor_minutes": 30.0,
                "turnaround_reference_type": "OFFICIAL_FLOOR",
                "turnaround_reference_support": "OFFICIAL_OBSERVED",
                "turnaround_reference_version": "turn-v1",
                "successor_sobt_support_level": "OFFICIAL_OBSERVED",
                "successor_sobt_reference_version": "sobt-v1",
                "taxi_reference_minutes": 15.0,
                "taxi_reference_support": "SUPPORTED_PROXY",
                "taxi_reference_version": "taxi-v1",
                "episode_start_time": pd.Timestamp("2026-01-01 11:00", tz="UTC"),
                "episode_end_time": pd.Timestamp("2026-01-01 13:00", tz="UTC"),
                "split": "validation",
                "airport": "EHAM",
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "event_id": "event-aldt",
                "flight_id": "flight-minus",
                "event_name": "ALDT_MINUS",
                "event_time": pd.Timestamp("2026-01-01 10:20", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 10:21", tz="UTC"),
                "support_level": "OFFICIAL_OBSERVED",
                "reconstruction_method": "DIRECT",
                "confidence": 1.0,
                "source_hash": "a" * 64,
            },
            {
                "event_id": "event-ib",
                "flight_id": "flight-minus",
                "event_name": "AIBT_MINUS",
                "event_time": pd.Timestamp("2026-01-01 10:30", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 10:31", tz="UTC"),
                "support_level": "OFFICIAL_OBSERVED",
                "reconstruction_method": "DIRECT",
                "confidence": 1.0,
                "source_hash": "b" * 64,
            },
            {
                "event_id": "event-ob",
                "flight_id": "flight-plus",
                "event_name": "AOBT_PLUS",
                "event_time": pd.Timestamp("2026-01-01 11:10", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 11:11", tz="UTC"),
                "support_level": "OFFICIAL_OBSERVED",
                "reconstruction_method": "DIRECT",
                "confidence": 1.0,
                "source_hash": "c" * 64,
            },
            {
                "event_id": "event-tx",
                "flight_id": "flight-plus",
                "event_name": "ATOT_PLUS",
                "event_time": pd.Timestamp("2026-01-01 11:30", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 11:31", tz="UTC"),
                "support_level": "OFFICIAL_OBSERVED",
                "reconstruction_method": "DIRECT",
                "confidence": 1.0,
                "source_hash": "d" * 64,
            },
        ]
    )
    observations = pd.DataFrame(
        [
            {
                "observation_id": "obs-available",
                "source": "weather",
                "observation_date": "2026-01-01",
                "observation_time": pd.Timestamp("2026-01-01 09:50", tz="UTC"),
                "event_time": pd.Timestamp("2026-01-01 09:50", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 09:55", tz="UTC"),
                "source_record_id": "weather-1",
                "source_file": "weather.parquet",
                "source_hash": "e" * 64,
                "airport_id": "EHAM",
                "aircraft_id": None,
                "flight_id": None,
                "wind_speed": 10.0,
            },
            {
                "observation_id": "obs-future-availability",
                "source": "weather",
                "observation_date": "2026-01-01",
                "observation_time": pd.Timestamp("2026-01-01 09:50", tz="UTC"),
                "event_time": pd.Timestamp("2026-01-01 09:50", tz="UTC"),
                "availability_time": pd.Timestamp("2026-01-01 10:45", tz="UTC"),
                "source_record_id": "weather-2",
                "source_file": "weather.parquet",
                "source_hash": "f" * 64,
                "airport_id": "EHAM",
                "aircraft_id": None,
                "flight_id": None,
                "wind_speed": 99.0,
            },
        ]
    )
    membership = pd.DataFrame(
        [
            {
                "observation_id": observation_id,
                "source": "weather",
                "chain_episode_id": episode_id,
                "membership_role": "AIRPORT_CONTEXT",
                "availability_supported": True,
            }
            for observation_id in observations["observation_id"]
            for episode_id in ("ep-1", "ep-2")
        ]
    )
    calibration = pd.DataFrame(
        [{"reference_id": "ref-1", "fit_split": "train", "reference_value": 10.0}]
    )
    evidence = pd.DataFrame(
        [
            {
                "evidence_id": "evidence-1",
                "variable_name": "wind_speed",
                "support_level": "SUPPORTED_PROXY",
                "fallback_level": "NONE",
            }
        ]
    )
    direct = {
        "episodes": episodes,
        "events": events,
        "calibration": calibration,
        "evidence_audit": evidence,
    }
    for name, frame in direct.items():
        frame.to_parquet(root / f"{name}.parquet", index=False)
    registry = {
        "columns": [
            {
                "table": "observations",
                "standard_column": "wind_speed",
                "model_input_allowed": True,
            },
            {
                "table": "observations",
                "standard_column": "visibility",
                "model_input_allowed": True,
            },
            {
                "table": "episodes",
                "standard_column": "airport",
                "model_input_allowed": True,
            },
        ]
    }
    (root / "column_registry.yaml").write_text(
        yaml.safe_dump(registry, sort_keys=True), encoding="utf-8"
    )

    partition_specs = (
        ("observations", "observation_partition_manifest.json", observations),
        (
            "observation_membership",
            "observation_membership_partition_manifest.json",
            membership,
        ),
    )
    for directory, manifest_name, frame in partition_specs:
        partition_root = root / directory
        data_path = partition_root / "source=weather" / "part-00000.parquet"
        data_path.parent.mkdir(parents=True)
        frame.to_parquet(data_path, index=False)
        _write_json(
            partition_root / manifest_name,
            {
                "partitions": {
                    "source=weather": {
                        "status": "PASS",
                        "relative_path": "source=weather/part-00000.parquet",
                        "file_hash": sha256_file(data_path),
                        "row_count": len(frame),
                    }
                }
            },
        )

    file_hashes = {
        name: sha256_file(root / f"{name}.parquet") for name in direct
    }
    file_hashes.update(
        {
            "column_registry": sha256_file(root / "column_registry.yaml"),
            "observation_partition_manifest": sha256_file(
                root / "observations" / "observation_partition_manifest.json"
            ),
            "membership_partition_manifest": sha256_file(
                root
                / "observation_membership"
                / "observation_membership_partition_manifest.json"
            ),
        }
    )
    _write_json(
        root / "pre_manifest.json",
        {
            "contract_id": "AIR_CHAIN_CORE_V2",
            "schema_version": "air-chain-core-2.0",
            "research_code_revision": "AIR_CHAIN_CORE_V2_R2",
            "mode": "fast",
            "source_manifest_hash": "1" * 64,
            "frozen_config_hash": "2" * 64,
            "git_commit": "3" * 40,
            "file_hashes": file_hashes,
        },
    )
    return root


@pytest.fixture
def published_root(tmp_path: Path) -> Path:
    return build_published_bundle(tmp_path)


@pytest.fixture
def published_bundle(published_root: Path):
    return load_published_bundle(published_root)


@pytest.fixture
def input_bundle_factory():
    identity = PreBundleIdentity(
        contract_id="AIR_CHAIN_CORE_V2",
        schema_version="air-chain-core-2.0",
        research_code_revision="AIR_CHAIN_CORE_V2_R2",
        pre_manifest_hash="a" * 64,
        source_manifest_hash="b" * 64,
        frozen_config_hash="c" * 64,
        git_commit="d" * 40,
        mode="fast",
    )
    contracts = {
        name: TargetContract(
            target_name=name,
            target_semantics=name,
            active=True,
            m1_support_level="OFFICIAL_OPERATIONAL",
            pre_event_support_levels={},
            chain_support_level="OFFICIAL_ROTATION",
            target_reference=name,
            target_units="minutes",
            target_time_uncertainty_seconds=None,
            inactive_reason=None,
        )
        for name in ("R_IB", "R_OB", "T_TX")
    }

    def supported(value: object, field: str) -> SupportedOperationalValue:
        return SupportedOperationalValue(
            value=value,
            active=True,
            support_level="OFFICIAL_OPERATIONAL",
            source_field=field,
            source_event_id=None,
            availability_time=None,
            reference_version="fixture-v1",
            inactive_reason=None,
        )

    references = OperationalReferences(
        successor_sobt=supported(datetime(2026, 1, 1, 11, 0, tzinfo=UTC), "successor_sobt"),
        turnaround_floor_minutes=supported(30.0, "turnaround_floor_minutes"),
        taxi_reference_minutes=supported(15.0, "taxi_reference_minutes"),
        predecessor_inblock_observed=SupportedOperationalValue(
            None, False, "UNSUPPORTED", None, None, None, None, "NOT_OBSERVED"
        ),
        successor_offblock_observed=SupportedOperationalValue(
            None, False, "UNSUPPORTED", None, None, None, None, "NOT_OBSERVED"
        ),
        successor_takeoff_observed=SupportedOperationalValue(
            None, False, "UNSUPPORTED", None, None, None, None, "NOT_OBSERVED"
        ),
    )

    def factory(**overrides: Any) -> M1SnapshotNode:
        payload: dict[str, Any] = {
            "episode_id": "ep-1",
            "snapshot_id": "snapshot-1",
            "snapshot_version": 1,
            "query_time": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            "information_cutoff": datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            "pre_bundle_identity": identity,
            "feature_vector": (10.0,),
            "feature_schema_hash": "fixture-schema-hash",
            "source_observation_ids": ("obs-1",),
            "flight_chain_stage": FlightChainStage.PREDECESSOR_ENROUTE,
            "evidence_status": {"wind_speed": "SUPPORTED_PROXY"},
            "fallback_status": {"wind_speed": "NONE"},
            "target_contracts": contracts,
            "observed_event_mask": {},
            "operational_references": references,
            "state_reset_signal": False,
        }
        payload.update(overrides)
        return M1SnapshotNode(**payload)

    return factory
