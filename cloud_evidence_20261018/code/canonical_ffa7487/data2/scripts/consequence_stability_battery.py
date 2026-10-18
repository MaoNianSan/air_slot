# -*- coding: utf-8 -*-
"""Consequence-side cohort-size stability battery (M5-b).

    python data2/scripts/consequence_stability_battery.py --phase sentinel --years 2019
    python data2/scripts/cohort_size_study.py --collect --years 2019        # if pool missing
    python data2/scripts/consequence_stability_battery.py --phase fit   --years 2019 2020
    python data2/scripts/consequence_stability_battery.py --phase eval  --years 2019 2020

HARD SCOPE: development window only (Y-08-01..09-30); zero Oct-Dec reads.
Protocol: data2/reports/cohort_size_stability/CONSEQUENCE_STABILITY_PROTOCOL_V1.json
(hash frozen before any metric; compute fallback ladder is runtime/memory-only).

FIT  : M1_N trained on the N-prefix of the hash-ranked TRAIN cohort
       (calibration N/2 from Y-07), all evaluated on the SAME fixed dev cases.
EVAL : fixed M1_4096; development cohorts are nested hash-ranked prefixes;
       nested-cohort bootstrap preserves D_N subset D_4096 within replicates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from typing import Any
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from model.PRE.cohort import split_for_date_multiyear
from model.PRE.development import materialize_preselected_cohorts
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import (
    data2_turnaround_reference_from_payload,
)
from model.M1.data import (
    FEATURE_NAMES_V2,
    STATIC_FEATURE_COUNT,
    fit_train_normalization,
)
from model.M1.lifecycle import M1Lifecycle
from model.M1.pipeline import M1Pipeline
from model.M1.preparation import (
    active_rows,
    build_training_examples,
    fit_static_normalization_from_rows,
    normalization_rows,
)
from model.common.config import load_config_layers
from model.common.cu_normalization import CUNormalizationRegistry
from model.M2.valuation import M2CUNormalizationAdapter

REPO = _REPO_ROOT
DATA2 = REPO / "data2"
STUDY_ROOT = DATA2 / "reports" / "cohort_size_stability"
PRE_ROOT = REPO / "artifacts" / "models" / "pre" / "PRE_MULTIYEAR_V1"
INSTANCE_ID = "data2_2017_2022"
FIXED_M5_SEED = "M5-COHORT-SEED-20260928"
N_GRID = (128, 256, 512, 1024, 2048, 4096)
N_REF = 4096
SCENARIO_COUNT = 64
TRAIN_SEED = 20260821
BOOTSTRAP_SEED = 20260906
BOOTSTRAP_REPLICATES = 2000
EVAL_BUDGET_HOURS = 6.0

# pre-registered compute fallback ladder (runtime/memory ONLY; never outcome-aware)
LADDER = (4096, 2048, 1024)


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(message: str) -> None:
    print(f"[{now_iso()}] {message}", flush=True)


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False,
                               default=str) + "\n", encoding="utf-8")


def protocol_hash() -> str:
    """Frozen CONSEQUENCE_STABILITY_PROTOCOL_V2 hash (created/verified on demand)."""

    import consequence_stability_metrics as m5b
    path = STUDY_ROOT / "CONSEQUENCE_STABILITY_PROTOCOL_V2.json"
    if not path.is_file():
        m5b.create_or_verify_protocol_v2(STUDY_ROOT)
    return json.loads(path.read_text(encoding="utf-8"))["protocol_hash"]


def load_hash_cohort(year: int) -> dict[str, list]:
    """(rank, EpisodeRecord) per split, sorted by rank — from the M5 pool pass."""
    path = STUDY_ROOT / str(year) / "HASH_SELECTED_COHORT_RECORDS_N4096.jsonl"
    from model.PRE.contracts.pre_state import EpisodeRecord
    records: dict[str, list] = {"train": [], "calibration": [],
                                "development": []}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            records[row["split"]].append(
                (row["rank"], EpisodeRecord.model_validate(row["episode"])))
    for split in records:
        records[split].sort(key=lambda item: item[0])
    return records


def year_references(year: int):
    root = PRE_ROOT / str(year)
    taxi = data2_taxi_reference_from_payload(json.loads(
        (root / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN.json").read_text("utf-8")))
    turnaround = data2_turnaround_reference_from_payload(json.loads(
        (root / "DATA2_TURNAROUND_REFERENCE_TRAIN_FROZEN.json").read_text("utf-8")))
    return taxi, turnaround


def year_scales(year: int) -> dict[str, float]:
    import consequence_stability_metrics as m5b
    return m5b.load_year_m2_bundle(year)["scales"]


# ------------------------------------------------------------- M1_N train --

def prefix_partitions(selected: dict[str, list], n: int):
    counts = {"train": n, "calibration": max(1, n // 2), "development": n}
    return {split: tuple(episode for _rank, episode in
                         selected[split][:count])
            for split, count in counts.items()}


def examples_digest(examples: tuple) -> str:
    """Deterministic digest of a built training-example tuple."""
    digest = hashlib.sha256()
    for ex in examples:
        digest.update(ex.episode_id.encode("utf-8"))
        values = ex.values.detach().numpy().tobytes() if hasattr(
            ex.values, "numpy") else bytes(ex.values)
        digest.update(len(values).to_bytes(8, "little"))
        digest.update(values)
    return "sha256:" + digest.hexdigest()


def normalization_digest(normalization) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(normalization.model_dump(mode="json"), sort_keys=True,
                   default=str).encode("utf-8")).hexdigest()


def calibration_digest(temperatures) -> str:
    """Deterministic digest of the fitted temperature payload.

    Accepts only a mapping of temperature name -> float (or a pydantic model
    exposing ``model_dump``).  Anything else raises instead of silently hashing
    an object repr, which would fabricate a nondeterminism signal.
    """

    if hasattr(temperatures, "model_dump"):
        payload = temperatures.model_dump(mode="json")
    elif isinstance(temperatures, dict):
        payload = {str(key): float(value)
                   for key, value in temperatures.items()}
    else:
        raise ValueError(
            "M5B_CALIBRATION_DIGEST_UNSUPPORTED_INPUT:"
            f"{type(temperatures).__name__}")
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def state_dict_digest(lifecycle) -> str:
    model = lifecycle.pipeline.model
    return "sha256:" + hashlib.sha256(
        str({k: v.detach().cpu().numpy().tobytes()
             for k, v in model.state_dict().items()}).encode("utf-8")
    ).hexdigest()


def train_m1_n(year: int, n: int, scientific, selected: dict[str, list],
               out_root: Path) -> dict:
    """Train M1_N on the hash-ranked prefix; returns hashes + checkpoint path."""
    out = out_root / f"N{n}"
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "M1_N.pt"
    hash_record_path = out / "M1_N_HASHES.json"
    if hash_record_path.is_file():
        record = json.loads(hash_record_path.read_text(encoding="utf-8"))
        recorded_hash = record.get("checkpoint_hash")
        # cache hit requires: record present + checkpoint present + hash match
        if checkpoint.is_file() and (
                recorded_hash is None or recorded_hash == _file_hash(checkpoint)):
            log(f"  {year} N={n}: cached (skip training)")
            return record
        log(f"  {year} N={n}: stale cache (checkpoint missing/hash mismatch); "
            "retraining")

    started = time.perf_counter()
    taxi, turnaround = year_references(year)
    partitions = prefix_partitions(selected, n)
    cohorts = materialize_preselected_cohorts(
        scientific,
        root=REPO,
        partitions=partitions,
        year=year,
        dataset_instance_id=INSTANCE_ID,
        split_resolver=split_for_date_multiyear,
        taxi_reference=taxi,
        turnaround_reference=turnaround,
    )
    rows, stages = {}, {}
    for split in ("train", "calibration", "development"):
        rows[split], stages[split] = active_rows(
            getattr(cohorts, split), taxi_reference=taxi)
    normalization = fit_train_normalization(
        normalization_rows([prefix for _ep, prefix, _lbl in rows["train"]]),
        split="train")
    static_normalization = fit_static_normalization_from_rows(rows["train"])
    examples = {
        split: build_training_examples(
            rows[split], normalization, None,
            static_normalization=static_normalization)
        for split in rows}

    hidden_size = int(scientific.parameters["m1_hidden_size"].value)
    # Determinism gate (frozen protocol floor_rule): M1V2GRU construction
    # consumes the ambient global RNG, so without an explicit seed every
    # retraining starts from different initial weights -- the measured source
    # of TRAINING_NONDETERMINISM.  Seed immediately BEFORE construction; the
    # lifecycle's own seed (TRAIN_SEED) still governs training downstream.
    torch.manual_seed(TRAIN_SEED)
    pipeline = M1Pipeline.from_scientific_config(
        scientific,
        input_size=len(FEATURE_NAMES_V2),
        normalization=normalization,
        hidden_size=hidden_size,
        static_input_size=STATIC_FEATURE_COUNT,
        static_normalization=static_normalization,
    )
    lifecycle = M1Lifecycle(pipeline, device="cpu")
    lifecycle.train(
        examples["train"],
        epochs=2,
        learning_rate=0.001,
        batch_size=64,
        bucketed=True,
        seed=TRAIN_SEED,
        teacher_forcing=True,
    )
    lifecycle.calibrate(examples["calibration"], batch_size=64)
    lifecycle.save(checkpoint)

    record = {
        "year": year, "n": n,
        "train_episodes": len(partitions["train"]),
        "calibration_episodes": len(partitions["calibration"]),
        "train_examples": len(examples["train"]),
        "calibration_examples": len(examples["calibration"]),
        "development_nodes": sum(len(item.nodes) for item in cohorts.development),
        "examples_digest": examples_digest(examples["train"]),
        "normalization_digest": normalization_digest(normalization),
        # digest the ACTUAL fitted temperatures (pipeline.temperatures); the
        # earlier fallback hashed the lifecycle object's repr (which embeds the
        # memory address) and therefore reported a false nondeterminism signal
        "calibration_digest": calibration_digest(
            dict(lifecycle.pipeline.temperatures)),
        "state_dict_digest": state_dict_digest(lifecycle),
        "checkpoint": str(checkpoint),
        "checkpoint_hash": _file_hash(checkpoint),
        "seconds": round(time.perf_counter() - started, 1),
    }
    write_json(hash_record_path, record)
    log(f"  {year} N={n}: trained ({record['seconds']}s, "
        f"{record['train_examples']} examples)")
    return record


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _protocol_payload() -> dict:
    import consequence_stability_metrics as m5b
    return m5b.create_or_verify_protocol_v2(STUDY_ROOT)


# ---------------------------------------------------------------- scope --
# ``--scope-tag`` redirects the SHARED battery artifacts (sentinel verdict,
# floor quantification, smoke, EVAL summary) into a per-scope subdirectory so
# parallel extension-year runs never overwrite the pilot's files.  Year-keyed
# artifacts (passes, checkpoints, per-year comparisons, ladder probes) keep
# their year keys and are never redirected.
SCOPE_TAG = None
# INPUT_ROOT  : frozen read-only inputs (protocol, PRE cohort records, M2 bundles)
# OUTPUT_ROOT : every artifact this run writes (passes, checkpoints, metrics,
#               summaries, logs).  Defaults to STUDY_ROOT so the 2019/2020 pilot
#               run keeps writing exactly where it always did; extension runs
#               point it at their own directory and can never overwrite the
#               pilot's or another year's results.
INPUT_ROOT = STUDY_ROOT
OUTPUT_ROOT = STUDY_ROOT


def out_path(*parts: str | int) -> Path:
    return OUTPUT_ROOT.joinpath(*(str(part) for part in parts))


def scoped_path(name: str) -> Path:
    return (OUTPUT_ROOT / SCOPE_TAG / name) if SCOPE_TAG else (OUTPUT_ROOT / name)


def _pass_dir(year: int, tag: str) -> Path:
    return out_path(year, "passes", tag)


def _ladder_e(year: int) -> int:
    path = OUTPUT_ROOT / f"LADDER_PROBE_{year}.json"
    if not path.is_file():
        raise RuntimeError(f"BLOCK_M5B_LADDER_PROBE_MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "PASS":
        raise RuntimeError(f"BLOCK_M5B_COMPUTE_BUDGET:{year}")
    return int(payload["evaluation_E"])


EVAL_IMPLEMENTED = True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", required=True,
                        choices=["sentinel", "headroom", "ladder", "smoke",
                                 "floor", "fit", "eval"])
    parser.add_argument("--years", type=int, nargs="*", default=[2019, 2020])
    parser.add_argument("--n", type=int, nargs="*", default=list(N_GRID))
    parser.add_argument("--reuse-fit-comparison", action="store_true",
                        help="eval phase: reuse hash-verified FIT comparison "
                             "payloads instead of recomputing them")
    parser.add_argument("--scope-tag", default=None,
                        help="redirect shared battery artifacts into "
                             "<output-root>/<scope-tag>/")
    parser.add_argument("--output-root", default=None,
                        help="directory for ALL artifacts of this run "
                             "(passes, checkpoints, metrics, summaries); "
                             "inputs keep being read from INPUT_ROOT")
    parser.add_argument("--bundle-base", default=None,
                        help="explicit M2-bundle base; default derives it "
                             "from --output-root")
    args = parser.parse_args()
    global SCOPE_TAG, OUTPUT_ROOT
    SCOPE_TAG = args.scope_tag
    if args.output_root:
        OUTPUT_ROOT = Path(args.output_root)
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    import consequence_stability_metrics as _m5b
    # runs with their own output root derive implicit artifacts (e.g. year
    # headroom summaries) there instead of leaking into the shared STUDY_ROOT
    study_base = OUTPUT_ROOT if OUTPUT_ROOT != STUDY_ROOT else None
    if args.bundle_base:
        _m5b.set_run_context(bundle_base=Path(args.bundle_base),
                             study_base=study_base)
    else:
        _m5b.set_run_context(bundle_base=study_base, study_base=study_base)
    for n in args.n:
        if n not in N_GRID:
            raise SystemExit(f"BLOCKED_PROTOCOL_SCOPE:N_OUT_OF_GRID:{n}")
    log(f"phase={args.phase} protocol={protocol_hash()[:20]}... "
        f"years={args.years} n={args.n}")
    scientific = load_config_layers(REPO / "configs").scientific
    selected = {year: load_hash_cohort(year) for year in args.years}
    if args.phase == "sentinel":
        return sentinel_phase(args.years, scientific, selected)
    if args.phase == "headroom":
        import consequence_stability_metrics as m5b
        for year in args.years:
            m5b.build_year_headroom(year, study_root=OUTPUT_ROOT)
        return 0
    if args.phase == "ladder":
        return ladder_phase(args.years, scientific, selected)
    if args.phase == "smoke":
        return smoke_phase(args.years, scientific, selected)
    if args.phase == "floor":
        return floor_phase(args.years, scientific, selected)
    if args.phase == "fit":
        return fit_phase(args.years, args.n, scientific, selected)
    if args.phase == "eval":
        if not EVAL_IMPLEMENTED:
            raise RuntimeError("BLOCKED_CONSEQUENCE_INTERFACE")
        return eval_phase(args.years, args.n, scientific, selected,
                          reuse_fit_comparison=args.reuse_fit_comparison)
    return 0


def sentinel_phase(years, scientific, selected_by_year) -> int:
    """Digest-only determinism detection.

    The continue/stop DECISION belongs to the frozen floor rule
    (DETERMINISM_FLOOR_QUANTIFICATION state), never to this phase.
    """
    verdicts = {}
    digest_keys = ("examples_digest", "normalization_digest",
                   "calibration_digest", "state_dict_digest")
    for year in years:
        for n in (128, 4096):
            digests = []
            for replica in (1, 2):
                out_root = out_path(year, f"sentinel_N{n}_r{replica}")
                digests.append(
                    train_m1_n(year, n, scientific, selected_by_year[year],
                               out_root=out_root))
            first, second = digests
            mismatches = [key for key in digest_keys
                          if first[key] != second[key]]
            verdicts[f"{year}_N{n}"] = {
                "deterministic": not mismatches,
                "nondeterminism_detected": bool(mismatches),
                "mismatched_digests": mismatches,
                "hashes": [first["state_dict_digest"][:22],
                           second["state_dict_digest"][:22]],
                "replica_checkpoints": [
                    str(out_path(year, f"sentinel_N{n}_r{r}", f"N{n}",
                                 "M1_N.pt")) for r in (1, 2)],
            }
    write_json(scoped_path("M1_DETERMINISM_SENTINEL.json"),
               {"verdicts": verdicts,
                "note": ("digest detection only; the continue/stop decision "
                         "is made by the frozen V2 floor rule"),
                "status": ("PASS" if all(v["deterministic"]
                                         for v in verdicts.values())
                           else "NONDETERMINISTIC")})
    detection = {key: value["deterministic"]
                 for key, value in verdicts.items()}
    log(f"sentinel: {json.dumps(detection)}")
    return 0


def ladder_phase(years, scientific, selected_by_year) -> int:
    """Runtime-only ladder probe; picks evaluation_E per year (frozen budget)."""
    import consequence_stability_metrics as m5b
    for year in years:
        checkpoint = out_path(year, "N128", "M1_N.pt")
        if not checkpoint.is_file():
            # legacy fallback: pilot-era chains ran ladder before fit and
            # probed the 2019 sentinel replica checkpoint
            checkpoint = out_path(2019, "sentinel_N128_r1", "N128", "M1_N.pt")
        if not checkpoint.is_file():
            raise RuntimeError(
                f"BLOCK_M5B_SENTINEL_CHECKPOINT_MISSING:{checkpoint}")
        m5b.ladder_probe(
            year, checkpoint=checkpoint,
            ranked_dev_episodes=selected_by_year[year]["development"],
            scientific=scientific,
            out_path=OUTPUT_ROOT / f"LADDER_PROBE_{year}.json")
    return 0


def smoke_phase(years, scientific, selected_by_year) -> int:
    """INTERFACE_SMOKE_ONLY: minimal closed loop on 3 dev episodes per year.

    Chain: sentinel checkpoint -> M2 bundle -> headroom -> bindings ->
    consequence/support frames -> Stage-I (canonical selector) -> Stage-II
    (canonical exact enumeration) -> metric layer (point values only).
    Bootstrap, equivalence and stability conclusions are NOT produced here.
    """
    import consequence_stability_metrics as m5b
    results: dict[str, Any] = {}
    failures: list[str] = []
    for year in years:
        checkpoint = out_path(year, "sentinel_N128_r1", "N128", "M1_N.pt")
        if not checkpoint.is_file():
            # 2020 has no trained checkpoint before FIT; reuse the 2019 sentinel
            # model for INTERFACE connectivity only (recorded explicitly).
            fallback = out_path(2019, "sentinel_N128_r1", "N128", "M1_N.pt")
            if year != 2019 and fallback.is_file():
                checkpoint = fallback
                model_note = (
                    f"2019 sentinel N128 model reused for {year} INTERFACE "
                    "connectivity only; the model-year mismatch is recorded "
                    "and no scientific reading is permitted")
            else:
                failures.append(f"{year}:BLOCK_M5B_SENTINEL_CHECKPOINT_MISSING")
                continue
        else:
            model_note = f"{year} sentinel N128 replica-1 checkpoint"
        try:
            cases = selected_by_year[year]["development"][:m5b.SMOKE_E]
            out_dir = _pass_dir(year, "smoke")
            manifest = m5b.evaluate_model_on_cases(
                year, checkpoint, cases, scientific=scientific,
                out_dir=out_dir, pass_id=f"{year}_smoke")
            rows = m5b.read_node_frame(out_dir)
            stage1 = m5b.stage1_evaluate(rows, cohort_id=f"SMOKE_{year}")
            shortlist = sorted({node
                                for info in stage1["per_stage"].values() if info
                                for node in info["shortlist"]})
            bundle = m5b.load_year_m2_bundle(year)
            service = m5b.service_from_pass(year, out_dir, bundle)
            headroom = m5b.year_headroom_summary(year, study_root=OUTPUT_ROOT)
            stage2 = m5b.stage2_solve_nodes(
                year, pass_dir=out_dir, node_ids=shortlist, service=service,
                headroom=headroom, want_curves=True)
            # metric layer exercise (point values only; no bootstrap here)
            eligible = [row for row in rows if row.get("eligible")]
            contrast_tau = m5b.contrast_tau(eligible)
            contrast_k = m5b.contrast_ranking_at_k(eligible)
            decisions = stage2["decisions"]
            actionable = [record for record in decisions.values()
                          if record.get("recoverable_value") is not None]
            activation = (sum(1 for record in actionable
                              if float(record["u_star"]) > 0.0)
                          / len(actionable)) if actionable else None
            results[str(year)] = {
                "status": "PASS",
                "checkpoint": str(checkpoint), "model_note": model_note,
                "node_count": len(rows),
                "bound_node_count": manifest["bound_node_count"],
                "eligible_node_count": len(eligible),
                "stage1_stages": {stage: ({"k": info["k"],
                                           "cohort_size": info["cohort_size"]}
                                          if info else None)
                                  for stage, info in stage1["per_stage"].items()},
                "stage1_shortlist_size": len(shortlist),
                "stage2_decisions": len(decisions),
                "stage2_curves": len(stage2.get("curves", {})),
                "stage2_activation_rate": activation,
                "metric_layer": {"contrast_kendall_tau_b": contrast_tau,
                                 "contrast_ranking_at_k": contrast_k},
                "headroom_summary_hash": m5b.sha256_json(
                    headroom.model_dump(mode="json")),
            }
            log(f"smoke {year}: nodes={len(rows)} "
                f"stage2={len(decisions)} tau={contrast_tau}")
        except Exception as error:  # keep the real traceback, then decide
            import traceback
            failures.append(f"{year}:{type(error).__name__}:{error}")
            results[str(year)] = {
                "status": "FAIL", "checkpoint": str(checkpoint),
                "model_note": model_note,
                "traceback": traceback.format_exc()[-3000:],
            }
    payload = {
        "schema_version": "M5B_SMOKE_V1",
        "status": ("PASS" if not failures else "FAIL"),
        "analysis_layer": "INTERFACE_SMOKE_ONLY",
        "note": ("3 episodes per year only; no bootstrap, no equivalence, and "
                 "no stability conclusion may be drawn from this artifact"),
        "years": results, "failures": failures,
        "final_test_access_count": 0,
    }
    payload["artifact_hash"] = m5b.sha256_json(
        {key: value for key, value in payload.items()
         if key != "artifact_hash"})
    m5b.write_json_atomic(scoped_path("M5B_SMOKE.json"), payload)
    if failures:
        raise RuntimeError("FAIL_EVAL_SMOKE:" + ";".join(failures[:3]))
    log("smoke: PASS for " + ",".join(results))
    return 0


def floor_phase(years, scientific, selected_by_year) -> int:
    """DETERMINISM_FLOOR_QUANTIFICATION per the frozen V2 floor rule.

    Scope = the protocol's sentinel settings (``m1_determinism_sentinel.runs``,
    i.e. 2019 only).  Requested years without a sentinel setting are recorded
    explicitly as NOT_QUANTIFIED (no protocol setting exists for them); they
    are never silently treated as deterministic.
    """
    import consequence_stability_metrics as m5b
    protocol = _protocol_payload()
    sentinel_path = scoped_path("M1_DETERMINISM_SENTINEL.json")
    if not sentinel_path.is_file():
        raise RuntimeError(f"BLOCK_M5B_SENTINEL_MISSING:{sentinel_path}")
    sentinel = json.loads(sentinel_path.read_text(encoding="utf-8"))
    sentinel_years = sorted({int(key.split("_")[0])
                             for key in sentinel["verdicts"]})
    not_quantified = [year for year in years if year not in sentinel_years]
    settings_payload = {}
    for year in sentinel_years:
        e_probe = _ladder_e(year)
        dev = selected_by_year[year]["development"][:e_probe]
        bundle = m5b.load_year_m2_bundle(year)
        headroom = m5b.year_headroom_summary(year, study_root=OUTPUT_ROOT)
        for n in (128, 4096):
            verdict = sentinel["verdicts"].get(f"{year}_N{n}")
            if verdict is None:
                raise RuntimeError(f"BLOCK_M5B_SENTINEL_SETTING_MISSING:{year}_N{n}")
            replica_dirs = []
            for replica, checkpoint in enumerate(
                    verdict["replica_checkpoints"], start=1):
                checkpoint_path = Path(checkpoint)
                if not checkpoint_path.is_file():
                    raise RuntimeError(
                        f"BLOCK_M5B_SENTINEL_CHECKPOINT_MISSING:{checkpoint_path}")
                out_dir = _pass_dir(year, f"floorN{n}_r{replica}")
                m5b.evaluate_model_on_cases(
                    year, checkpoint_path, dev, scientific=scientific,
                    out_dir=out_dir, pass_id=f"{year}_floorN{n}_r{replica}")
                replica_dirs.append(out_dir)
            service = m5b.service_from_pass(year, replica_dirs[0], bundle)
            setting = f"{year}_N{n}"
            settings_payload[setting] = m5b.floor_comparison(
                year, ref_pass_dir=replica_dirs[0],
                comp_pass_dir=replica_dirs[1], service=service,
                headroom=headroom, protocol=protocol,
                scales=bundle["scales"], setting=setting)
    decision = m5b.floor_decision(settings_payload, protocol)
    decision["years_not_quantified_no_protocol_setting"] = not_quantified
    payload = {
        "schema_version": "M5B_FLOOR_QUANTIFICATION_V1",
        "protocol_hash": protocol["protocol_hash"],
        "sentinel_settings_quantified": sorted(settings_payload),
        "settings": settings_payload,
        "decision": decision,
        "analysis_layer": "TRAINING_NONDETERMINISM_FLOOR_ONLY",
        "git": m5b.git_provenance(),
        "final_test_access_count": 0,
    }
    payload["artifact_hash"] = m5b.sha256_json(
        {key: value for key, value in payload.items()
         if key != "artifact_hash"})
    m5b.write_json_atomic(scoped_path("M5B_FLOOR_QUANTIFICATION.json"), payload)
    log(f"floor decision: {decision['decision']} "
        f"blocked={decision['blocked_metrics']}")
    return 0


def fit_phase(years, n_grid, scientific, selected_by_year) -> int:
    """FIT stage: train all M1_N checkpoints (metrics run in --phase eval)."""
    for year in years:
        for n in n_grid:
            train_m1_n(year, n, scientific, selected_by_year[year],
                       out_root=out_path(year))
    log("FIT stage training complete; evaluation phase next (--phase eval)")
    return 0


def eval_phase(years, n_grid, scientific, selected_by_year, *,
               reuse_fit_comparison: bool = False) -> int:
    """FIT-stage (paired bootstrap) + EVAL-stage (nested bootstrap) metrics."""
    import consequence_stability_metrics as m5b
    protocol = _protocol_payload()
    summary = {"schema_version": "M5B_EVAL_SUMMARY_V1",
               "protocol_hash": protocol["protocol_hash"],
               "bootstrap": {"replicates": m5b.BOOTSTRAP_REPLICATES,
                             "seed": m5b.BOOTSTRAP_SEED},
               "years": {}}
    for year in years:
        e_probe = _ladder_e(year)
        dev = selected_by_year[year]["development"][:e_probe]
        passes = {}
        for n in n_grid:
            checkpoint = out_path(year, f"N{n}", "M1_N.pt")
            if not checkpoint.is_file():
                raise RuntimeError(f"BLOCK_M5B_FIT_CHECKPOINT_MISSING:{checkpoint}")
            passes[int(n)] = _pass_dir(year, f"fitN{n}")
            m5b.evaluate_model_on_cases(
                year, checkpoint, dev, scientific=scientific,
                out_dir=passes[int(n)], pass_id=f"{year}_fitN{n}")
        ref_n = N_REF if N_REF in passes else max(passes)
        ref_dir = passes[ref_n]
        comp_dirs = {n: path for n, path in passes.items() if n != ref_n}
        bundle = m5b.load_year_m2_bundle(year)
        headroom = m5b.year_headroom_summary(year, study_root=OUTPUT_ROOT)
        service = m5b.service_from_pass(year, ref_dir, bundle)
        if reuse_fit_comparison:
            # reuse hash-verified FIT comparison payloads (this comparison path
            # is not affected by the nested-cohort convention fix); recompute
            # only when a payload is missing
            fit = {}
            for n in sorted(passes):
                if int(n) == ref_n:
                    continue
                payload_path = OUTPUT_ROOT / f"FIT_METRICS_{year}_N{n}.json"
                if payload_path.is_file():
                    fit[int(n)] = json.loads(payload_path.read_text(encoding="utf-8"))
                    log(f"FIT comparison {year} N{n}: reused (unaffected path)")
                else:
                    fit.update(m5b.fit_comparison_batch(
                        year, n_grid=[n], ref_pass_dir=ref_dir,
                        comp_pass_dirs={n: passes[n]}, service=service,
                        headroom=headroom, protocol=protocol,
                        scales=bundle["scales"], out_root=OUTPUT_ROOT))
        else:
            fit = m5b.fit_comparison_batch(
                year, n_grid=sorted(passes), ref_pass_dir=ref_dir,
                comp_pass_dirs=comp_dirs, service=service, headroom=headroom,
                protocol=protocol, scales=bundle["scales"], out_root=OUTPUT_ROOT)
        ev = m5b.eval_comparison_batch(
            year, n_grid=sorted(passes), ref_pass_dir=ref_dir,
            service=service, headroom=headroom, protocol=protocol,
            scales=bundle["scales"], out_root=OUTPUT_ROOT,
            evaluation_e=e_probe)
        summary["years"][str(year)] = {
            "evaluation_E": e_probe,
            "fit": {str(n): {name: record["status"]
                             for name, record in payload["results"].items()}
                    for n, payload in fit.items()},
            "eval": {str(n): (payload.get("status")
                              or {name: record["status"]
                                  for name, record in payload["results"].items()})
                     for n, payload in ev.items()},
        }
    failed = []
    ladder_capped = []
    for year in years:
        year_summary = summary["years"][str(year)]
        for stage in ("fit", "eval"):
            at_2048 = year_summary[stage].get(str(2048))
            if isinstance(at_2048, str):
                if at_2048 == "NOT_IDENTIFIABLE_AT_THIS_N":
                    ladder_capped.append(f"{year}:{stage}")
                continue
            for name, status in (at_2048 or {}).items():
                if status == "FAIL":
                    failed.append(f"{year}:{stage}:{name}")
    if ladder_capped:
        decision = {"status": "N_GRID_UPPER_BOUND_REACHED",
                    "reason": "ladder_cap",
                    "ladder_capped_2048": ladder_capped,
                    "failed_instances": sorted(set(failed))}
    else:
        decision = {"status": ("N_GRID_UPPER_BOUND_REACHED" if failed
                               else "M5B_PILOT_COMPLETE_HARD_STOP"),
                    "failed_instances": sorted(set(failed))}
    summary["decision"] = decision
    write_json(scoped_path("EVAL_SUMMARY.json"), summary)
    log(f"eval decision: {decision['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
