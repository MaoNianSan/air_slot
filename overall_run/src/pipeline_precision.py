from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .audit import evaluate_precision_audit
from .config import RunConfig, dump_config_snapshot
from .failures import FormalRunBlocked
from .input import load_pre_bundle, normalize_bundle
from .m1 import prepare_model_frame
from .m3 import generate_m3_library, load_actions
from .m4 import evaluate_m4
from .metric import precision_metrics
from .pipeline_checkpoint import prepare_empty_publish_target
from .pipeline_data import (
    attach_rule_context,
    enrich_snapshots,
    set_model_attrs,
    write_frame,
)
from .progress import Progress
from .utils import run_id, stable_hash, write_json


def run_precision(
    cfg: RunConfig,
    progress_level: str = "normal",
    pre_output: Path | None = None,
) -> Path:
    """Re-evaluate a frozen accepted action set with a larger MC budget."""
    progress = Progress(progress_level)
    parent_mode: str | None = None
    parent: Path | None = None
    parent_summary: dict[str, Any] | None = None
    for candidate in ("adapt_full", "full"):
        path = cfg.root / "output" / candidate
        summary_path = path / "run_summary.json"
        if not summary_path.is_file():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("engineering_status") == "PASS" and summary.get("scientific_status") == "PASS":
            parent_mode, parent, parent_summary = candidate, path, summary
            break
    if parent is None or parent_mode is None or parent_summary is None:
        raise FormalRunBlocked("PRECISION_REQUIRES_ACCEPTED_ADAPT_FULL_OR_FULL")

    progress.stage(1, 6, "Load accepted parent artifacts")
    m1 = joblib.load(parent / "m1.joblib")
    m2 = joblib.load(parent / "m2.joblib")
    m4 = joblib.load(parent / "m4.joblib")
    parent_rankings = pd.read_parquet(parent / "m4_rankings.parquet")
    parent_physical = pd.read_parquet(parent / "metrics" / "m4_physical_screening.parquet")
    parent_keys = parent_rankings[
        ["episode_id", "snapshot_id", "flight_id"]
    ].drop_duplicates()
    maximum_flights = int(cfg.mode("precision").get("max_flights", 200))
    flights = parent_keys[["flight_id"]].drop_duplicates().copy()
    flights["selection_key"] = flights["flight_id"].map(
        lambda value: stable_hash(cfg.compute["random_seed"], "precision", value)
    )
    selected_flights = set(
        flights.sort_values("selection_key", kind="mergesort")
        .head(maximum_flights)["flight_id"]
        .astype(str)
    )
    selected_keys = parent_keys[
        parent_keys["flight_id"].astype(str).isin(selected_flights)
    ][["episode_id", "snapshot_id"]].drop_duplicates()
    if selected_keys.empty:
        raise FormalRunBlocked("PRECISION_COHORT_EMPTY")

    progress.stage(2, 6, "Load PRE and frozen precision cohort")
    if pre_output is not None:
        resolved_pre = pre_output.resolve()
    else:
        raw = Path(cfg.scientific.get("paths", {}).get("pre_output", "../pre/output"))
        base = (cfg.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        candidate = base / parent_mode
        resolved_pre = candidate if candidate.exists() else base
    bundle = load_pre_bundle(resolved_pre, cfg.scientific, require_acceptance=True)
    tables = normalize_bundle(bundle)
    tables["snapshots"] = enrich_snapshots(tables["snapshots"], tables["calibration"])
    tables["snapshots"] = attach_rule_context(tables["snapshots"], tables["rules"])
    model_frame, _, _, _ = prepare_model_frame(
        tables["snapshots"], tables["episodes"], cfg.scientific
    )
    frame = model_frame.merge(
        selected_keys,
        on=["episode_id", "snapshot_id"],
        how="inner",
        validate="one_to_one",
    ).reset_index(drop=True)
    frame = set_model_attrs(
        frame,
        list(m1.feature_columns),
        list(m1.numeric_columns),
        list(m1.categorical_columns),
    )
    if len(frame) != len(selected_keys):
        raise FormalRunBlocked(
            f"PRECISION_PRE_KEY_COVERAGE_MISMATCH:{len(frame)}!={len(selected_keys)}"
        )

    progress.stage(3, 6, "Run higher-budget M1-M4 scoring")
    n_samples = int(cfg.mode("precision")["formal_samples"])
    prediction = m1.predict_distribution(frame, n_samples, int(cfg.compute["random_seed"]))
    m2_result = m2.reconstruct(frame, prediction["samples"])
    actions = load_actions(cfg.scientific)
    precision_m3 = generate_m3_library(
        actions, n_samples, int(cfg.compute["random_seed"]), cfg.scientific
    )
    key_set = set(zip(frame["episode_id"].astype(str), frame["snapshot_id"].astype(str)))
    physical = parent_physical[
        [
            (str(episode), str(snapshot)) in key_set
            for episode, snapshot in zip(
                parent_physical["episode_id"], parent_physical["snapshot_id"]
            )
        ]
    ].copy()
    expected_physical = len(frame) * len(actions)
    if len(physical) != expected_physical:
        raise FormalRunBlocked(
            f"PRECISION_PHYSICAL_AUDIT_INCOMPLETE:{len(physical)}!={expected_physical}"
        )
    frozen_rank = parent_rankings[
        [
            (str(episode), str(snapshot)) in key_set
            for episode, snapshot in zip(
                parent_rankings["episode_id"], parent_rankings["snapshot_id"]
            )
        ]
    ].copy()
    frozen_actions = {
        (str(key[0]), str(key[1])): set(group["action_id"].astype(str))
        for key, group in frozen_rank.groupby(["episode_id", "snapshot_id"], sort=False)
    }
    action_scores, precision_rankings, candidates = evaluate_m4(
        frame,
        m2_result["costs_rmb"],
        physical,
        actions,
        precision_m3,
        m4,
        frozen_evaluation_actions=frozen_actions,
    )
    parent_action_keys = set(zip(
        frozen_rank["episode_id"].astype(str),
        frozen_rank["snapshot_id"].astype(str),
        frozen_rank["action_id"].astype(str),
    ))
    precision_action_keys = set(zip(
        precision_rankings["episode_id"].astype(str),
        precision_rankings["snapshot_id"].astype(str),
        precision_rankings["action_id"].astype(str),
    ))
    if parent_action_keys != precision_action_keys:
        raise FormalRunBlocked("PRECISION_ACTION_SET_CHANGED")

    progress.stage(4, 6, "Compute numerical convergence")
    action_comparison, precision_summary = precision_metrics(
        frozen_rank, precision_rankings
    )
    decision = evaluate_precision_audit(precision_summary, cfg.acceptance)
    progress.stage(5, 6, "Publish precision artifacts")
    target = cfg.root / "output" / "precision"
    prepare_empty_publish_target(target)
    target.mkdir(parents=True, exist_ok=True)
    for frame_value, name in (
        (action_scores, "m4_action_scores.parquet"),
        (candidates, "m4_candidate_screen.parquet"),
        (precision_rankings, "m4_rankings.parquet"),
        (action_comparison, "action_comparison.parquet"),
        (precision_summary, "precision_summary.parquet"),
        (decision.checks, "audit.parquet"),
        (precision_m3.parameter_table, "m3_response_parameters.parquet"),
    ):
        write_frame(frame_value, target / name)
    write_json(target / "run_summary.json", {
        "run_id": run_id("precision", cfg.config_hash, cfg.root),
        "mode": "precision",
        "parent_mode": parent_mode,
        "parent_run_id": parent_summary.get("run_id"),
        "engineering_status": "PASS" if not decision.failures else "FAIL",
        "scientific_status": decision.final_status,
        "blocking_reasons": decision.failures,
        "warning_reasons": decision.warnings,
        "formal_samples": n_samples,
        "frozen_snapshot_count": len(frame),
        "frozen_action_count": len(precision_rankings),
        "m3_parameter_hash": precision_m3.parameter_hash,
        "m3_sample_hash": precision_m3.sample_hash,
        "completed_at": pd.Timestamp.now(tz="UTC"),
    })
    dump_config_snapshot(cfg, target)
    progress.stage(6, 6, "Precision complete")
    progress.summary(f"{decision.final_status}: {target}")
    return target
