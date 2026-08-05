from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file


CONTRACT_ID = "AIR_CHAIN_CORE_V2"
SCHEMA_VERSION = "air-chain-core-2.0"
EVENT_CONTRACT_ID = "AIR_CHAIN_EVENT_V2"
CHAIN_CONTRACT_ID = "IMMEDIATE_NEXT_OBSERVED_LEG_V2"
SPLIT_CONTRACT_ID = "EPISODE_START_FROZEN_SPLIT_V2"
REFERENCE_CONTRACT_ID = "TRAIN_ONLY_REFERENCE_V2"
OBSERVATION_CONTRACT_ID = "SOURCE_GLOBAL_OBSERVATION_V2"
COLUMN_REGISTRY_CONTRACT_ID = "RAW_SOURCE_COLUMN_REGISTRY_V2"
RESEARCH_CODE_REVISION = "AIR_CHAIN_CORE_V2_R2"


@dataclass(frozen=True)
class ResumeContract:
    """Immutable identity for a resumable Core V2 staging build."""

    contract_id: str
    schema_version: str
    research_code_revision: str
    frozen_config_hash: str
    source_manifest_hash: str
    source_schema_hash: str
    request_contract_hash: str
    request_rows_hash: str
    episode_interval_hash: str
    cache_key: str
    expected_partitions: tuple[str, ...]
    git_commit: str = "UNKNOWN"
    git_dirty: bool = False
    implementation_hash: str | None = None
    implementation_hash_status: str = "WARNING"
    implementation_file_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["expected_partitions"] = list(self.expected_partitions)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResumeContract":
        return cls(
            contract_id=str(payload["contract_id"]),
            schema_version=str(payload["schema_version"]),
            research_code_revision=str(payload["research_code_revision"]),
            frozen_config_hash=str(payload["frozen_config_hash"]),
            source_manifest_hash=str(payload["source_manifest_hash"]),
            source_schema_hash=str(payload["source_schema_hash"]),
            request_contract_hash=str(payload["request_contract_hash"]),
            request_rows_hash=str(payload["request_rows_hash"]),
            episode_interval_hash=str(payload["episode_interval_hash"]),
            cache_key=str(payload.get("cache_key", "")),
            expected_partitions=tuple(sorted(str(value) for value in payload.get("expected_partitions", ()))),
            git_commit=str(payload.get("git_commit", "UNKNOWN")),
            git_dirty=bool(payload.get("git_dirty", False)),
            implementation_hash=(
                str(payload["implementation_hash"])
                if payload.get("implementation_hash")
                else None
            ),
            implementation_hash_status=str(
                payload.get("implementation_hash_status", "WARNING")
            ),
            implementation_file_count=int(payload.get("implementation_file_count", 0)),
        )


class SupportLevel(str, Enum):
    OFFICIAL_OBSERVED = "OFFICIAL_OBSERVED"
    RECONSTRUCTED_HIGH = "RECONSTRUCTED_HIGH"
    SUPPORTED_PROXY = "SUPPORTED_PROXY"
    FALLBACK_PROXY = "FALLBACK_PROXY"
    UNSUPPORTED = "UNSUPPORTED"


class EventName(str, Enum):
    ATOT_MINUS = "ATOT_MINUS"
    ALDT_MINUS = "ALDT_MINUS"
    AIBT_MINUS = "AIBT_MINUS"
    AOBT_PLUS = "AOBT_PLUS"
    ATOT_PLUS = "ATOT_PLUS"


class ChainSupportLevel(str, Enum):
    OFFICIAL_ROTATION = "OFFICIAL_ROTATION"
    SCHEDULE_AIRCRAFT_MATCH = "SCHEDULE_AIRCRAFT_MATCH"
    RECONSTRUCTED_CHAIN = "RECONSTRUCTED_CHAIN"
    OBSERVED_CHAIN_PROXY = "OBSERVED_CHAIN_PROXY"
    UNSUPPORTED = "UNSUPPORTED"


class ChainMatchStatus(str, Enum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMATCHED = "UNMATCHED"
    UNSUPPORTED = "UNSUPPORTED"


def stable_id(*values: Any, length: int = 32) -> str:
    payload = "|".join("" if pd.isna(value) else str(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def utc_series(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="coerce")


def core_output_root(cfg: dict[str, Any], override: str | Path | None = None) -> Path:
    if override is not None:
        root = Path(override)
        return root if root.is_absolute() else (Path.cwd() / root).resolve()
    return cfg["project_root"] / "output_core" / cfg["mode"] / CONTRACT_ID


IMPLEMENTATION_DEPENDENCIES = (
    "pre/main.py",
    "pre/src/core/**/*.py",
    "pre/src/input.py",
    "pre/src/input_sources.py",
    "pre/src/inventory.py",
    "pre/src/state.py",
    "pre/src/episode.py",
    "pre/src/passenger_fit.py",
    "pre/src/pipeline_config.py",
    "pre/config/schema/*.yaml",
)


def implementation_hash(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
    if (root / "src/core").is_dir() and not (root / "pre/src/core").is_dir():
        root = root.parent
    files: dict[str, str] = {}
    for pattern in IMPLEMENTATION_DEPENDENCIES:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                files[path.relative_to(root).as_posix()] = sha256_file(path)
    if not files:
        return {
            "status": "WARNING",
            "reason": "IMPLEMENTATION_HASH_SCOPE_EMPTY",
            "hash": None,
            "file_count": 0,
        }
    return {
        "status": "PASS",
        "reason": "",
        "hash": object_hash({"scope": list(IMPLEMENTATION_DEPENDENCIES), "files": files}),
        "file_count": len(files),
    }


def frozen_research_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical scientific/data identity for Core V2 R2."""
    return {
        "contract_id": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "research_code_revision": RESEARCH_CODE_REVISION,
        "labels": cfg.get("labels", {}),
        "splits": cfg.get("splits", {}),
        "airport_cohort": {
            "core": cfg.get("airports", {}).get("core", []),
            "regions": cfg.get("airports", {}).get("regions", {}),
        },
        "event_contract": {
            "event_specs": cfg.get("event_specs", {}),
            "availability_lag_minutes": cfg.get("availability_lag_minutes", {}),
            "support_level_mapping": cfg.get("event_support_level_mapping", {}),
            "reconstruction_methods": cfg.get("event_reconstruction_methods", {}),
        },
        "chain_contract": cfg.get("predecessor_matching", {}),
        "request_contract": {
            "state_lookback_minutes": cfg.get("state_vectors", {}).get("lookback_minutes"),
            "flow_lookback_minutes": cfg.get("flow", {}).get("lookback_minutes"),
            "availability_semantics": "SOURCE_GLOBAL_NATIVE_EVENT_TIME",
        },
        "source_schema": cfg.get("sources", {}),
        "source_admission": {
            "state_vectors": cfg.get("state_vectors", {}),
            "flow": cfg.get("flow", {}),
            "validation": cfg.get("validation", {}),
        },
        "retention_rules": cfg.get("core_schema", {}).get("retention_rules", {}),
        "partitioning": cfg.get("core_schema", {}).get("partitioning", {}),
        "reference_contract": {
            "rules": cfg.get("references", {}),
            "fit_split": "train",
            "deduplicate": "observation_id",
        },
        "eligibility_contract": {
            "formal_eligible": "DEPRECATED_COMPATIBILITY_ALIAS",
            "engineering_source": "engineering_eligible",
            "observed_proxy_scientific_eligible": False,
        },
        "membership_contract": {
            "identity": {
                "state": "aircraft_id",
                "weather": "airport_id",
                "flow": "airport_id",
            },
            "interval": "request_start_closed_request_end_closed",
            "partition_unit": "source_date",
            "many_to_many": True,
            "roles": [
                "PREDECESSOR_HISTORY", "PREDECESSOR_ACTIVE",
                "TURNAROUND_CONTEXT", "SUCCESSOR_CONTEXT",
                "AIRPORT_CONTEXT", "WEATHER_CONTEXT",
            ],
        },
    }


def frozen_config_hash(cfg: dict[str, Any]) -> str:
    return object_hash(frozen_research_config(cfg))


def config_hash(cfg: dict[str, Any]) -> str:
    """Compatibility alias; V2 R2 manifests use ``frozen_config_hash``."""
    return frozen_config_hash(cfg)


def git_metadata(project_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
            text=True, check=True,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True,
            text=True, check=True,
        ).stdout
        return {"git_commit": commit, "git_dirty": bool(porcelain.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "UNKNOWN", "git_dirty": True}


def schema_hash(cfg: dict[str, Any]) -> str:
    return object_hash(cfg["core_schema"])


def contract_hashes(cfg: dict[str, Any]) -> dict[str, str]:
    chain = cfg.get("predecessor_matching", {})
    return {
        "event_contract_hash": object_hash(
            {
                "id": EVENT_CONTRACT_ID,
                "event_specs": cfg.get("event_specs", {}),
                "availability_lag": cfg.get("availability_lag_minutes", {}),
                "support_level_mapping": cfg.get("event_support_level_mapping", {}),
                "reconstruction_methods": cfg.get("event_reconstruction_methods", {}),
                "availability": "completed_flightlist_lastseen",
            }
        ),
        "chain_contract_hash": object_hash(
            {
                "id": CHAIN_CONTRACT_ID,
                "gap_threshold_minutes": chain.get("gap_threshold_minutes"),
                "administrative_hard_ceiling_minutes": chain.get("administrative_hard_ceiling_minutes"),
                "successor_search": "ALL_FUTURE_CANDIDATES_FIRST_VALID_TIME",
                "identity_conflicts": ["registration", "typecode"],
            }
        ),
        "split_contract_hash": object_hash({"id": SPLIT_CONTRACT_ID, "splits": cfg["splits"]}),
        "reference_contract_hash": object_hash(
            {
                "id": REFERENCE_CONTRACT_ID,
                "fit_split": "train",
                "membership_join": "observations JOIN observation_membership JOIN episodes",
                "deduplicate": "observation_id",
            }
        ),
        "observation_contract_hash": object_hash(
            {
                "id": OBSERVATION_CONTRACT_ID,
                "source_schemas": cfg.get("sources", {}),
                "history_minutes": cfg["state_vectors"]["lookback_minutes"],
                "retention_rules": cfg.get("core_schema", {}).get("retention_rules", {}),
                "partitioning": cfg["core_schema"]["partitioning"]["observations"],
                "availability_semantics": "source_global_native_event_time",
                "membership_semantics": "many_to_many_chain_interval",
            }
        ),
        "column_registry_contract_hash": object_hash(
            {
                "id": COLUMN_REGISTRY_CONTRACT_ID,
                "required_fields": cfg.get("core_schema", {}).get("column_registry_required", []),
                "raw_sources": cfg.get("sources", {}),
                "roles": cfg.get("core_schema", {}).get("role_definitions", []),
            }
        ),
    }
