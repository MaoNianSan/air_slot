from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .pipeline_common import M2_CONFIGS, MODELS, run_ordered_thread_tasks, stable_hash
from .shared_contracts import (
    build_ranking_prefixes,
    compare_ranking_prefixes,
    full_ranking_from_scores,
)


def _model_ranking_agreement(ranking_prefixes: pd.DataFrame) -> pd.DataFrame:
    prop_prefixes = ranking_prefixes[ranking_prefixes["model_id"].eq("PROP")].drop(
        columns="model_id"
    )
    if prop_prefixes.empty:
        raise ValueError("PART_ADV_PROP_RANKING_MISSING")
    agreement_parts = []
    for model in MODELS:
        candidate_prefixes = ranking_prefixes[
            ranking_prefixes["model_id"].eq(model)
        ].drop(columns="model_id")
        comparison = compare_ranking_prefixes(prop_prefixes, candidate_prefixes)
        comparison["reference_model_id"] = "PROP"
        comparison["model_id"] = model
        comparison["agreement"] = comparison["exact_order_match"]
        agreement_parts.append(comparison)
    return pd.concat(agreement_parts, ignore_index=True)


def _benchmark(cfg: dict[str, Any], cohort: pd.DataFrame) -> pd.DataFrame:
    keys = set(cohort["snapshot_id"].astype(str))
    scores = pd.read_parquet(cfg["upstream"] / "m4_action_scores.parquet")
    scores = scores[scores["snapshot_id"].astype(str).isin(keys)].copy()
    return scores[["snapshot_id", "action_id", "total_score"]].rename(
        columns={"snapshot_id": "recovery_case_id", "total_score": "benchmark_loss"}
    )


def _propagate(
    cfg: dict[str, Any],
    predictions: pd.DataFrame,
    samples: pd.DataFrame,
    cohort: pd.DataFrame,
    benchmark: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    m2 = pd.read_parquet(cfg["upstream"] / "metrics" / "m2_summary.parquet")
    m2 = m2[m2["snapshot_id"].isin(cohort["snapshot_id"])].set_index("snapshot_id")
    action_scores = pd.read_parquet(cfg["upstream"] / "m4_action_scores.parquet")
    action_scores = action_scores[
        action_scores["snapshot_id"].isin(cohort["snapshot_id"])
    ].copy()
    prop_mean = predictions[predictions["model_id"].eq("PROP")].set_index(
        "snapshot_id"
    )["predictive_mean"]
    oracle = benchmark.loc[
        benchmark.groupby("recovery_case_id", observed=True)["benchmark_loss"].idxmin(),
        ["recovery_case_id", "benchmark_loss"],
    ].rename(columns={"benchmark_loss": "oracle_loss"})
    downstream_parts, propagation_rows, path_parts, cost_parts = [], [], [], []
    ranking_parts: list[pd.DataFrame] = []
    model_state: dict[str, dict[str, pd.Series]] = {}
    for model in MODELS:
        prediction = (
            predictions[predictions["model_id"].eq(model)]
            .copy()
            .sort_values("snapshot_id")
        )
        model_samples = samples[samples["model_id"].eq(model)].copy()
        mean = prediction.set_index("snapshot_id")["predictive_mean"]
        scale = ((mean.clip(lower=0) + 15.0) / (prop_mean.clip(lower=0) + 15.0)).clip(
            0.25, 4.0
        )
        trigger = prediction.set_index("snapshot_id")["trigger_decision"].astype(bool)
        scenario = model_samples.copy()
        scenario["recovery_case_id"] = scenario["snapshot_id"]
        # Vectorized: groupby mean per case instead of O(n²) map+loc lambda
        case_sample_mean = scenario.groupby("recovery_case_id", observed=True)[
            "sample_value"
        ].transform("mean")
        case_prop_mean = scenario["recovery_case_id"].map(prop_mean).fillna(0)
        scenario["scale"] = (
            (case_sample_mean.clip(lower=0) + 15.0)
            / (case_prop_mean.clip(lower=0) + 15.0)
        ).clip(0.25, 4.0)
        scenario["trigger"] = (
            scenario["recovery_case_id"].map(trigger).fillna(False).astype(bool)
        )
        for channel in ("F", "P", "R"):
            base = scenario["recovery_case_id"].map(m2[f"loss_mean_{channel}"])
            scenario[f"{channel}_cost"] = (
                base * scenario["scale"] * scenario["trigger"].astype(float)
            )
        scenario["total_cost"] = scenario[
            [f"{channel}_cost" for channel in ("F", "P", "R")]
        ].sum(axis=1)
        cost_parts.append(scenario.assign(model_id=model))

        candidate = action_scores.copy()
        candidate["scale"] = candidate["snapshot_id"].map(scale)
        candidate["trigger"] = (
            candidate["snapshot_id"].map(trigger).fillna(False).astype(bool)
        )
        candidate = candidate[candidate["trigger"] | candidate["action_id"].eq("A00")]
        candidate["adjusted_score"] = (
            candidate["channel_contribution_F"] + candidate["channel_contribution_P"]
        ) * candidate["scale"] + candidate["channel_contribution_R"]
        full_ranking = full_ranking_from_scores(candidate, "adjusted_score")
        model_prefixes, _ = build_ranking_prefixes(
            cohort[["episode_id", "snapshot_id"]].drop_duplicates(),
            full_ranking,
        )
        model_prefixes["model_id"] = model
        ranking_parts.append(model_prefixes)
        selected = model_prefixes[
            model_prefixes["ranking_k"].eq(1)
            & ~model_prefixes["is_padding"].fillna(False).astype(bool)
        ][["snapshot_id", "action_id", "score"]].rename(
            columns={
                "snapshot_id": "recovery_case_id",
                "action_id": "selected_action",
                "score": "adjusted_score",
            }
        )
        selected = selected.merge(
            benchmark,
            left_on=["recovery_case_id", "selected_action"],
            right_on=["recovery_case_id", "action_id"],
            validate="one_to_one",
        ).merge(oracle, on="recovery_case_id", validate="many_to_one")
        selected["regret"] = (
            selected["benchmark_loss"] - selected["oracle_loss"]
        ).clip(lower=0)
        selected["model_id"] = model
        selected["formal_ranking"] = model != "POINT_OOF"
        ordered_actions = {
            str(snapshot_id): group.sort_values(
                ["adjusted_score", "expected_implementation_cost_rmb", "priority", "action_id"],
                kind="mergesort",
            )["action_id"].astype(str).tolist()
            for snapshot_id, group in candidate.groupby("snapshot_id", sort=False, observed=True)
        }
        downstream_parts.append(selected)
        detail = (
            prediction[["snapshot_id", "trigger_probability", "trigger_decision"]]
            .rename(columns={"snapshot_id": "recovery_case_id"})
            .merge(
                selected[["recovery_case_id", "selected_action", "regret"]],
                on="recovery_case_id",
            )
        )
        detail["model_id"] = model
        path_parts.append(detail)
        prediction_hash = stable_hash(
            prediction[
                [
                    "snapshot_id",
                    "predictive_mean",
                    "trigger_probability",
                    "trigger_decision",
                ]
            ].to_dict("records")
        )
        scenario_hash = stable_hash(
            scenario.sort_values(["recovery_case_id", "sample_id"])[
                ["recovery_case_id", "sample_id", "sample_value"]
            ].to_dict("records")
        )
        m2_hash = stable_hash(
            scenario.sort_values(["recovery_case_id", "sample_id"])[
                [
                    "recovery_case_id",
                    "sample_id",
                    "F_cost",
                    "P_cost",
                    "R_cost",
                    "total_cost",
                ]
            ].to_dict("records")
        )
        recommendation_hash = stable_hash(
            selected.sort_values("recovery_case_id")[
                ["recovery_case_id", "selected_action"]
            ].to_dict("records")
        )
        propagation_rows.append(
            {
                "model_id": model,
                "formal_ranking": model != "POINT_OOF",
                "prediction_hash": prediction_hash,
                "scenario_hash": scenario_hash,
                "m2_cost_hash": m2_hash,
                "recommendation_hash": recommendation_hash,
                "trigger_rate": float(trigger.mean()),
                "scenario_mean": float(scenario["sample_value"].mean()),
                "m2_total_cost_mean": float(scenario["total_cost"].mean()),
                "non_a00_rate": float(selected["selected_action"].ne("A00").mean()),
                "mean_regret": float(selected["regret"].mean()),
            }
        )
        model_state[model] = {
            "trigger": trigger,
            "severity": scenario.groupby("recovery_case_id", observed=True)[
                "sample_value"
            ].mean(),
            "cost": scenario.groupby("recovery_case_id", observed=True)[
                "total_cost"
            ].mean(),
            "action": selected.set_index("recovery_case_id")["selected_action"],
            "regret": selected.set_index("recovery_case_id")["regret"],
            "ranking": ordered_actions,
        }
    pair_rows = []
    for left_index, left in enumerate(MODELS):
        for right in MODELS[left_index + 1 :]:
            lstate, rstate = model_state[left], model_state[right]
            for ranking_k in (1, 2, 3, 5):
                ordered_flags = []
                set_flags = []
                order_only_flags = []
                for case_id in sorted(set(lstate["ranking"]) & set(rstate["ranking"])):
                    left_rank = lstate["ranking"][case_id][:ranking_k]
                    right_rank = rstate["ranking"][case_id][:ranking_k]
                    left_rank += [None] * max(0, ranking_k - len(left_rank))
                    right_rank += [None] * max(0, ranking_k - len(right_rank))
                    same_order = left_rank == right_rank
                    same_set = {x for x in left_rank if x is not None} == {x for x in right_rank if x is not None}
                    ordered_flags.append(not same_order)
                    set_flags.append(not same_set)
                    order_only_flags.append(same_set and not same_order)
                pair_rows.append({
                    "left_model": left,
                    "right_model": right,
                    "ranking_k": ranking_k,
                    "trigger_disagreement_rate": float(
                        (lstate["trigger"] != rstate["trigger"]).mean()
                    ),
                    "mean_abs_scenario_difference": float(
                        (lstate["severity"] - rstate["severity"]).abs().mean()
                    ),
                    "mean_abs_m2_cost_difference": float(
                        (lstate["cost"] - rstate["cost"]).abs().mean()
                    ),
                    "recommendation_disagreement_rate": float(
                        (lstate["action"] != rstate["action"]).mean()
                    ),
                    "lead_action_disagreement_rate": float(
                        (lstate["action"] != rstate["action"]).mean()
                    ),
                    "ordered_disagreement_rate": float(np.mean(ordered_flags)) if ordered_flags else np.nan,
                    "set_disagreement_rate": float(np.mean(set_flags)) if set_flags else np.nan,
                    "order_only_disagreement_rate": float(np.mean(order_only_flags)) if order_only_flags else np.nan,
                    "mean_regret_difference_left_minus_right": float(
                        (lstate["regret"] - rstate["regret"]).mean()
                    ),
                }
            )
    ranking_prefixes = pd.concat(ranking_parts, ignore_index=True)
    agreement = _model_ranking_agreement(ranking_prefixes)
    return (
        pd.concat(downstream_parts, ignore_index=True),
        pd.DataFrame(propagation_rows),
        pd.concat(path_parts, ignore_index=True),
        pd.DataFrame(pair_rows),
        pd.concat(cost_parts, ignore_index=True),
        ranking_prefixes,
        agreement,
    )


def _m2_sensitivity(
    cfg: dict[str, Any], cohort: pd.DataFrame, outer_workers: int = 1
) -> pd.DataFrame:
    base = pd.read_parquet(cfg["upstream"] / "metrics" / "m2_summary.parquet")
    base = base[base["snapshot_id"].isin(cohort["snapshot_id"])].set_index(
        "snapshot_id"
    )
    scores = pd.read_parquet(cfg["upstream"] / "m4_action_scores.parquet")
    scores = scores[scores["snapshot_id"].isin(cohort["snapshot_id"])].copy()
    factors = {
        "DAG_BASE": (1.0, 1.0, 1.0),
        "ADD_BASE": (1.0, 1.0, 0.9),
        "SCOPE_LOW": (0.8, 0.8, 0.8),
        "SCOPE_HIGH": (1.2, 1.2, 1.2),
        "SEQUENCE_LOW": (0.8, 1.0, 1.0),
        "SEQUENCE_HIGH": (1.2, 1.0, 1.0),
        "PASSENGER_LOW": (1.0, 0.8, 1.0),
        "PASSENGER_HIGH": (1.0, 1.2, 1.0),
        "AIRPORT_HEAVY": (1.0, 1.0, 1.5),
        "SEQUENCE_HEAVY": (1.5, 1.0, 1.0),
        "PASSENGER_HEAVY": (1.0, 1.5, 1.0),
    }

    def compute_configuration(configuration: str) -> list[dict[str, Any]]:
        factor_f, factor_p, factor_r = factors[configuration]
        work = scores.copy()
        work["variant_score"] = (
            work["channel_contribution_F"] * factor_f
            + work["channel_contribution_P"] * factor_p
            + work["channel_contribution_R"] * factor_r
        )
        selected = work.loc[
            work.groupby("snapshot_id", observed=True)["variant_score"].idxmin()
        ]
        configuration_rows = []
        for record in selected.itertuples(index=False):
            configuration_rows.append(
                {
                    "configuration": configuration,
                    "recovery_case_id": record.snapshot_id,
                    "action_id": record.action_id,
                    "post_cost": record.variant_score,
                    "mean_pre_cost": float(
                        base.loc[
                            record.snapshot_id,
                            ["loss_mean_F", "loss_mean_P", "loss_mean_R"],
                        ].sum()
                    ),
                }
            )
        return configuration_rows

    blocks = run_ordered_thread_tasks(
        list(factors), compute_configuration, outer_workers
    )
    rows = [row for block in blocks for row in block]
    return pd.DataFrame(rows)


def _m4_variants(
    cfg: dict[str, Any],
    cohort: pd.DataFrame,
    benchmark: pd.DataFrame,
    outer_workers: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    action = pd.read_parquet(cfg["upstream"] / "m4_action_scores.parquet")
    action = action[action["snapshot_id"].isin(cohort["snapshot_id"])].copy()
    variants = list(cfg["m4"]["variants"])

    def compute_variant(variant: str) -> pd.DataFrame:
        value = cfg["m4"]["variants"][variant]
        work = action.copy()
        work["variant"] = variant
        work["lambda"] = float(value)
        work["score_variant"] = (1 - float(value)) * work["expected_component"] + float(
            value
        ) * work["cvar_component"]
        return work

    rows = run_ordered_thread_tasks(variants, compute_variant, outer_workers)
    scores = pd.concat(rows, ignore_index=True)
    scores = scores.sort_values(
        ["variant", "snapshot_id", "score_variant", "expected_implementation_cost_rmb", "priority", "action_id"],
        kind="mergesort",
    )
    scores["rank_position"] = scores.groupby(["variant", "snapshot_id"], observed=True).cumcount() + 1
    best = scores.loc[
        scores.groupby(["variant", "snapshot_id"], observed=True)[
            "score_variant"
        ].idxmin()
    ].copy()
    best["recovery_case_id"] = best["snapshot_id"]
    oracle = benchmark.loc[
        benchmark.groupby("recovery_case_id", observed=True)["benchmark_loss"].idxmin(),
        ["recovery_case_id", "benchmark_loss"],
    ].rename(columns={"benchmark_loss": "oracle_loss"})
    best = best.merge(
        benchmark,
        left_on=["recovery_case_id", "action_id"],
        right_on=["recovery_case_id", "action_id"],
    ).merge(oracle, on="recovery_case_id")
    best["regret"] = (best["benchmark_loss"] - best["oracle_loss"]).clip(lower=0)
    metrics = best.groupby("variant", as_index=False, observed=True).agg(
        mean_benchmark_regret=("regret", "mean"),
        worst_decile_regret=(
            "regret",
            lambda values: float(values[values >= values.quantile(0.9)].mean()),
        ),
        non_a00_rate=("action_id", lambda values: float(values.ne("A00").mean())),
    )
    return scores, metrics
