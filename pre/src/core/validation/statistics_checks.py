from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .core import core_statistics


def compare_statistics(
    root: Path,
    tables: dict[str, pd.DataFrame],
    observations: dict[str, Any],
    membership: dict[str, Any],
    registry: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    recomputed = core_statistics(tables, observations, membership, registry)
    stored_path = root / "reports" / "core_validation.json"
    stored = json.loads(stored_path.read_text(encoding="utf-8")) if stored_path.exists() else {}
    stored_statistics = stored.get("statistics", {})
    mismatches = {
        key: {"stored": stored_statistics.get(key), "recomputed": value}
        for key, value in recomputed.items()
        if stored_statistics.get(key) != value
    }
    return {
        "status": "PASS" if not mismatches else "FAIL",
        "stored": stored_statistics,
        "recomputed": recomputed,
        "mismatches": mismatches,
    }, stored


def stored_component_mismatch(
    stored: dict[str, Any], checks: dict[str, Any], failures: list[str]
) -> bool:
    mapping = {
        "tables": "table_schemas_and_keys",
        "events": "event_contract",
        "chains": "chain_contract",
        "observations": "observations",
        "references": "reference_train_only",
        "leakage": "leakage",
        "column_registry": "column_registry",
        "membership": "membership_uniqueness",
    }
    mismatch = bool(stored) and stored.get("status") != ("PASS" if not failures else "FAIL")
    for stored_name, recomputed_name in mapping.items():
        if stored_name in stored and recomputed_name in checks:
            mismatch = mismatch or stored[stored_name].get("status") != checks[recomputed_name].get("status")
    return mismatch
