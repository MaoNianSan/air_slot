"""Outcome-blind deterministic selection of Q4-contained S34 episodes.

This module is an isolated extension entry point. It intentionally does not
change or call the Development-only reservoir/materializer.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any

from data2.scripts.cohort_size_study import FIXED_M5_SEED
from model.PRE.cohort import split_for_date_multiyear
from model.PRE.episode.containment import episode_containment_from_rows
from model.PRE.streaming.data2 import (
    aircraft_tail,
    build_data2_episode_records,
    lightweight_flights,
    load_timezones,
)


INSTANCE_ID = "data2_2017_2022"
MONTHS_WITH_CONTEXT = (9, 10, 11, 12)
Q4_MONTHS = (10, 11, 12)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def q4_rank(episode_id: str) -> str:
    return hashlib.sha256(
        (FIXED_M5_SEED + "||" + episode_id).encode("utf-8")
    ).hexdigest()


def _monthly_paths(root: Path, year: int) -> tuple[Path, ...]:
    paths: list[Path] = []
    for month in MONTHS_WITH_CONTEXT:
        partition = (
            root / "data2" / "raw" / "bts" / "ontime" / str(year)
            / f"month={month:02d}"
        )
        candidates = tuple(sorted(partition.glob("*.csv")))
        if len(candidates) != 1:
            raise RuntimeError(
                f"Q4_MONTH_SOURCE_CARDINALITY:{year}-{month:02d}:{len(candidates)}"
            )
        paths.append(candidates[0])
    return tuple(paths)


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def select_q4_cohort(
    *, root: Path, year: int, output_dir: Path, n: int = 4096
) -> dict[str, Any]:
    """Select and freeze the SHA-ranked Q4 cohort before state/model evaluation.

    September is parsed only as aircraft-rotation context for October. An
    episode is eligible only if the existing multiyear resolver and full
    episode-containment function assign every support date/time to `test`.
    """

    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    year = int(year)
    n = int(n)
    if year not in range(2017, 2023):
        raise ValueError(f"Q4_YEAR_OUT_OF_SCOPE:{year}")
    if n != 4096:
        raise ValueError(f"Q4_COHORT_SIZE_FROZEN:{n}")
    paths = _monthly_paths(root, year)
    zones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    previous_rows: tuple[dict, ...] = ()
    eligible: dict[str, Any] = {}
    skipped_rows: dict[str, int] = {}
    parsed_rows: dict[str, int] = {}

    for path in paths:
        month = int(path.parent.name.split("=", 1)[1])
        rows, skipped = lightweight_flights(
            path, zones, dataset_instance_id=INSTANCE_ID
        )
        skipped_rows[f"{year}-{month:02d}"] = skipped
        parsed_rows[f"{year}-{month:02d}"] = len(rows)
        by_id = {row["flight_id"]: row for row in (*previous_rows, *rows)}
        month_key = f"{year}-{month:02d}"
        for episode in sorted(
            build_data2_episode_records((*previous_rows, *rows)),
            key=lambda item: item.episode_id,
        ):
            successor = by_id.get(episode.successor_flight_id)
            service_date = None if successor is None else successor.get("service_date")
            if not service_date or service_date[:7] != month_key:
                continue
            if month not in Q4_MONTHS:
                continue
            containment = episode_containment_from_rows(
                episode, by_id, split_resolver=split_for_date_multiyear
            )
            if containment.allowed and containment.split == "test":
                eligible.setdefault(episode.episode_id, episode)
        previous_rows = aircraft_tail(rows)

    ranked = sorted(
        ((q4_rank(episode_id), episode_id, episode)
         for episode_id, episode in eligible.items()),
        key=lambda item: (item[0], item[1]),
    )
    if len(ranked) < n:
        q4_rows_read = sum(
            parsed_rows.get(f"{year}-{month:02d}", 0)
            + skipped_rows.get(f"{year}-{month:02d}", 0)
            for month in Q4_MONTHS
        )
        _atomic_json(output_dir / "Q4_COHORT_SHORTFALL.json", {
            "schema_version": "JATM_S34_Q4_COHORT_SHORTFALL_V1",
            "year": year,
            "split": "test",
            "required_n": n,
            "eligible_n": len(ranked),
            "status": "STOP_SHORTFALL",
            "raw_rows_read_by_month": {
                month: parsed_rows[month] + skipped_rows[month]
                for month in parsed_rows
            },
            "q4_raw_rows_read": q4_rows_read,
            "final_test_access_count": q4_rows_read,
        })
        raise RuntimeError(f"Q4_ELIGIBLE_COHORT_SHORTFALL:{year}:{len(ranked)}<{n}")

    selected = ranked[:n]
    ids_path = output_dir / "Q4_SELECTED_COHORT.jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary = ids_path.with_suffix(ids_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for rank, episode_id, episode in selected:
            stream.write(json.dumps({
                "rank": rank,
                "episode_id": episode_id,
                "episode": episode.model_dump(mode="json"),
            }, sort_keys=True, ensure_ascii=False) + "\n")
    temporary.replace(ids_path)
    payload = {
        "schema_version": "JATM_S34_Q4_COHORT_V1",
        "status": "COHORT_FROZEN",
        "year": year,
        "split": "test",
        "service_date_window": {
            "start_inclusive": date(year, 10, 1).isoformat(),
            "end_inclusive": date(year, 12, 31).isoformat(),
        },
        "context_months": [9],
        "eligible_episode_count": len(ranked),
        "selected_episode_count": n,
        "rank_contract": f"SHA256({FIXED_M5_SEED} || episode_id)",
        "tie_break": "episode_id_ascending",
        "selected_ids_sha256": _file_sha256(ids_path),
        "source_hashes": {
            str(path.relative_to(root)).replace("\\", "/"): _file_sha256(path)
            for path in paths
        },
        "weather_and_model_evaluation_started": False,
        "raw_rows_read_by_month": {
            month: parsed_rows[month] + skipped_rows[month]
            for month in parsed_rows
        },
        "parsed_rows_by_month": parsed_rows,
        "skipped_rows_by_month": skipped_rows,
        "q4_raw_rows_read": sum(
            parsed_rows[f"{year}-{month:02d}"] + skipped_rows[f"{year}-{month:02d}"]
            for month in Q4_MONTHS
        ),
        "september_context_rows_read": (
            parsed_rows[f"{year}-09"] + skipped_rows[f"{year}-09"]
        ),
        "final_test_access_count": sum(
            parsed_rows[f"{year}-{month:02d}"] + skipped_rows[f"{year}-{month:02d}"]
            for month in Q4_MONTHS
        ),
        "final_test_access_count_unit": "raw_q4_ontime_source_rows_read",
    }
    _atomic_json(output_dir / "Q4_COHORT_MANIFEST.json", payload)
    return payload

