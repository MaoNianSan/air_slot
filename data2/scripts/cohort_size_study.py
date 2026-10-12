# -*- coding: utf-8 -*-
"""Cohort-size stability study (M5 Phase C/D) - DEVELOPMENT ONLY.

    python data2/scripts/cohort_size_study.py --collect --years 2019
    python data2/scripts/cohort_size_study.py --materialize --years 2019 --n 128 256 512 1024 2048 4096

Protocol (user-approved M5 hard corrections):
- sampling rank = SHA256(FIXED_M5_SEED || episode_id), identical contract for
  every year (no year-derived seeds);
- size vector: TRAIN=N, CALIBRATION=N/2, DEVELOPMENT=N (final test is NOT
  touched in this study);
- nested cohorts: the top-N by rank is a prefix of top-2N (bounded heaps at
  N_MAX=4096 cover the whole grid by prefixes);
- eligibility = the production chain semantics (same builder, same
  containment, split via DATA2_TEMPORAL_SPLIT@2.0.0, test excluded);
- the eligible pool is NOT retained by any PRE_MULTIYEAR_V1 artifact
  (Phase B audit), so the single sanctioned pass re-walks the lightweight
  projection + chain enumeration over ontime months 1-9 - it does NOT
  re-execute reference fits, stream manifests, or any materialization;
- stability metrics in this phase are development-only (no Oct-Dec reads).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from model.PRE.cohort import split_for_date_multiyear
from model.PRE.development import materialize_preselected_cohorts
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.episode.containment import (
    episode_containment_from_rows,
    episode_node_count,
)
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)
from model.PRE.streaming.data2 import (
    aircraft_tail,
    lightweight_flights,
    load_timezones,
    ontime_paths,
)

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
RAW = DATA2 / "raw"
OUT_ROOT = DATA2 / "reports" / "cohort_size_stability"
PRE_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
INSTANCE_ID = "data2_2017_2022"
FIXED_M5_SEED = "M5-COHORT-SEED-20260928"   # identical for every year
N_GRID = (128, 256, 512, 1024, 2048, 4096)
N_MAX = 4096
MAX_GAP_MINUTES = 360


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_rank(episode_id: str) -> str:
    return hashlib.sha256(
        (FIXED_M5_SEED + "||" + episode_id).encode("utf-8")).hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


def load_year_references(year: int):
    """Load the per-year train-frozen taxi/turnaround references, re-bound to
    the multi-year instance, and normalized with the M5 metadata fields."""
    root = PRE_ROOT / str(year)
    payloads = {}
    for kind, loader in (("taxi", data2_taxi_reference_from_payload),
                         ("turnaround", data2_turnaround_reference_from_payload)):
        payload = json.loads(
            (root / f"DATA2_{kind.upper()}_REFERENCE_TRAIN_FROZEN.json")
            .read_text(encoding="utf-8"))
        payload["dataset_instance_id"] = INSTANCE_ID          # M5 re-bind
        payload["experiment_year"] = year                      # correction 8
        payload["fit_start"] = f"{year}-01-01"
        payload["fit_end"] = f"{year}-06-30"
        payload["reference_contract_id"] = (
            f"YEAR_SPECIFIC_H1_{kind.upper()}_V1")
        payloads[kind] = loader(payload)
    return payloads


# ------------------------------------------------------- pool collection --

def collect_hash_ranked_pool(year: int, out: Path) -> dict:
    """One sanctioned scan (lightweight projection + chain enumeration, months
    1-9); maintains per-split top-N_MAX EpisodeRecords by hash rank."""
    log(f"{year} collect: hash-ranked eligible pool (months 1-9, N_MAX={N_MAX})")
    started = time.perf_counter()
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")
    paths = ontime_paths(REPO, range(1, 10), year=year)
    if len(paths) != 9:
        raise RuntimeError(f"MISSING_MONTHS:{year}:{len(paths)}")
    heaps: dict[str, list] = {"train": [], "calibration": [], "development": []}
    pool_counts: Counter = Counter()
    previous_rows: tuple = ()
    for month, path in enumerate(paths, start=1):
        month_started = time.perf_counter()
        current_rows, _skipped = lightweight_flights(
            path, zones, dataset_instance_id=INSTANCE_ID)
        chunk = list(previous_rows) + current_rows
        by_id = {row["flight_id"]: row for row in chunk}
        month_key = f"{year}-{month:02d}"
        month_episodes = 0
        for episode in build_data2_episode_records(chunk):
            service_date = by_id[episode.successor_flight_id].get(
                "service_date", "")
            if not service_date or service_date[:7] != month_key:
                continue
            split = split_for_date_multiyear(
                date.fromisoformat(service_date))
            if split == "test":
                continue   # final test is never read in this study
            containment = episode_containment_from_rows(
                episode, by_id, split_resolver=split_for_date_multiyear)
            if not containment.allowed:
                continue
            pool_counts[split] += 1
            month_episodes += 1
            rank = hash_rank(episode.episode_id)
            heap = heaps[split]
            if len(heap) < N_MAX:
                heap.append((rank, episode))
                heap.sort(key=lambda item: item[0])
            elif rank < heap[-1][0]:
                heap[-1] = (rank, episode)
                heap.sort(key=lambda item: item[0])
        previous_rows = aircraft_tail(current_rows)
        del current_rows, chunk, by_id
        log(f"  {year}-{month:02d}: month_episodes={month_episodes} "
            f"({time.perf_counter() - month_started:.0f}s)")
    selected = {split: [episode for _rank, episode in heap]
                for split, heap in heaps.items()}
    records_path = out / "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl"
    with records_path.open("w", encoding="utf-8") as fh:
        for split in ("train", "calibration", "development"):
            for rank, episode in heaps[split]:
                fh.write(json.dumps({
                    "split": split, "rank": rank,
                    "episode": episode.model_dump(mode="json")},
                    sort_keys=True) + "\n")
                fh.flush()
    result = {
        "stage": "HASH_RANKED_POOL", "year": year,
        "seed_contract": f"SHA256({FIXED_M5_SEED} || episode_id)",
        "N_MAX": N_MAX, "pool_counts": dict(pool_counts),
        "selected_counts": {k: len(v) for k, v in selected.items()},
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "HASH_RANKED_POOL_SUMMARY.json", result)
    log(f"{year} collect done: pool={dict(pool_counts)} "
        f"({result['seconds']}s)")
    return result


def load_selected_cohort(year: int) -> dict[str, list]:
    records: dict[str, list] = {"train": [], "calibration": [],
                                "development": []}
    path = (OUT_ROOT / str(year) /
            "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl")
    from model.PRE.contracts.pre_state import EpisodeRecord
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            records[row["split"]].append(
                (row["rank"], EpisodeRecord.model_validate(row["episode"])))
    for split in records:
        records[split].sort(key=lambda item: item[0])
    return records


# ------------------------------------------------------ materialize per N --

def materialize_for_n(year: int, n: int, scientific,
                      selected: dict[str, list]) -> dict:
    started = time.perf_counter()
    counts = {"train": n, "calibration": n // 2, "development": n}
    partitions = {
        split: tuple(episode for _rank, episode in selected[split][:count])
        for split, count in counts.items()}
    refs = load_year_references(year)
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=REPO,
        partitions=partitions,
        year=year,
        dataset_instance_id=INSTANCE_ID,
        split_resolver=split_for_date_multiyear,
        taxi_reference=refs["taxi"],
        turnaround_reference=refs["turnaround"],
    )
    states = [state for item in cohorts.development for state in item.states]
    nodes = [node for item in cohorts.development for node in item.nodes]
    out = OUT_ROOT / str(year) / f"N{n}"
    states_path = out / "PRE_DEVELOPMENT_STATES.jsonl"
    states_path.parent.mkdir(parents=True, exist_ok=True)
    with states_path.open("w", encoding="utf-8") as fh:
        for state in states:
            fh.write(json.dumps(state.model_dump(mode="json"),
                                sort_keys=True) + "\n")
    weather = cohorts.audit.get("weather", {})
    result = {
        "year": year, "n": n,
        "size_vector": {"TRAIN": counts["train"],
                        "CALIBRATION": counts["calibration"],
                        "DEVELOPMENT": counts["development"]},
        "materialized_episodes": len(cohorts.development),
        "development_nodes": len(nodes),
        "prestates": len(states),
        "weather_audit": weather,
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "MATERIALIZE_SUMMARY.json", result)
    log(f"{year} N={n}: episodes={len(cohorts.development)} "
        f"nodes={len(nodes)} states={len(states)} "
        f"({result['seconds']}s)")
    return result


# ------------------------------------------------------------------- main --

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=[2019])
    parser.add_argument("--collect", action="store_true",
                        help="run the sanctioned pool-collection scan")
    parser.add_argument("--materialize", action="store_true",
                        help="materialize the N grid from the selected cohort")
    parser.add_argument("--n", type=int, nargs="*", default=list(N_GRID))
    args = parser.parse_args()

    scientific = None
    if args.materialize:
        from model.common.config import load_config_layers
        scientific = load_config_layers(REPO / "configs").scientific

    for year in args.years:
        out = OUT_ROOT / str(year)
        out.mkdir(parents=True, exist_ok=True)
        if args.collect:
            collect_hash_ranked_pool(year, out)
        if args.materialize:
            selected = load_selected_cohort(year)
            for n in args.n:
                if n > N_MAX:
                    continue
                summary_path = out / f"N{n}" / "MATERIALIZE_SUMMARY.json"
                if summary_path.is_file():
                    log(f"{year} N={n}: cached")
                    continue
                materialize_for_n(year, n, scientific, selected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
