from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .pipeline_common import (
    PROJECT,
    ROOT,
    _Heartbeat,
    _seed,
    load_common_passenger_cohort,
    run_ordered_thread_tasks,
    stable_hash,
)


def _load(mode: str, override: Path | None = None) -> dict[str, Any]:
    cfg = yaml.safe_load((ROOT / "config" / "v3.yaml").read_text(encoding="utf-8"))
    if override:
        path = override if override.is_absolute() else ROOT / override
        cfg.update(yaml.safe_load(path.read_text(encoding="utf-8")))
    cfg["mode"] = mode
    compute_mode = "full" if mode == "adapt_full" else mode
    cfg["upstream"] = PROJECT / "overall_run" / "output" / mode
    cfg["output"] = ROOT / "output" / mode
    cfg["draws"] = int(cfg[f"benchmark_draws_{compute_mode}"])
    cfg["bootstrap"] = int(cfg[f"bootstrap_{compute_mode}"])
    cfg["config_hash"] = stable_hash({k: v for k, v in cfg.items() if k not in {"upstream", "output", "config_hash"}})
    return cfg


def _upstream(cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    cohort, audit = load_common_passenger_cohort(PROJECT, cfg["mode"])
    required = [
        "run_summary.json",
        "artifact_registry.json",
        "metrics/m1_predictions_evaluation.parquet",
        "metrics/m2_summary.parquet",
        "metrics/m3_audit.parquet",
        "m4_action_scores.parquet",
        "m4_recommendations.parquet",
    ]
    missing = [name for name in required if not (cfg["upstream"] / name).exists()]
    if missing:
        raise FileNotFoundError("UNIFIED_UPSTREAM_ARTIFACT_MISSING:" + ",".join(missing))
    return cohort, audit


def _decisions(scores: pd.DataFrame, recommendations: pd.DataFrame, cohort: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = set(cohort["snapshot_id"].astype(str))
    scores = scores[scores["snapshot_id"].astype(str).isin(keys)].copy()
    recommendations = recommendations[recommendations["snapshot_id"].astype(str).isin(keys)].copy()
    # channel_contribution_F is the F-channel share of the formal total-cost
    # mean-CVaR score and already includes F implementation cost exactly once.
    scores["local_f_score"] = pd.to_numeric(
        scores["channel_contribution_F"], errors="coerce"
    )
    local = scores.loc[
        scores.groupby("snapshot_id", sort=False, observed=True)["local_f_score"].idxmin(),
        ["snapshot_id", "action_id", "local_f_score"],
    ].rename(columns={"action_id": "selected_action", "local_f_score": "policy_score"})
    local["policy_id"] = "LOCAL_F"
    global_policy = recommendations[
        ["snapshot_id", "action_id", "score"]
    ].rename(columns={"action_id": "selected_action", "score": "policy_score"})
    global_policy["policy_id"] = "GLOBAL_FPR"
    decisions = pd.concat([local, global_policy], ignore_index=True)
    decisions = decisions.merge(
        cohort[
            [
                "snapshot_id",
                "recovery_case_id",
                "recovery_event_id",
                "anchor_date",
                "airport_id",
                "snapshot_stage",
            ]
        ],
        on="snapshot_id",
        validate="many_to_one",
    )
    if decisions.groupby("policy_id", observed=True)["recovery_case_id"].nunique().nunique() != 1:
        raise ValueError("COMMON_SUPPORT_COHORT_MISMATCH")
    return scores, decisions


def _benchmark(
    scores: pd.DataFrame,
    cohort: pd.DataFrame,
    cfg: dict[str, Any],
    heartbeat: _Heartbeat | None = None,
    outer_workers: int = 1,
) -> pd.DataFrame:
    metadata = cohort[
        ["snapshot_id", "recovery_case_id", "recovery_event_id", "anchor_date"]
    ]
    source = scores.merge(metadata, on="snapshot_id", validate="many_to_one").reset_index(drop=True)
    draws = int(cfg["draws"])
    total = len(source) * draws
    numeric = {
        "airport_resource_loss": np.empty(total, dtype=float),
        "aircraft_sequence_loss": np.empty(total, dtype=float),
        "passenger_handling_loss": np.empty(total, dtype=float),
        "implementation_cost": np.empty(total, dtype=float),
        "total_loss": np.empty(total, dtype=float),
    }
    records = list(source.itertuples(index=False))

    def compute_row(task_id: str) -> dict[str, np.ndarray]:
        row_index = int(task_id)
        record = records[row_index]
        components = {
            channel: max(float(getattr(record, f"expected_component_{channel}")), 0.0)
            for channel in ("F", "P", "R")
        }
        burden = max(float(record.secondary_burden), 0.0)
        row_values = {name: np.empty(draws, dtype=float) for name in numeric}
        for draw in range(draws):
            rng = np.random.default_rng(_seed(cfg["base_seed"], record.snapshot_id, record.action_id, draw))
            losses = {
                channel: value * float(np.exp(0.12 * rng.normal() - 0.5 * 0.12**2))
                for channel, value in components.items()
            }
            implementation = burden * max(0.0, 1.0 + 0.05 * float(rng.normal()))
            row_values["airport_resource_loss"][draw] = losses["R"]
            row_values["aircraft_sequence_loss"][draw] = losses["F"]
            row_values["passenger_handling_loss"][draw] = losses["P"]
            row_values["implementation_cost"][draw] = implementation
            row_values["total_loss"][draw] = sum(losses.values())
        return row_values

    if outer_workers > 1 and len(records) > 1:
        computed_rows = run_ordered_thread_tasks(
            [str(index) for index in range(len(records))],
            compute_row,
            outer_workers,
        )
        for row_index, row_values in enumerate(computed_rows):
            start = row_index * draws
            for name, values in row_values.items():
                numeric[name][start : start + draws] = values
            if heartbeat is not None:
                heartbeat.tick("benchmark", "LOCAL_F/GLOBAL_FPR", (row_index + 1) * draws)
    else:
        for row_index in range(len(records)):
            row_values = compute_row(str(row_index))
            start = row_index * draws
            for name, values in row_values.items():
                numeric[name][start : start + draws] = values
            if heartbeat is not None:
                heartbeat.tick("benchmark", "LOCAL_F/GLOBAL_FPR", (row_index + 1) * draws)
    result = pd.DataFrame({
        "recovery_event_id": np.repeat(source["recovery_event_id"].to_numpy(), draws),
        "recovery_case_id": np.repeat(source["recovery_case_id"].to_numpy(), draws),
        "snapshot_id": np.repeat(source["snapshot_id"].to_numpy(), draws),
        "anchor_date": np.repeat(source["anchor_date"].to_numpy(), draws),
        "airport_id": np.repeat(source["airport"].to_numpy(), draws),
        "snapshot_stage": np.repeat(source["snapshot_stage"].to_numpy(), draws),
        "action_id": np.repeat(source["action_id"].to_numpy(), draws),
        "benchmark_draw_id": np.tile(np.arange(draws, dtype=np.int32), len(source)),
        **numeric,
    })
    for column in ["recovery_event_id", "recovery_case_id", "snapshot_id", "airport_id", "snapshot_stage", "action_id"]:
        result[column] = result[column].astype("category")
    return result


def _metrics(decisions: pd.DataFrame, benchmark: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    action = benchmark.groupby(["recovery_case_id", "action_id"], as_index=False, observed=True).agg(
        benchmark_loss=("total_loss", "mean"),
        airport_resource_loss=("airport_resource_loss", "mean"),
        aircraft_sequence_loss=("aircraft_sequence_loss", "mean"),
        passenger_handling_loss=("passenger_handling_loss", "mean"),
        implementation_cost=("implementation_cost", "mean"),
    )
    oracle = action.loc[action.groupby("recovery_case_id", observed=True)["benchmark_loss"].idxmin(), [
        "recovery_case_id", "action_id", "benchmark_loss"
    ]].rename(columns={"action_id": "oracle_action", "benchmark_loss": "oracle_loss"})
    a00 = action[action["action_id"].eq("A00")][["recovery_case_id", "benchmark_loss"]].rename(
        columns={"benchmark_loss": "a00_loss"}
    )
    metrics = (
        decisions.merge(
            action,
            left_on=["recovery_case_id", "selected_action"],
            right_on=["recovery_case_id", "action_id"],
            validate="many_to_one",
        )
        .merge(oracle, on="recovery_case_id", validate="many_to_one")
        .merge(a00, on="recovery_case_id", validate="many_to_one")
    )
    metrics["regret"] = (metrics["benchmark_loss"] - metrics["oracle_loss"]).clip(lower=0)
    metrics["harmful_intervention"] = metrics["benchmark_loss"] > metrics["a00_loss"] + 1e-10
    metrics["null_selection"] = metrics["selected_action"].eq("A00")
    paired = metrics.pivot(index="recovery_case_id", columns="policy_id", values="regret").reset_index()
    paired["local_minus_global_regret"] = paired["LOCAL_F"] - paired["GLOBAL_FPR"]
    summary = metrics.groupby("policy_id", as_index=False, observed=True).agg(
        mean_benchmark_loss=("benchmark_loss", "mean"),
        mean_regret=("regret", "mean"),
        worst_decile_regret=("regret", lambda values: float(values[values >= values.quantile(.9)].mean())),
        harmful_intervention_rate=("harmful_intervention", "mean"),
        null_selection_rate=("null_selection", "mean"),
    )
    return metrics, paired, summary


def _bootstrap(
    metrics: pd.DataFrame,
    repetitions: int,
    seed: int,
    heartbeat: _Heartbeat | None = None,
    outer_workers: int = 1,
) -> pd.DataFrame:
    wide = metrics.pivot_table(
        index=["recovery_event_id", "recovery_case_id"], columns="policy_id", values="regret", observed=True
    ).reset_index()
    events = wide["recovery_event_id"].unique()
    def compute_replicate(task_id: str) -> dict[str, Any]:
        replicate = int(task_id)
        rng = np.random.default_rng(_seed(seed, "bootstrap", replicate))
        chosen = rng.choice(events, size=len(events), replace=True)
        sampled = pd.concat([wide[wide["recovery_event_id"].eq(event)] for event in chosen], ignore_index=True)
        return {
            "replicate": replicate,
            "local_minus_global_regret": float((sampled["LOCAL_F"] - sampled["GLOBAL_FPR"]).mean()),
            "recovery_event_count": len(events),
            "recovery_case_count": len(sampled),
        }

    rows = run_ordered_thread_tasks(
        [str(replicate) for replicate in range(repetitions)],
        compute_replicate,
        outer_workers,
    )
    if heartbeat is not None:
        heartbeat.tick("bootstrap", "LOCAL_F/GLOBAL_FPR", repetitions, force=True)
    return pd.DataFrame(rows)


