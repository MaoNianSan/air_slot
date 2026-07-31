from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from .m1_lineage_contract import (
    AuditStop,
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    MIN_EVENT_CLUSTERS,
    cohort_hash,
    stable_hash,
)


def build_cohort_lineage(context: dict[str, Any], dictionary: pd.DataFrame) -> pd.DataFrame:
    evaluation = context["evaluation"]
    formal = context["predictions"]
    tail = evaluation.loc[context["tail_mask"]]
    formal_episode_hash = cohort_hash(formal["episode_id"].drop_duplicates())
    tail_episode_hash = cohort_hash(tail["episode_id"].drop_duplicates())
    stage_distribution = json.dumps(
        evaluation["snapshot_stage_x" if "snapshot_stage_x" in evaluation else "snapshot_stage"]
        .value_counts().sort_index().astype(int).to_dict(), sort_keys=True
    )
    rows: list[dict[str, Any]] = []
    for spec in dictionary.to_dict("records"):
        is_tail = spec["value_key"] == "tail_coverage90"
        selected = tail if is_tail else evaluation
        event_count = int(selected["trigger_event_group_id"].nunique())
        rows.append(
            {
                "metric_id": spec["metric_id"],
                "run_id": context["run_id"],
                "mode": "fast",
                "split": "test",
                "base_rows": context["base_rows"],
                "eligible_rows": context["base_rows"],
                "evaluation_rows": int(len(selected)),
                "tail_rows": int(len(tail)) if is_tail else 0,
                "episodes": int(selected["episode_id"].nunique()),
                "flights": int(selected["flight_id"].nunique()),
                "snapshots": int(len(selected)),
                "anchor_days": int(selected["anchor_date"].nunique()),
                "recovery_events": event_count,
                "airport_count": int(selected["airport_id"].nunique()),
                "stage_distribution": stage_distribution if not is_tail else json.dumps(
                    selected["snapshot_stage_y" if "snapshot_stage_y" in selected else "snapshot_stage"]
                    .value_counts().sort_index().astype(int).to_dict(), sort_keys=True
                ),
                "passenger_support": int(
                    selected["m4_passenger_input_supported"].fillna(False).astype(bool).sum()
                ),
                "filter_expression": spec["cohort_filter"],
                "outcome_used_in_filter": bool(is_tail),
                "outcome_used_in_weight": bool(spec["outcome_used_in_weight"]),
                "cohort_role": "OUTCOME_SELECTED_DIAGNOSTIC_ONLY" if is_tail else "FORMAL_EVALUATION_COHORT",
                "cohort_hash": context["tail_cohort_hash"] if is_tail else context["formal_cohort_hash"],
                "episode_id_hash": tail_episode_hash if is_tail else formal_episode_hash,
                "snapshot_id_hash": context["tail_cohort_hash"] if is_tail else context["formal_cohort_hash"],
                "support_definition": spec["support_definition"],
            }
        )
    return pd.DataFrame(rows)


def build_metric_version_registry(dictionary: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for spec in dictionary.to_dict("records"):
        components = {
            "formula": spec["formula"],
            "prediction_layer": spec["prediction_layer"],
            "cohort": spec["cohort_filter"],
            "aggregation": spec["aggregation_unit"],
            "threshold": spec["threshold"],
            "bootstrap_unit": spec["bootstrap_unit"],
            "gate_role": spec["gate_role"],
        }
        rows.append(
            {
                "canonical_metric_id": spec["canonical_metric_id"],
                "formula_version": spec["formula_version"],
                **components,
                "definition_hash": stable_hash(components),
                "status": "ACTIVE_CURRENT_FAST" if "HIST" not in spec["canonical_metric_id"] else "ACTIVE_COMPARATOR",
            }
        )
    frame = pd.DataFrame(rows)
    if frame["canonical_metric_id"].duplicated().any() or frame["definition_hash"].duplicated().any():
        raise AuditStop("METRIC_VERSION_NOT_UNIQUE")
    return frame


def build_bootstrap_lineage(context: dict[str, Any], dictionary: pd.DataFrame) -> pd.DataFrame:
    q95 = context["q95_audit"]
    active = {
        "M1_Q95_EMPIRICAL_EXCEEDANCE_V1": (q95["q95_calibration"], 0.05, "ONE_SIDED_95_PERCENT_UPPER"),
        "M1_Q99_EMPIRICAL_EXCEEDANCE_V1": (q95["q99_calibration"], 0.05, "ONE_SIDED_95_PERCENT_UPPER"),
        "M1_TWCRPS_PROP_MINUS_HIST_V1": (q95["comparative"]["twcrps"], 0.0, "TWO_SIDED_95_PERCENT"),
        "M1_PINBALL_Q95_PROP_MINUS_HIST_V1": (q95["comparative"]["q95_pinball"], 0.0, "TWO_SIDED_95_PERCENT"),
        "M1_PINBALL_Q99_PROP_MINUS_HIST_V1": (q95["comparative"]["q99_pinball"], 0.0, "TWO_SIDED_95_PERCENT"),
    }
    rows = []
    for spec in dictionary.to_dict("records"):
        metric_id = spec["metric_id"]
        if metric_id in active:
            result, threshold, ci_type = active[metric_id]
            limited = result.get("support") == "METRIC_SUPPORT_LIMITED"
            rows.append(
                {
                    "metric_id": metric_id,
                    "bootstrap_applicable": True,
                    "point_estimate": float(result["estimate"]),
                    "ci_lower": result.get("ci_lower"),
                    "ci_upper": result.get("ci_upper"),
                    "support_rows": len(context["predictions"]),
                    "support_clusters": int(result["event_clusters"]),
                    "bootstrap_unit": "trigger_event_group_id",
                    "bootstrap_draws_configured": BOOTSTRAP_DRAWS,
                    "bootstrap_draws_executed": 0 if limited else BOOTSTRAP_DRAWS,
                    "seed": BOOTSTRAP_SEED,
                    "seed_namespace": "CORRECTED_Q95_FAST_SUPPORT_AUDIT",
                    "ci_type": ci_type,
                    "threshold": threshold,
                    "status": "METRIC_SUPPORT_LIMITED" if limited else result.get("status", result.get("certification")),
                    "minimum_clusters": MIN_EVENT_CLUSTERS,
                }
            )
        else:
            rows.append(
                {
                    "metric_id": metric_id,
                    "bootstrap_applicable": False,
                    "point_estimate": context["values"][spec["value_key"]],
                    "ci_lower": None,
                    "ci_upper": None,
                    "support_rows": int(context["tail_mask"].sum()) if spec["value_key"] == "tail_coverage90" else len(context["predictions"]),
                    "support_clusters": 0,
                    "bootstrap_unit": "NONE",
                    "bootstrap_draws_configured": 0,
                    "bootstrap_draws_executed": 0,
                    "seed": None,
                    "seed_namespace": "NONE",
                    "ci_type": "NONE",
                    "threshold": spec["threshold"],
                    "status": "NOT_APPLICABLE",
                    "minimum_clusters": 0,
                }
            )
    frame = pd.DataFrame(rows)
    frame["threshold"] = frame["threshold"].map(
        lambda value: None if value is None or pd.isna(value) else str(value)
    )
    return frame


