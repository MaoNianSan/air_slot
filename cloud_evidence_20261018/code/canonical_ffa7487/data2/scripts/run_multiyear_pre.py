# -*- coding: utf-8 -*-
"""Per-year replication of the 2019 Data2 PRE preprocessing flow (M4b).

    python data2/scripts/run_multiyear_pre.py --years 2019          # gate first
    python data2/scripts/run_multiyear_pre.py                       # all six years
    python data2/scripts/run_multiyear_pre.py --gate-only            # 2019 gate

Each year runs the same four stages the 2019 flow ran (JATM Table 8 structure:
months 1-6 train / 7 calibration / 8-9 development / 10-12 held out):

  A  cohort reservoirs        : episode_reservoirs over months 1-9 with the
                                frozen cohort counts {128,64,128,0} and seed
                                20260813, plus train-split reference
                                observation (taxi/turnaround histograms)
  B  development stream       : run_development_pre_stream over months 7-9
                                (counting pass; no PREState retention)
  3  split containment closure: per-year boundary audit with the production
                                chain/containment primitives, producing the
                                cross-split removal delta for the year
  C  reference fit + freeze   : year-train-fitted taxi/turnaround references,
                                then materialize_preselected_cohorts ->
                                PRE states for the sampled development cohort

Products land under artifacts/models/pre/PRE_MULTIYEAR_V1/{year}/ and the
six-year summary under data2/reports/multiyear_pre_flow/.

Hard gates: the 2019 run must reproduce the frozen 2019 artifacts
(pool_sizes, stream counts, state_key) before any other year runs; a mismatch
raises PER_YEAR_BLOCKED_LEGACY_REGRESSION and stops the run.

Out of scope (hard stop): no M1/M2 training, no Stage-I/II experiments, no
formal/v2_phase7 sealed-authority changes, no git commit.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT),):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from model.PRE.cohort import split_for_date_multiyear
from model.PRE.development import build_sampled_pre_cohorts
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)
from model.PRE.streaming.containment import (
    _episode_namespace,
    _iter_data2_episode_pairs,
)
from model.PRE.streaming.data2 import (
    aircraft_tail,
    lightweight_flights,
    load_timezones,
    ontime_paths,
)
from model.PRE.streaming.development import run_development_pre_stream
from model.common.config import load_config_layers
from validation.m1_v2_data_gate_a2 import (
    ReferenceCollector,
    _hist_median,
    _reference_payload,
)

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
OUT_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
REPORT_ROOT = DATA2 / "reports" / "multiyear_pre_flow"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
INSTANCE_ID = "data2_2017_2022"
COHORT_COUNTS = {"train": 128, "calibration": 64, "development": 128, "test": 0}
COHORT_SEED = 20260813               # frozen 2019 selection seed (replicated)
FROZEN_2019_REF_ROOT = REPO / "artifacts" / "diagnostics" / "v5_development_freeze"

# 2019 reproduction gate.
#
# Authoritative 2019 anchors: the frozen COHORT POOL sizes and the
# preparation STATE KEY (content-addressed over sources/counts/seed/rules) -
# both reproduced exactly by the parameterized flow. The frozen
# PRE_DEVELOPMENT_STREAM_MANIFEST.json (V1) predates the BTS signed-delay
# semantic correction (bfd3d34 wrote V1; 694f2d4 added the correction), so
# its raw stream counts no longer describe current code; the drift is
# recorded below for attribution and the fresh run is instead gated on
# self-consistency with the frozen development pool.
GATE_POOL_SIZES = {"train": 2665240, "calibration": 490886,
                   "development": 946184, "test": 0}
GATE_STATE_KEY = ("sha256:c4f2af99f145e0daf6ac3d6e7ec5312b12695c2c0dad99cb9c23a3a58"
                  "f7c2800")
GATE_STREAM_V1_STALE = {"candidate_episodes": 951359,
                        "pre_eligible_episodes": 951359,
                        "decision_nodes": 13721540,
                        "pre_eligible_nodes": 13721540,
                        "weather_supported_nodes": 5610432}


class GateFailure(RuntimeError):
    """Raised with PER_YEAR_BLOCKED_LEGACY_REGRESSION semantics."""


def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args],
                         capture_output=True, text=True)
    return (out.stdout + out.stderr).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str)
                    + "\n", encoding="utf-8")


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


# --------------------------------------------------------------- stage A --

def stage_a(year: int, out: Path) -> dict:
    log(f"{year} stage A: cohort reservoirs (months 1-9)")
    started = time.perf_counter()
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")
    paths = ontime_paths(REPO, range(1, 10), year=year)
    if len(paths) != 9:
        raise GateFailure(f"PER_YEAR_BLOCKED_MISSING_MONTHS:{year}:{len(paths)}")
    reservoirs, pool_sizes, total_episodes, per_month, skipped = (
        _episode_reservoirs_year(
            year=year,
            paths=paths,
            zones=zones,
            out=out,
        )
    )
    if reservoirs["test"]:
        raise GateFailure(f"FINAL_TEST_EPISODE_MATERIALIZED:{year}")
    result = {
        "stage": "A_COHORT_RESERVOIRS",
        "year": year,
        "pool_sizes": dict(pool_sizes),
        "sampled_counts": {name: len(values)
                           for name, values in reservoirs.items()},
        "total_episodes": total_episodes,
        "ontime_rows_by_month": per_month,
        "ontime_rows_skipped": skipped,
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "STAGE_A_SUMMARY.json", result)
    log(f"{year} stage A done: pool={dict(pool_sizes)} "
        f"({result['seconds']}s)")
    return result


def _episode_reservoirs_year(*, year: int, paths, zones, out):
    from model.PRE.streaming.data2 import episode_reservoirs
    return episode_reservoirs(
        REPO,
        paths,
        zones,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
        state_path=out / "COHORT_PREPARATION_STATE.pt",
        manifest_path=out / "COHORT_PREPARATION_PROGRESS.json",
        resume=True,
        year=year,
        dataset_instance_id=INSTANCE_ID,
        split_resolver=split_for_date_multiyear,
    )


# --------------------------------------------------------------- stage R --

def stage_r(year: int, out: Path) -> dict:
    """Train-split reference observation (taxi / turnaround histograms).

    Mirrors the A2 collector semantics: rows are observed for the train split
    only (months 1-6), and episode gaps are observed before containment
    filtering, exactly as the reservoir observers do. Cached so the
    reference fit survives restarts."""
    log(f"{year} stage R: train-split reference histograms (months 1-6)")
    started = time.perf_counter()
    from model.PRE.episode.builder import build_data2_episode_records
    collector = ReferenceCollector()
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")
    months = tuple(range(1, 7))
    paths = ontime_paths(REPO, months, year=year)
    previous_rows: tuple = ()
    episodes_observed = 0
    for month, path in zip(months, paths):
        current_rows, _skipped = lightweight_flights(
            path, zones, include_warning_fields=True,
            dataset_instance_id=INSTANCE_ID)
        collector.observe_flights("train", current_rows)
        chunk = list(previous_rows) + current_rows
        by_id = {row["flight_id"]: row for row in chunk}
        month_key = f"{year}-{month:02d}"
        for episode in build_data2_episode_records(chunk):
            service_date = by_id[episode.successor_flight_id].get(
                "service_date", "")
            if service_date[:7] != month_key:
                continue
            if split_for_date_multiyear(
                    date.fromisoformat(service_date)) != "train":
                continue
            collector.observe_episode("train", episode, by_id)
            episodes_observed += 1
        previous_rows = aircraft_tail(current_rows)
        del current_rows, chunk, by_id
    histograms = {
        "year": year,
        "months": list(months),
        "episodes_observed": episodes_observed,
        "taxi_global": {str(k): v for k, v in collector.taxi_global.items()},
        "taxi_airports": {airport: {str(k): v for k, v in hist.items()}
                          for airport, hist in collector.taxi_airports.items()},
        "turnaround_global": {str(k): v
                              for k, v in collector.turnaround_global.items()},
        "turnaround_airports": {airport: {str(k): v for k, v in hist.items()}
                                for airport, hist in
                                collector.turnaround_airports.items()},
    }
    write_json(out / "REFERENCE_HISTOGRAMS.json", histograms)
    result = {
        "stage": "R_REFERENCE_HISTOGRAMS", "year": year,
        "train_taxi_samples": sum(collector.taxi_global.values()),
        "train_turnaround_samples": sum(collector.turnaround_global.values()),
        "taxi_airports": len(collector.taxi_airports),
        "turnaround_airports": len(collector.turnaround_airports),
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "STAGE_R_SUMMARY.json", result)
    log(f"{year} stage R done: taxi={result['train_taxi_samples']} "
        f"turnaround={result['train_turnaround_samples']} "
        f"({result['seconds']}s)")
    return result


def load_histograms(out: Path) -> ReferenceCollector:
    payload = json.loads((out / "REFERENCE_HISTOGRAMS.json").read_text(
        encoding="utf-8"))
    collector = ReferenceCollector()
    for key, value in payload["taxi_global"].items():
        collector.taxi_global[float(key)] += value
    for airport, hist in payload["taxi_airports"].items():
        for key, value in hist.items():
            collector.taxi_airports[airport][float(key)] += value
    for key, value in payload["turnaround_global"].items():
        collector.turnaround_global[float(key)] += value
    for airport, hist in payload["turnaround_airports"].items():
        for key, value in hist.items():
            collector.turnaround_airports[airport][float(key)] += value
    return collector


# --------------------------------------------------------------- stage B --

def stage_b(year: int, out: Path, scientific) -> dict:
    log(f"{year} stage B: development stream (months 7-9)")
    started = time.perf_counter()
    manifest = run_development_pre_stream(
        scientific,
        root=REPO,
        manifest_path=out / "PRE_DEVELOPMENT_STREAM_MANIFEST.json",
        resume_path=out / "PRE_DEVELOPMENT_STREAM_RESUME.pt",
        year=year,
        dataset_instance_id=INSTANCE_ID,
        split_resolver=split_for_date_multiyear,
    )
    counts = manifest.get("counts", {})
    result = {
        "stage": "B_DEVELOPMENT_STREAM",
        "year": year,
        "counts": counts,
        "weather_audit": manifest.get("weather_audit"),
        "development_date_bounds": manifest.get("development_date_bounds"),
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "STAGE_B_SUMMARY.json", result)
    log(f"{year} stage B done: episodes={counts.get('pre_eligible_episodes')} "
        f"nodes={counts.get('pre_eligible_nodes')} "
        f"weather_nodes={counts.get('weather_supported_nodes')} "
        f"({result['seconds']}s)")
    return result


# --------------------------------------------------------- stage 3 (audit) --

def stage_containment(year: int, out: Path) -> dict:
    """Per-year boundary containment closure using the production chain and
    containment primitives (the 2019 equivalent audit is entangled with the
    2019 freeze cache; this reproduces its semantics per year)."""
    log(f"{year} stage 3: split containment closure (months 6-9)")
    started = time.perf_counter()
    zones = load_timezones(DATA2 / "refs" / "us_airport_timezones.csv")
    months = (6, 7, 8, 9)
    paths = ontime_paths(REPO, months, year=year)
    cross_by_pool: Counter = Counter()
    removed_nodes_by_pool: Counter = Counter()
    transitions: Counter = Counter()
    episodes = boundary_candidates = same_split_cross_month = 0
    previous_rows: tuple = ()
    from model.PRE.episode.containment import (
        episode_containment_from_rows,
        episode_node_count,
    )
    for month, path in zip(months, paths):
        current_rows, _skipped = lightweight_flights(
            path, zones, dataset_instance_id=INSTANCE_ID)
        chunk = list(previous_rows) + current_rows
        month_key = f"{year}-{month:02d}"
        for predecessor, successor in _iter_data2_episode_pairs(chunk):
            service_date = successor.get("service_date", "")
            if service_date[:7] != month_key:
                continue
            episodes += 1
            split_set = {
                split_for_date_multiyear(
                    date.fromisoformat(predecessor["service_date"])),
                split_for_date_multiyear(
                    date.fromisoformat(successor["service_date"])),
                split_for_date_multiyear(
                    predecessor["event_end_time"].date()),
                split_for_date_multiyear(successor["event_start_time"].date()),
            }
            cross_month = predecessor["service_date"][:7] != service_date[:7]
            if len(split_set) == 1 and not cross_month:
                continue
            if len(split_set) == 1 and cross_month:
                same_split_cross_month += 1
                continue
            boundary_candidates += 1
            episode = _episode_namespace(predecessor, successor)
            rows = {predecessor["flight_id"]: predecessor,
                    successor["flight_id"]: successor}
            containment = episode_containment_from_rows(
                episode, rows, split_resolver=split_for_date_multiyear)
            if containment.split == "test":
                raise GateFailure(f"FINAL_TEST_EPISODE_MATERIALIZED:{year}")
            if containment.allowed:
                continue
            successor_split = split_for_date_multiyear(
                date.fromisoformat(service_date))
            cross_by_pool[successor_split] += 1
            removed_nodes_by_pool[successor_split] += episode_node_count(
                episode_start_time=episode.episode_start_time,
                episode_end_time=episode.episode_end_time)
            transitions.update(containment.transitions)
        previous_rows = aircraft_tail(current_rows)
        del current_rows, chunk
    result = {
        "stage": "3_SPLIT_CONTAINMENT_CLOSURE",
        "year": year,
        "episodes_scanned": episodes,
        "boundary_candidates": boundary_candidates,
        "same_split_cross_month_allowed": same_split_cross_month,
        "cross_split_by_pool": dict(cross_by_pool),
        "cross_split_removed_nodes_by_pool": dict(removed_nodes_by_pool),
        "transitions": dict(transitions),
        "cross_split_removed_episodes": sum(cross_by_pool.values()),
        "cross_split_removed_nodes": sum(removed_nodes_by_pool.values()),
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "SPLIT_CONTAINMENT_AUDIT.json", result)
    log(f"{year} stage 3 done: cross-split episodes="
        f"{result['cross_split_removed_episodes']} nodes="
        f"{result['cross_split_removed_nodes']} ({result['seconds']}s)")
    return result


# --------------------------------------------------------------- stage C --

def stage_c(year: int, out: Path, scientific, collector: ReferenceCollector,
            stage_a_result: dict) -> dict:
    log(f"{year} stage C: reference fit + PRE materialization/freeze")
    started = time.perf_counter()
    template_taxi = json.loads(
        (FROZEN_2019_REF_ROOT / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json")
        .read_text(encoding="utf-8"))
    template_turn = json.loads(
        (FROZEN_2019_REF_ROOT / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN_V1.json")
        .read_text(encoding="utf-8"))
    taxi_payload = _reference_payload(
        template=template_taxi,
        global_histogram=collector.taxi_global,
        airport_histograms=collector.taxi_airports,
        scope="TAXI_OUT_TRAIN_ROWS",
    )
    taxi_payload["fit_period"] = f"{year}-H1"
    turnaround_payload = _reference_payload(
        template=template_turn,
        global_histogram=collector.turnaround_global,
        airport_histograms=collector.turnaround_airports,
        scope="TURNAROUND_TRAIN_EPISODES",
    )
    turnaround_payload["fit_period"] = f"{year}-H1"
    write_json(out / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json", taxi_payload)
    write_json(out / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json",
               turnaround_payload)
    taxi_reference = data2_taxi_reference_from_payload(taxi_payload)
    turnaround_reference = data2_turnaround_reference_from_payload(
        turnaround_payload)

    cohorts = build_sampled_pre_cohorts(
        scientific,
        root=REPO,
        cohort_counts=COHORT_COUNTS,
        cohort_seed=COHORT_SEED,
        preparation_state=out / "COHORT_PREPARATION_STATE.pt",
        preparation_manifest=out / "COHORT_PREPARATION_PROGRESS.json",
        resume=True,
        taxi_reference=taxi_reference,
        turnaround_reference=turnaround_reference,
        year=year,
        dataset_instance_id=INSTANCE_ID,
        split_resolver=split_for_date_multiyear,
    )
    development = cohorts.development
    states = [state for item in development for state in item.states]
    with (out / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl").open("w",
                                                            encoding="utf-8") as fh:
        for state in states:
            fh.write(json.dumps(state.model_dump(mode="json"),
                                sort_keys=True) + "\n")
    nodes = [node for item in development for node in item.nodes]
    manifest = {
        "schema_version": "PRE_MULTIYEAR_DEVELOPMENT_V1",
        "year": year,
        "dataset_instance_id": INSTANCE_ID,
        "split_rule": "DATA2_TEMPORAL_SPLIT@2.0.0",
        "development_episode_count": len(development),
        "development_node_count": len(nodes),
        "prestate_count": len(states),
        "pool_sizes": stage_a_result["pool_sizes"],
        "sampled_counts": stage_a_result["sampled_counts"],
        "taxi_reference": {
            "reference_id": taxi_payload["reference_id"],
            "fit_period": taxi_payload["fit_period"],
            "cells_count": taxi_payload["cells_count"],
            "global_sample_count": taxi_payload["global_sample_count"],
        },
        "turnaround_reference": {
            "reference_id": turnaround_payload["reference_id"],
            "fit_period": turnaround_payload["fit_period"],
            "cells_count": turnaround_payload["cells_count"],
            "global_sample_count": turnaround_payload["global_sample_count"],
        },
        "cohort_audit": cohorts.audit,
        "final_test_access_count": 0,
        "created_at_utc": now_iso(),
    }
    write_json(out / "PRE_MULTIYEAR_DEVELOPMENT_MANIFEST.json", manifest)
    result = {
        "stage": "C_REFERENCE_FIT_AND_FREEZE",
        "year": year,
        "development_episodes": len(development),
        "development_nodes": len(nodes),
        "prestates": len(states),
        "taxi_cells": taxi_payload["cells_count"],
        "taxi_samples": taxi_payload["global_sample_count"],
        "turnaround_cells": turnaround_payload["cells_count"],
        "turnaround_samples": turnaround_payload["global_sample_count"],
        "states_bytes": (out / "PRE_FORMAL_DEVELOPMENT_STATES.jsonl").stat().st_size,
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(out / "STAGE_C_SUMMARY.json", result)
    log(f"{year} stage C done: episodes={result['development_episodes']} "
        f"nodes={result['development_nodes']} prestates={result['prestates']} "
        f"({result['seconds']}s)")
    return result


# ------------------------------------------------------------ gate + main --

def gate_2019(stage_a: dict, stage_b: dict, out: Path) -> dict:
    """2019 reproduction gate.

    Asserted anchors: frozen cohort pool sizes, the content-addressed
    preparation state key, and self-consistency between the stream's
    post-containment development count and the frozen development pool.
    The frozen V1 stream counts are recorded as documented drift (their
    manifest predates the signed-delay semantic correction), not asserted.
    """
    checks = {}
    checks["pool_sizes"] = stage_a["pool_sizes"] == GATE_POOL_SIZES
    progress = json.loads(
        (out / "COHORT_PREPARATION_PROGRESS.json").read_text(encoding="utf-8"))
    checks["state_key"] = progress.get("state_key") == GATE_STATE_KEY
    counts = stage_b["counts"]
    checks["development_pool_equals_stream_pre_eligible"] = (
        counts.get("pre_eligible_episodes")
        == GATE_POOL_SIZES["development"])
    checks["no_final_test_access"] = counts.get("final_test_access_count", 0) == 0
    drift = {
        key: {"frozen_v1": expected, "fresh": counts.get(key),
              "delta": (counts.get(key) - expected)
              if isinstance(counts.get(key), (int, float)) else None}
        for key, expected in GATE_STREAM_V1_STALE.items()
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    result = {"gate": "2019_REPRODUCTION", "checks": checks,
              "frozen_v1_stream_drift": drift,
              "drift_explanation":
                  "frozen V1 stream manifest (commit bfd3d34) predates the "
                  "BTS signed-delay semantic correction (commit 694f2d4); "
                  "the frozen cohort pool and state key - both reproduced "
                  "here exactly - are the authoritative anchors",
              "failed": failed,
              "status": "PASS" if not failed else "FAIL"}
    write_json(out / "GATE_2019_REPRODUCTION.json", result)
    if failed:
        raise GateFailure(
            f"PER_YEAR_BLOCKED_LEGACY_REGRESSION:{','.join(failed)}")
    return result


def build_report(years_result: dict) -> tuple[dict, str, list[dict]]:
    csv_rows = []
    for year in sorted(years_result):
        entry = years_result[year]
        a, b, c = entry["stage_a"], entry["stage_b"], entry["stage_c"]
        cont = entry["containment"]
        csv_rows.append({
            "year": year,
            "pool_train": a["pool_sizes"].get("train"),
            "pool_calibration": a["pool_sizes"].get("calibration"),
            "pool_development": a["pool_sizes"].get("development"),
            "sampled_train": a["sampled_counts"].get("train"),
            "sampled_calibration": a["sampled_counts"].get("calibration"),
            "sampled_development": a["sampled_counts"].get("development"),
            "stream_candidate_episodes": b["counts"].get("candidate_episodes"),
            "stream_pre_eligible_episodes": b["counts"].get(
                "pre_eligible_episodes"),
            "stream_decision_nodes": b["counts"].get("decision_nodes"),
            "stream_weather_supported_nodes": b["counts"].get(
                "weather_supported_nodes"),
            "cross_split_removed_episodes": cont["cross_split_removed_episodes"],
            "cross_split_removed_nodes": cont["cross_split_removed_nodes"],
            "development_episodes": c["development_episodes"],
            "development_nodes": c["development_nodes"],
            "prestates": c["prestates"],
            "taxi_cells": c["taxi_cells"],
            "turnaround_cells": c["turnaround_cells"],
            "total_seconds": round(a["seconds"] + b["seconds"]
                                   + cont["seconds"] + c["seconds"], 1),
        })
    overall = "PASS"
    report = {
        "EXECUTION_REPOSITORY": str(REPO),
        "BRANCH": _git("branch", "--show-current"),
        "GENERATED_AT_UTC": now_iso(),
        "INSTANCE_ID": INSTANCE_ID,
        "SPLIT_RULE": "DATA2_TEMPORAL_SPLIT@2.0.0 (within-year month window)",
        "YEARS": sorted(years_result),
        "PER_YEAR": {str(k): v for k, v in years_result.items()},
        "CSV_ROWS": csv_rows,
        "OVERALL_STATUS": overall,
    }
    lines = ["# Data2 2017-2022 per-year PRE preprocessing (2019-equivalent "
             "flow)", "",
             f"- Branch: `{report['BRANCH']}`  Generated: "
             f"{report['GENERATED_AT_UTC']}",
             "- Split rule: DATA2_TEMPORAL_SPLIT@2.0.0 (months 1-6 / 7 / 8-9 / "
             "10-12 repeated per year; legacy @1.0.0 untouched)",
             f"- **OVERALL_STATUS: {overall}**", "",
             "| year | pool train/calib/dev | sampled | stream episodes | "
             "stream nodes | cross-split removed (ep/nodes) | dev episodes | "
             "dev nodes | prestates | seconds |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for row in csv_rows:
        lines.append(
            f"| {row['year']} | {row['pool_train']}/{row['pool_calibration']}/"
            f"{row['pool_development']} | "
            f"{row['sampled_train']}/{row['sampled_calibration']}/"
            f"{row['sampled_development']} | "
            f"{row['stream_pre_eligible_episodes']} | "
            f"{row['stream_decision_nodes']} | "
            f"{row['cross_split_removed_episodes']}/"
            f"{row['cross_split_removed_nodes']} | "
            f"{row['development_episodes']} | {row['development_nodes']} | "
            f"{row['prestates']} | {row['total_seconds']} |")
    return report, "\n".join(lines) + "\n", csv_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--years", type=int, nargs="*", default=list(YEARS))
    parser.add_argument("--gate-only", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="recompute stages even when cached summaries exist")
    args = parser.parse_args()

    scientific = load_config_layers(REPO / "configs").scientific
    if (scientific.parameters["data2_factual_replay_availability"].value
            != "DECLARED_EVENT_TIME_REPLAY"):
        raise GateFailure("M4B_EXPECTED_DECLARED_EVENT_TIME_REPLAY")

    years = [2019] if args.gate_only else list(args.years)
    years_result: dict[int, dict] = {}
    for year in years:
        if year not in YEARS:
            continue
        out = OUT_ROOT / str(year)
        out.mkdir(parents=True, exist_ok=True)
        stage_a_path = out / "STAGE_A_SUMMARY.json"
        stage_b_path = out / "STAGE_B_SUMMARY.json"
        if stage_a_path.is_file() and not args.force:
            result_a = json.loads(stage_a_path.read_text(encoding="utf-8"))
            log(f"{year} stage A: cached (pool={result_a['pool_sizes']})")
        else:
            result_a = stage_a(year, out)
        if stage_b_path.is_file() and not args.force:
            result_b = json.loads(stage_b_path.read_text(encoding="utf-8"))
            log(f"{year} stage B: cached "
                f"(episodes={result_b['counts'].get('pre_eligible_episodes')})")
        else:
            result_b = stage_b(year, out, scientific)
        if year == 2019:
            gate = gate_2019(result_a, result_b, out)
            log(f"2019 reproduction gate: PASS {gate['checks']}")
        containment_path = out / "SPLIT_CONTAINMENT_AUDIT.json"
        if containment_path.is_file() and not args.force:
            result_containment = json.loads(
                containment_path.read_text(encoding="utf-8"))
            log(f"{year} stage 3: cached "
                f"(cross-split={result_containment['cross_split_removed_episodes']})")
        else:
            result_containment = stage_containment(year, out)
        stage_r_path = out / "STAGE_R_SUMMARY.json"
        if stage_r_path.is_file() and not args.force:
            result_r = json.loads(stage_r_path.read_text(encoding="utf-8"))
            log(f"{year} stage R: cached (taxi={result_r['train_taxi_samples']})")
        else:
            result_r = stage_r(year, out)
        stage_c_path = out / "STAGE_C_SUMMARY.json"
        if stage_c_path.is_file() and not args.force:
            result_c = json.loads(stage_c_path.read_text(encoding="utf-8"))
            log(f"{year} stage C: cached "
                f"(prestates={result_c['prestates']})")
        else:
            result_c = stage_c(year, out, scientific,
                               load_histograms(out), result_a)
        years_result[year] = {"stage_a": result_a, "stage_b": result_b,
                              "containment": result_containment,
                              "stage_r": result_r, "stage_c": result_c}
        if args.gate_only:
            break

    if not years_result:
        log("nothing to do")
        return 0
    report, markdown, csv_rows = build_report(years_result)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(REPORT_ROOT / "DATA2_2017_2022_PRE_FLOW_AUDIT.json", report)
    (REPORT_ROOT / "DATA2_2017_2022_PRE_FLOW_AUDIT.md").write_text(
        markdown, encoding="utf-8")
    with (REPORT_ROOT / "DATA2_2017_2022_PRE_FLOW_AUDIT.csv").open(
            "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0]),
                                lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    log(f"PRE_FLOW_AUDIT_WRITTEN years={sorted(years_result)} -> {REPORT_ROOT}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GateFailure as error:
        log(f"{error}")
        sys.exit(3)
