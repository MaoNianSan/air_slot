from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file


CONTRACT_ID = "AIR_CHAIN_CORE_V1"
SCHEMA_VERSION = "air-chain-core-1.0"
EVENT_CONTRACT_ID = "AIR_CHAIN_EVENT_V1"
CHAIN_CONTRACT_ID = "IMMEDIATE_NEXT_OBSERVED_LEG_V1"
SPLIT_CONTRACT_ID = "EPISODE_START_FROZEN_SPLIT_V1"
REFERENCE_CONTRACT_ID = "TRAIN_ONLY_REFERENCE_V1"
OBSERVATION_CONTRACT_ID = "NATIVE_INTERVAL_OBSERVATION_V1"


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


def implementation_hash() -> str:
    root = Path(__file__).resolve().parent
    files = sorted(root.glob("*.py"))
    return object_hash({path.name: sha256_file(path) for path in files})


def schema_hash(cfg: dict[str, Any]) -> str:
    return object_hash(cfg["core_schema"])


def contract_hashes(cfg: dict[str, Any]) -> dict[str, str]:
    chain = cfg.get("predecessor_matching", {})
    return {
        "event_contract_hash": object_hash(
            {"id": EVENT_CONTRACT_ID, "availability": "completed_flightlist_lastseen"}
        ),
        "chain_contract_hash": object_hash(
            {
                "id": CHAIN_CONTRACT_ID,
                "gap_threshold_minutes": chain.get("gap_threshold_minutes"),
                "administrative_hard_ceiling_minutes": chain.get(
                    "administrative_hard_ceiling_minutes"
                ),
            }
        ),
        "split_contract_hash": object_hash(
            {"id": SPLIT_CONTRACT_ID, "splits": cfg["splits"]}
        ),
        "reference_contract_hash": object_hash(
            {"id": REFERENCE_CONTRACT_ID, "fit_split": "train"}
        ),
        "observation_contract_hash": object_hash(
            {
                "id": OBSERVATION_CONTRACT_ID,
                "history_minutes": cfg["state_vectors"]["lookback_minutes"],
                "partitioning": cfg["core_schema"]["partitioning"]["observations"],
            }
        ),
    }
