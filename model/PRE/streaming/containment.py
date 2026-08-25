from __future__ import annotations

import json
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import psutil

from model.PRE.cohort import split_for_date
from model.PRE.episode.containment import (
    episode_containment_from_rows,
    episode_node_count,
)
from model.common.identity import content_id
from model.PRE.streaming.data2 import (
    aircraft_tail,
    lightweight_flights,
    load_timezones,
    ontime_paths,
)


def audit_v5_split_containment(root: Path) -> dict:
    """Audit every possible V5 split boundary without reconstructing interior pools."""
    started = time.perf_counter()
    process = psutil.Process()
    months = (6, 7, 8, 9)
    paths = ontime_paths(root, months=months)
    if any(path.parent.name in {"month=10", "month=11", "month=12"} for path in paths):
        raise RuntimeError("FINAL_TEST_SOURCE_PATH_SELECTED")
    if (
        split_for_date(date(2019, 6, 30)) != "train"
        or split_for_date(date(2019, 7, 1)) != "calibration"
        or split_for_date(date(2019, 8, 1)) != "development"
        or split_for_date(date(2019, 10, 1)) != "test"
    ):
        raise RuntimeError("V5_SPLIT_CONTRACT_MISMATCH")
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    cache_root = root / "artifacts" / "diagnostics" / "v5_development_freeze"
    cache_manifest = json.loads(
        (cache_root / "M1_BASE_CACHE_MANIFEST.json").read_text(encoding="utf-8")
    )
    pool_before = Counter(cache_manifest["audit"]["pool_sizes"])
    cross_by_pool = Counter()
    removed_nodes_by_pool = Counter()
    removed_insufficient_history_by_pool = Counter()
    transition_counts = Counter()
    cross_examples: dict[str, list[dict]] = {}
    selected_ids = _historical_selected_ids(root)
    selected_cross: dict[str, dict] = {}
    previous_rows: tuple[dict, ...] = ()
    source_rows = source_rows_skipped = episodes = boundary_candidates = 0
    same_split_cross_month_allowed = 0
    last_heartbeat = started

    def heartbeat(phase: str, *, rows: int | None = None, **_) -> None:
        nonlocal last_heartbeat
        print(
            json.dumps(
                {
                    "PHASE": phase,
                    "ROWS": source_rows if rows is None else rows,
                    "EPISODES": episodes,
                    "BOUNDARY_CANDIDATES": boundary_candidates,
                    "CROSS_SPLIT_FOUND": sum(cross_by_pool.values()),
                    "RSS_MB": round(process.memory_info().rss / 1024**2, 3),
                    "ELAPSED_SECONDS": round(time.perf_counter() - started, 3),
                    "FINAL_TEST_ACCESS_COUNT": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        last_heartbeat = time.perf_counter()

    for month, path in zip(months, paths):
        rows_before = source_rows
        current_rows, skipped = lightweight_flights(
            path,
            zones,
            heartbeat=lambda phase, **info: heartbeat(
                phase,
                rows=rows_before + int(info.get("rows", 0)),
            ),
        )
        source_rows += len(current_rows) + skipped
        source_rows_skipped += skipped
        chunk = list(previous_rows) + current_rows
        month_key = f"2019-{month:02d}"
        for predecessor, successor in _iter_data2_episode_pairs(chunk):
            service_date = successor.get("service_date", "")
            if service_date[:7] != month_key:
                continue
            episodes += 1
            predecessor_split = _fast_split(predecessor["service_date"])
            successor_split = _fast_split(successor["service_date"])
            start_split = _fast_split(predecessor["event_end_time"])
            end_split = _fast_split(successor["event_start_time"])
            support = {predecessor_split, successor_split, start_split, end_split}
            cross_month = predecessor["service_date"][:7] != service_date[:7]
            if len(support) == 1 and not cross_month:
                if time.perf_counter() - last_heartbeat >= 45:
                    heartbeat("BOUNDARY_EPISODE_SCAN")
                continue
            boundary_candidates += 1
            episode = _episode_namespace(predecessor, successor)
            containment = episode_containment_from_rows(
                episode,
                {
                    predecessor["flight_id"]: predecessor,
                    successor["flight_id"]: successor,
                },
            )
            if containment.split == "test":
                raise RuntimeError("FINAL_TEST_EPISODE_MATERIALIZED")
            if not containment.allowed:
                cross_by_pool[successor_split] += 1
                removed_nodes = episode_node_count(
                    episode_start_time=episode.episode_start_time,
                    episode_end_time=episode.episode_end_time,
                )
                removed_nodes_by_pool[successor_split] += removed_nodes
                if removed_nodes < 2:
                    removed_insufficient_history_by_pool[successor_split] += 1
                transition_counts.update(containment.transitions)
                examples = cross_examples.setdefault(successor_split, [])
                record = {
                    "episode_id": episode.episode_id,
                    "predecessor_service_date": predecessor.get("service_date"),
                    "successor_service_date": successor.get("service_date"),
                    "episode_start_time": episode.episode_start_time.isoformat(),
                    "episode_end_time": episode.episode_end_time.isoformat(),
                    "transitions": list(containment.transitions),
                    "removed_nodes": removed_nodes,
                }
                if len(examples) < 20:
                    examples.append(record)
                historical_split = selected_ids.get(episode.episode_id)
                if historical_split is not None:
                    cohort_size = sum(
                        value == historical_split for value in selected_ids.values()
                    )
                    selected_cross[episode.episode_id] = {
                        **record,
                        "historical_split": historical_split,
                        "episode_normalized_weight": 1.0,
                        "per_node_weight": 1.0 / removed_nodes,
                        "split_evaluation_weight": 1.0 / cohort_size,
                    }
            elif (
                predecessor["service_date"][:7] == "2019-08"
                and service_date[:7] == "2019-09"
            ):
                same_split_cross_month_allowed += 1
            if time.perf_counter() - last_heartbeat >= 45:
                heartbeat("BOUNDARY_EPISODE_SCAN")
        previous_rows = aircraft_tail(current_rows)
        heartbeat("BOUNDARY_MONTH_COMPLETE")
    pool_after = Counter(pool_before)
    pool_after.subtract(cross_by_pool)
    return {
        "schema_version": "AIR_SLOT_V5_SPLIT_CONTAINMENT_AUDIT_V2",
        "audit_method": "BOUNDARY_COMPLETE_INTERVAL_CONTAINMENT_O1",
        "audit_scope_basis": "MAX_CHAIN_GAP_360_MINUTES_AND_CONTIGUOUS_V5_SPLITS",
        "source_months_read": [f"2019-{month:02d}" for month in months],
        "final_test_access_count": 0,
        "source_rows": source_rows,
        "source_rows_skipped": source_rows_skipped,
        "pool_before": dict(pool_before),
        "pool_after": dict(pool_after),
        "cross_split_by_pool": dict(cross_by_pool),
        "removed_nodes_by_pool": dict(removed_nodes_by_pool),
        "removed_insufficient_history_by_pool": dict(
            removed_insufficient_history_by_pool
        ),
        "cross_split_total": sum(cross_by_pool.values()),
        "cross_split_transitions": dict(transition_counts),
        "cross_split_examples": cross_examples,
        "same_split_august_to_september_allowed": same_split_cross_month_allowed,
        "TRAIN_CROSS_SPLIT_EPISODES": cross_by_pool["train"],
        "CALIBRATION_CROSS_SPLIT_EPISODES": cross_by_pool["calibration"],
        "DEVELOPMENT_CROSS_SPLIT_EPISODES": cross_by_pool["development"],
        "TRAIN_TO_CALIBRATION": transition_counts["TRAIN_TO_CALIBRATION"],
        "CALIBRATION_TO_DEVELOPMENT": transition_counts["CALIBRATION_TO_DEVELOPMENT"],
        "DEVELOPMENT_TO_FINAL_TEST": transition_counts["DEVELOPMENT_TO_FINAL_TEST"],
        "historical_selected_episode_count": len(selected_ids),
        "historical_cross_split_episode_count": len(selected_cross),
        "historical_cross_split_episodes": selected_cross,
        "historical_h_selection_episodes_total": len(selected_ids),
        "historical_w_selection_episodes_total": len(selected_ids),
        "historical_h_selection_cross_split_episodes": len(selected_cross),
        "historical_w_selection_cross_split_episodes": len(selected_cross),
        "elapsed_seconds": time.perf_counter() - started,
        "historical_provenance": {
            "cache_manifest": "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE_MANIFEST.json",
            "cache_arrays": "artifacts/diagnostics/v5_development_freeze/M1_BASE_CACHE.npz",
            "h_evidence": "artifacts/diagnostics/v5_development_freeze/m1_hstar_evidence.json",
            "w_evidence": "artifacts/diagnostics/v5_development_freeze/m1_wstar_evidence.json",
        },
    }


def _iter_data2_episode_pairs(rows: list[dict]):
    """Yield PRE chain pairs without retaining millions of Pydantic objects."""
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault(
            (
                row["dataset_instance_id"],
                row["aircraft_id_namespace"],
                row["aircraft_id"],
            ),
            [],
        ).append(row)
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda row: (
                row["actual_departure_utc"],
                row["actual_arrival_utc"],
                row["flight_id"],
            ),
        )
        for predecessor, successor in zip(ordered, ordered[1:]):
            if predecessor["destination_airport_id"] != successor["origin_airport_id"]:
                continue
            if predecessor["actual_arrival_utc"] >= successor["actual_departure_utc"]:
                continue
            gap = (
                successor["actual_departure_utc"] - predecessor["actual_arrival_utc"]
            ).total_seconds() / 60
            if gap > 360:
                continue
            if predecessor["event_end_time"] >= successor["event_start_time"]:
                continue
            yield predecessor, successor


def _episode_namespace(predecessor: dict, successor: dict):
    payload = {
        "dataset": predecessor["dataset_instance_id"],
        "predecessor": predecessor["flight_id"],
        "successor": successor["flight_id"],
        "rule": "DATA2_SAME_AIRCRAFT_AIRPORT_GAP_360",
    }
    return SimpleNamespace(
        episode_id=content_id(payload),
        predecessor_flight_id=predecessor["flight_id"],
        successor_flight_id=successor["flight_id"],
        episode_start_time=predecessor["event_end_time"],
        episode_end_time=successor["event_start_time"],
    )


def _fast_split(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if value <= date(2019, 6, 30):
        return "train"
    if value <= date(2019, 7, 31):
        return "calibration"
    if value <= date(2019, 9, 30):
        return "development"
    return "test"


def _historical_selected_ids(root: Path) -> dict[str, str]:
    path = (
        root
        / "artifacts"
        / "diagnostics"
        / "v5_development_freeze"
        / "M1_BASE_CACHE.npz"
    )
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as arrays:
        episode_ids = arrays["episode_ids"].astype(str)
        split_by_episode: dict[str, str] = {}
        for episode_id, split in zip(
            arrays["sample_episode_ids"].astype(str),
            arrays["sample_splits"].astype(str),
        ):
            split_by_episode.setdefault(episode_id, split)
        return {
            episode_id: split_by_episode.get(episode_id, "unknown")
            for episode_id in episode_ids
        }
