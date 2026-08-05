from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import object_hash, sha256_file
from ..state import StateStore, _cache_key, extract_state_data
from .observation_requests import observation_request_hashes


V2_REQUIRED_STATE_CACHE_COLUMNS = {
    "callsign", "alert", "spi", "squawk", "baroaltitude",
    "geoaltitude", "lastposupdate", "lastcontact",
}


def _candidate_cache_has_v2_columns(root: Path) -> bool:
    sample = next((root / "candidate_states").rglob("*.parquet"), None)
    if sample is None:
        return False
    try:
        import pyarrow.parquet as pq

        return V2_REQUIRED_STATE_CACHE_COLUMNS.issubset(
            pq.ParquetFile(sample).schema_arrow.names
        )
    except (OSError, ValueError):
        return False


def _merged_intervals(frame: pd.DataFrame) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    result: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for code, group in frame.groupby("icao24", sort=False):
        merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        for row in group.sort_values("request_start").itertuples(index=False):
            start = pd.Timestamp(row.request_start)
            end = pd.Timestamp(row.request_end)
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        result[str(code)] = merged
    return result


def _contained(
    requested: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
    cached: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]],
) -> bool:
    for code, intervals in requested.items():
        available = cached.get(code, [])
        for start, end in intervals:
            if not any(cached_start <= start and cached_end >= end for cached_start, cached_end in available):
                return False
    return True


def _legacy_cache(cfg: dict[str, Any], requests: pd.DataFrame) -> tuple[StateStore | None, dict[str, Any]]:
    root = cfg["project_root"] / "cache" / "state_extract_v2"
    manifest_path = root / "cache_manifest.json"
    legacy_requests = (
        cfg["project_root"]
        / "output"
        / cfg["mode"]
        / "intermediate"
        / "snapshot_state_requests.parquet"
    )
    report = {
        "legacy_candidate_reused": False,
        "legacy_flow_reused": False,
        "legacy_reuse_reason": "LEGACY_CACHE_NOT_AVAILABLE",
        "raw_column_cache_compatible": False,
    }
    if not manifest_path.exists():
        return None, report
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inputs = manifest.get("cache_inputs", {})
    requested_dates = set(
        pd.concat(
            [
                pd.to_datetime(requests["request_start"], utc=True).dt.strftime("%Y-%m-%d"),
                pd.to_datetime(requests["request_end"], utc=True).dt.strftime("%Y-%m-%d"),
            ]
        ).dropna()
    )
    cached_dates = set(inputs.get("request_dates", []))
    same_flow = (
        float(inputs.get("flow_lookback_minutes", -1))
        == float(cfg["flow"]["lookback_minutes"])
        and float(inputs.get("flow_radius_km", -1))
        == float(cfg["flow"]["airport_radius_km"])
        and inputs.get("dedup_key") == cfg["flow"]["dedup_key"]
    )
    flow_ok = requested_dates.issubset(cached_dates) and same_flow and (root / "flow_states").exists()
    candidate_ok = False
    if legacy_requests.exists():
        legacy = pd.read_parquet(
            legacy_requests, columns=["icao24", "request_start", "request_end"]
        )
        candidate_ok = _contained(
            _merged_intervals(requests), _merged_intervals(legacy)
        ) and (root / "candidate_states").exists() and _candidate_cache_has_v2_columns(root)
    report.update(
        legacy_candidate_reused=candidate_ok,
        legacy_flow_reused=flow_ok,
        legacy_reuse_reason=(
            "FULL_INTERVAL_CONTAINMENT"
            if candidate_ok
            else "LEGACY_CACHE_MISSING_V2_RAW_COLUMNS_OR_INTERVAL_COVERAGE"
        ),
        raw_column_cache_compatible=_candidate_cache_has_v2_columns(root),
    )
    if not candidate_ok:
        return None, report
    return StateStore(root / "candidate_states", root / "flow_states", pd.DataFrame()), report


def prepare_state_cache(
    cfg: dict[str, Any],
    requests: pd.DataFrame,
    airports: pd.DataFrame,
    coverage: pd.DataFrame,
) -> tuple[StateStore, pd.DataFrame, dict[str, Any]]:
    state_requests = requests[requests["source"].eq("state")].copy()
    legacy_store, reuse = _legacy_cache(cfg, state_requests)
    hashes = observation_request_hashes(requests)
    if legacy_store is not None:
        store = StateStore(
            legacy_store.candidate_root, legacy_store.flow_root, coverage
        )
        manifest = {
            **hashes,
            **reuse,
            "cache_status": "LEGACY_FULL_REUSE",
            "cache_root": str(legacy_store.candidate_root.parent),
        }
        return store, pd.DataFrame(), manifest
    base_root = cfg["project_root"] / "cache" / "state_extract_core_v2"
    key = _cache_key(cfg, state_requests, airports)
    variant = base_root.parent / f"{base_root.name}-{key[:12]}"
    cache_root = variant if (variant / "cache_manifest.json").exists() else base_root
    store, extraction, base_manifest = extract_state_data(
        cfg, state_requests, airports, coverage, cache_root
    )
    if reuse["legacy_flow_reused"]:
        legacy_root = cfg["project_root"] / "cache" / "state_extract_v2"
        store = StateStore(store.candidate_root, legacy_root / "flow_states", coverage)
    manifest = {
        **hashes,
        **reuse,
        "cache_status": (
            "CORE_HIT"
            if not extraction.empty and extraction["cache_status"].eq("HIT").all()
            else "CORE_MISS_OR_PARTIAL"
        ),
        "cache_root": str(store.candidate_root.parent),
        "source_hash": object_hash(cfg.get("raw_hashes", {})),
        "extraction_code_hash": sha256_file(
            Path(__file__).resolve().parents[1] / "state.py"
        ),
        "base_cache_key": base_manifest.get("cache_key"),
    }
    return store, extraction, manifest
