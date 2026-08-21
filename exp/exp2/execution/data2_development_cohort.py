"""Deterministic, Development-only Data2 pilot cohort materialization."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from typing import Iterable

from model.common.identity import content_id
from model.PRE.development import (
    build_development_episode_nodes,
    eligible_development_episodes_from_rows,
)
from model.PRE.streaming.data2 import (
    iter_lightweight_flights,
    load_timezones,
)


DEVELOPMENT_START = date(2019, 8, 1)
DEVELOPMENT_END = date(2019, 9, 30)
DEVELOPMENT_MONTHS = (8, 9)
PILOT_EPISODE_COUNT = 5
PILOT_SELECTOR_SEED = 20260813
COHORT_SCHEMA_VERSION = "AIR_SLOT_EXP2_DATA2_DEVELOPMENT_PILOT_COHORT_V1"
COHORT_FILENAME = "DATA2_DEVELOPMENT_PILOT_COHORT.json"


def development_ontime_paths(root: Path) -> tuple[Path, ...]:
    """Return exactly the two permitted Development source files."""
    paths = tuple(_single_development_source(root, month) for month in DEVELOPMENT_MONTHS)
    _assert_development_paths(paths)
    return paths


def _single_development_source(root: Path, month: int) -> Path:
    directory = root / "data2" / "raw" / "bts" / "ontime" / "2019" / f"month={month:02d}"
    sources = tuple(sorted(directory.glob("*.csv")))
    if len(sources) != 1:
        raise RuntimeError("EXP2_DEVELOPMENT_COHORT_SOURCE_SCOPE_VIOLATION")
    return sources[0]


def _assert_development_paths(paths: Iterable[Path]) -> None:
    values = tuple(Path(path) for path in paths)
    if any(path.parent.name in {"month=10", "month=11", "month=12"} for path in values):
        raise RuntimeError("FINAL_TEST_SOURCE_PATH_SELECTED")
    expected = {f"month={month:02d}" for month in DEVELOPMENT_MONTHS}
    actual = {path.parent.name for path in values}
    if actual != expected or len(values) != len(DEVELOPMENT_MONTHS):
        raise RuntimeError("EXP2_DEVELOPMENT_COHORT_SOURCE_SCOPE_VIOLATION")


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _source_hashes(root: Path, paths: tuple[Path, ...]) -> dict[str, str]:
    return {str(path.relative_to(root)): _file_hash(path) for path in paths}


def _write_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current == payload:
            return
        raise RuntimeError("EXP2_DEVELOPMENT_COHORT_ARTIFACT_EXISTS_WITH_DIFFERENT_CONTENT")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    os.replace(temporary, path)


def _create_stage(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE flights (
            dataset_instance_id TEXT NOT NULL,
            aircraft_id_namespace TEXT NOT NULL,
            aircraft_id TEXT NOT NULL,
            flight_id TEXT NOT NULL,
            origin_airport_id TEXT NOT NULL,
            destination_airport_id TEXT NOT NULL,
            event_start_time TEXT NOT NULL,
            event_end_time TEXT NOT NULL,
            actual_arrival_utc TEXT NOT NULL,
            actual_departure_utc TEXT NOT NULL,
            service_date TEXT NOT NULL
        )
        """
    )


def _insert_development_rows(
    connection: sqlite3.Connection,
    paths: tuple[Path, ...],
    zones: dict[str, str],
) -> tuple[int, int]:
    source_rows = skipped_rows = 0
    batch: list[tuple[str, ...]] = []
    for path in paths:
        generator = iter_lightweight_flights(path, zones)
        while True:
            try:
                row = next(generator)
            except StopIteration as stop:
                skipped_rows += int((stop.value or {}).get("skipped_rows", 0))
                break
            source_rows += 1
            batch.append(
                (
                    row["dataset_instance_id"],
                    row["aircraft_id_namespace"],
                    row["aircraft_id"],
                    row["flight_id"],
                    row["origin_airport_id"],
                    row["destination_airport_id"],
                    row["event_start_time"].isoformat(),
                    row["event_end_time"].isoformat(),
                    row["actual_arrival_utc"].isoformat(),
                    row["actual_departure_utc"].isoformat(),
                    row["service_date"],
                )
            )
            if len(batch) >= 10_000:
                connection.executemany(
                    "INSERT INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
                )
                connection.commit()
                batch.clear()
    if batch:
        connection.executemany(
            "INSERT INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch
        )
        connection.commit()
    connection.execute(
        """
        CREATE INDEX ordered_flights ON flights (
            dataset_instance_id, aircraft_id_namespace, aircraft_id,
            actual_departure_utc, actual_arrival_utc, flight_id
        )
        """
    )
    return source_rows, skipped_rows


def _row_from_stage(values: tuple[str, ...]) -> dict:
    return {
        "dataset_instance_id": values[0],
        "aircraft_id_namespace": values[1],
        "aircraft_id": values[2],
        "flight_id": values[3],
        "origin_airport_id": values[4],
        "destination_airport_id": values[5],
        "event_start_time": datetime.fromisoformat(values[6]),
        "event_end_time": datetime.fromisoformat(values[7]),
        "actual_arrival_utc": datetime.fromisoformat(values[8]),
        "actual_departure_utc": datetime.fromisoformat(values[9]),
        "service_date": values[10],
    }


def select_deterministic_pilot(
    candidates: Iterable[tuple[object, dict[str, dict]]],
    *,
    episode_count: int,
) -> tuple[object, ...]:
    """Keep the first N eligible stable episode identities without outcomes or scores."""
    selected: dict[str, object] = {}
    for episode, _ in candidates:
        episode_id = episode.episode_id
        if len(selected) < episode_count:
            selected[episode_id] = episode
            continue
        greatest = max(selected)
        if episode_id < greatest:
            del selected[greatest]
            selected[episode_id] = episode
    return tuple(selected[item] for item in sorted(selected))


def _eligible_episodes(connection: sqlite3.Connection):
    cursor = connection.execute(
        """
        SELECT dataset_instance_id, aircraft_id_namespace, aircraft_id, flight_id,
               origin_airport_id, destination_airport_id, event_start_time,
               event_end_time, actual_arrival_utc, actual_departure_utc, service_date
        FROM flights
        ORDER BY dataset_instance_id, aircraft_id_namespace, aircraft_id,
                 actual_departure_utc, actual_arrival_utc, flight_id
        """
    )
    current_key: tuple[str, str, str] | None = None
    group: list[dict] = []
    for values in cursor:
        row = _row_from_stage(values)
        key = (row["dataset_instance_id"], row["aircraft_id_namespace"], row["aircraft_id"])
        if current_key is not None and key != current_key:
            yield from eligible_development_episodes_from_rows(group)
            group.clear()
        current_key = key
        group.append(row)
    if group:
        yield from eligible_development_episodes_from_rows(group)


def materialize_development_pilot_cohort(
    *,
    root: Path,
    output_path: Path | None = None,
    episode_count: int = PILOT_EPISODE_COUNT,
    selector_seed: int = PILOT_SELECTOR_SEED,
) -> dict:
    """Freeze a real, non-outcome-selected Development pilot cohort and nodes."""
    if episode_count < 1:
        raise ValueError("EXP2_DEVELOPMENT_PILOT_EPISODE_COUNT_REQUIRED")
    paths = development_ontime_paths(root)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    source_hashes = _source_hashes(root, paths)

    temporary_root = root / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="exp2-data2-development-", dir=temporary_root) as directory:
        database = Path(directory) / "cohort.sqlite"
        connection = sqlite3.connect(database)
        try:
            _create_stage(connection)
            source_rows, skipped_rows = _insert_development_rows(connection, paths, zones)
            candidates = _eligible_episodes(connection)
            selected = select_deterministic_pilot(candidates, episode_count=episode_count)
        finally:
            connection.close()

    if len(selected) != episode_count:
        raise RuntimeError("EXP2_DEVELOPMENT_PILOT_INSUFFICIENT_ELIGIBLE_EPISODES")
    nodes, config_hash, registry_hash = build_development_episode_nodes(
        root, selected, paths, zones,
    )
    if not nodes:
        raise RuntimeError("EXP2_DEVELOPMENT_PILOT_NO_DECISION_NODES")

    source_manifest_hash = content_id(source_hashes)
    episode_ids = tuple(item.episode_id for item in selected)
    node_ids = tuple(item.decision_node_id for item in nodes)
    identity = {
        "dataset_id": "DATA2",
        "source_dataset_id": "data2_2019",
        "source_manifest_hash": source_manifest_hash,
        "split": "DEVELOPMENT",
        "selector_rule": "FIRST_N_ELIGIBLE_BY_STABLE_EPISODE_ID",
        "selector_seed": selector_seed,
        "selector_seed_role": "DECLARED_NOT_USED_BY_FIRST_N_SELECTOR",
        "episode_ids": episode_ids,
        "node_ids": node_ids,
        "config_hash": config_hash,
        "registry_hash": registry_hash,
    }
    cohort_hash = content_id(identity)
    payload = {
        "schema_version": COHORT_SCHEMA_VERSION,
        "status": "FROZEN_DEVELOPMENT_PILOT_COHORT",
        "dataset_id": "DATA2",
        "source_dataset_id": "data2_2019",
        "dataset_version": "DATA2_2019_DEVELOPMENT_AUG_SEP_V1",
        "split": "DEVELOPMENT",
        "successor_service_date_range": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "source_files": source_hashes,
        "source_manifest_hash": source_manifest_hash,
        "source_rows_after_lightweight_eligibility": source_rows,
        "source_rows_skipped": skipped_rows,
        "selector_rule": "FIRST_N_ELIGIBLE_BY_STABLE_EPISODE_ID",
        "selector_seed": selector_seed,
        "selector_seed_role": "DECLARED_NOT_USED_BY_FIRST_N_SELECTOR",
        "selector_pre_outcome": True,
        "selector_disallows_variant_or_outcome_selection": True,
        "split_containment_rule": "V5_FULL_EPISODE_SUPPORT_V1",
        "rolling_interval_minutes": 5,
        "cohort_scope": "DATA2_EPISODE_IDENTITY_AND_ROLLING_NODE_GRID_ONLY",
        "factual_replay_status": "DATA2_FACTUAL_REPLAY_AVAILABILITY_DECISION_REQUIRED",
        "episode_ids": episode_ids,
        "episode_ids_hash": content_id(episode_ids),
        "episode_records": tuple(item.model_dump(mode="json") for item in selected),
        "node_ids": node_ids,
        "node_ids_hash": content_id(node_ids),
        "decision_nodes": tuple(item.model_dump(mode="json") for item in nodes),
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "config_hash": config_hash,
        "registry_hash": registry_hash,
        "cohort_hash": cohort_hash,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    payload["artifact_hash"] = content_id(payload)
    target = output_path or root / "artifacts" / "experiment" / "exp2" / COHORT_FILENAME
    _write_json(target, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=PILOT_EPISODE_COUNT)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    payload = materialize_development_pilot_cohort(root=root, episode_count=args.episodes)
    print(json.dumps({
        "status": payload["status"],
        "cohort_hash": payload["cohort_hash"],
        "episode_count": len(payload["episode_ids"]),
        "node_count": len(payload["node_ids"]),
        "final_test_access_count": payload["FINAL_TEST_ACCESS_COUNT"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
