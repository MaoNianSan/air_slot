"""Exp1 full-Development STATE metrics from M1 scenarios and post-outcome labels.

Implements OUTPUT_CONTRACT_20260823 Exp1 STATE metric definitions using the
frozen scenario envelope (exp.common.full_development_scenarios) and the
separate post-outcome labels artifact.  Decision-level metrics remain NOT_RUN
until the shared M4 mapping/replay gate is frozen; event-threshold metrics
remain NOT_RUN until a frozen delay-event definition exists.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable, Mapping

from exp.common.bootstrap import episode_bootstrap
from exp.common.metrics_v2 import crps_from_samples
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus

M4_GATE_REASON = "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE"
M1_PREDICTIVE_REASON = "M1_V2_PREDICTIVE_OUTPUT_REQUIRED"
DELAY_EVENT_REASON = "FROZEN_DELAY_EVENT_DEFINITION_REQUIRED"

PRIMITIVE_SCENARIO_COLUMNS = {
    "R_IB": "T_IB_A00",
    "DeltaOB": "D_OB",
    "T_TX": "D_TX",
}
PRIMITIVE_LABEL_NAMES = {
    "R_IB": "T_IB_REMAINING_HAZARD",
    "DeltaOB": "D_OB",
    "T_TX": "D_TX",
}
BOOTSTRAP_REPLICATES = 2000


def _label_map(label_rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for row in label_rows:
        if not row.get("active", True):
            continue
        node = f"{row.get('episode_id')}::{row.get('decision_node_id')}"
        value = row.get("value")
        if value is None:
            continue
        values.setdefault(node, {})[str(row.get("target_name"))] = float(value)
    return values


def _not_run(metric_id: str, level: MetricLevel, unit: str, reason: str) -> MetricObservation:
    return MetricObservation(
        metric_id=metric_id, level=level, value=None, unit=unit,
        support_status=SupportStatus.NOT_RUN, metadata={"reason": reason},
    )


def compute_full_state_metrics(
    *,
    scenario_rows: Iterable[Mapping[str, Any]],
    label_rows: Iterable[Mapping[str, Any]],
    variants: tuple[str, ...],
    seed: int = 0,
) -> dict[str, dict[str, MetricObservation]]:
    """STATE metrics per variant from scenario draws and observed labels.

    CRPS_PRIMITIVE_TARGET aggregates node-level CRPS per primitive with an
    episode-cluster bootstrap (replicates=2000, seed recorded).  The derived
    D_TO primitive uses D_OB + D_TX only where both are supported.
    """
    scenario_rows = tuple(scenario_rows)
    labels = _label_map(label_rows)
    by_node: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in scenario_rows:
        by_node[f"{row.get('episode_id')}::{row.get('decision_node_id')}"].append(row)

    crps_rows: dict[str, list[dict[str, Any]]] = {}
    node_counts: dict[str, int] = {}
    for primitive in PRIMITIVE_SCENARIO_COLUMNS:
        crps_rows[primitive] = []
        node_counts[primitive] = 0
    crps_rows["D_TO"] = []
    node_counts["D_TO"] = 0

    for node, rows in sorted(by_node.items()):
        episode_id = str(rows[0].get("episode_id"))
        observed = labels.get(node, {})
        for primitive, column in PRIMITIVE_SCENARIO_COLUMNS.items():
            observed_value = observed.get(PRIMITIVE_LABEL_NAMES[primitive])
            samples = [float(row[column]) for row in rows if row.get(column) is not None]
            if not samples or observed_value is None:
                continue
            crps_rows[primitive].append({
                "episode_id": episode_id,
                "crps": crps_from_samples(samples, observed_value),
            })
            node_counts[primitive] += 1
        d_ob, d_tx = observed.get("D_OB"), observed.get("D_TX")
        if d_ob is not None and d_tx is not None:
            samples_d_to = [
                float(row["D_OB"]) + float(row["D_TX"])
                for row in rows
                if row.get("D_OB") is not None and row.get("D_TX") is not None
            ]
            if samples_d_to:
                crps_rows["D_TO"].append({
                    "episode_id": episode_id,
                    "crps": crps_from_samples(samples_d_to, d_ob + d_tx),
                })
                node_counts["D_TO"] += 1

    per_primitive_mean: dict[str, float] = {}
    bootstrap: dict[str, Any] | None = None
    flat_rows: list[dict[str, Any]] = []
    for primitive in ("R_IB", "DeltaOB", "T_TX", "D_TO"):
        if crps_rows[primitive]:
            per_primitive_mean[primitive] = mean(
                float(item["crps"]) for item in crps_rows[primitive]
            )
            flat_rows.extend(crps_rows[primitive])

    observations: dict[str, dict[str, MetricObservation]] = {}
    for variant in variants:
        metrics: dict[str, MetricObservation] = {}
        if flat_rows:
            bootstrap = episode_bootstrap(
                flat_rows, "crps", replicates=BOOTSTRAP_REPLICATES, seed=seed,
            )
            metrics["CRPS_PRIMITIVE_TARGET"] = MetricObservation(
                metric_id="CRPS_PRIMITIVE_TARGET", level=MetricLevel.STATE,
                value=bootstrap.estimate, unit="minutes",
                support_status=SupportStatus.SUPPORTED,
                metadata={
                    "primitive_scope": "R_IB, DeltaOB, T_TX, derived D_TO",
                    "per_primitive_mean": per_primitive_mean,
                    "node_counts": node_counts,
                    "n_episodes": len({item["episode_id"] for item in flat_rows}),
                    "bootstrap": {
                        "method": "episode_bootstrap",
                        "replicates": bootstrap.replicates,
                        "seed": seed,
                        "estimate": bootstrap.estimate,
                        "ci_lower": bootstrap.ci_lower,
                        "ci_upper": bootstrap.ci_upper,
                    },
                },
            )
        else:
            metrics["CRPS_PRIMITIVE_TARGET"] = _not_run(
                "CRPS_PRIMITIVE_TARGET", MetricLevel.STATE, "minutes",
                "NO_SUPPORTED_PRIMITIVE_SAMPLES_OR_LABELS",
            )
        metrics["STATE_REPRESENTATION_DIFFERENCE"] = _not_run(
            "STATE_REPRESENTATION_DIFFERENCE", MetricLevel.STATE, "minutes",
            M1_PREDICTIVE_REASON,
        )
        metrics["BRIER_PRINCIPAL_DELAY_EVENT"] = _not_run(
            "BRIER_PRINCIPAL_DELAY_EVENT", MetricLevel.STATE, "score",
            DELAY_EVENT_REASON,
        )
        metrics["CALIBRATION"] = _not_run(
            "CALIBRATION", MetricLevel.STATE, "absolute_gap", DELAY_EVENT_REASON,
        )
        metrics["COVERAGE"] = _not_run(
            "COVERAGE", MetricLevel.STATE, "rate", DELAY_EVENT_REASON,
        )
        metrics["TOP1_ACTION_DISAGREEMENT"] = _not_run(
            "TOP1_ACTION_DISAGREEMENT", MetricLevel.DECISION, "rate", M4_GATE_REASON,
        )
        metrics["EXPOST_MODEL_IMPLIED_RESIDUAL_RISK"] = _not_run(
            "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", MetricLevel.DECISION,
            "CONSTRUCTED_LOSS_UNIT", M4_GATE_REASON,
        )
        observations[variant] = metrics
    return observations


__all__ = [
    "BOOTSTRAP_REPLICATES",
    "DELAY_EVENT_REASON",
    "M1_PREDICTIVE_REASON",
    "M4_GATE_REASON",
    "compute_full_state_metrics",
]
