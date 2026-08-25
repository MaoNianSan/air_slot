"""Global-development metrics adapter for OUTPUT_CONTRACT_20260823.

Adapts ``EXP{N}_FULL_DEVELOPMENT_METRICS.json`` payloads (Exp2/Exp3/Exp4
shapes) into registered contract metric rows and writes the ten-class
artifact set.  Kept separate from ``output_contract`` to hold the module
within the repository size budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from exp.reporting.exp4_output_adapter import (
    exp4_cohort,
    exp4_variant_definitions,
    rows_from_exp4_global_metrics,
)


def rows_from_global_metrics(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Adapt EXP{N}_FULL_DEVELOPMENT_METRICS.json into contract metric rows.

    Registered metric keys are mapped from the global-development payload;
    values that carry an explicit support_status/reason are preserved.
    Unregistered keys fail closed.
    """
    experiment_id = str(payload.get("experiment_id") or payload.get("schema_version", "")).split("_")[0]
    if experiment_id == "EXP4" and not payload.get("metrics"):
        return rows_from_exp4_global_metrics(payload)
    rows: list[dict[str, Any]] = []
    metric_map = {
        "tail_aware_brier": "BRIER",
        "calibration": "CALIBRATION",
        "state_crps": "CRPS",
        "crps": "CRPS",
        "variogram_score": "VARIOGRAM_SCORE",
        "mae_minutes": "MAE_MINUTES",
        "brier": "BRIER",
        "coverage": "COVERAGE",
    }
    for variant_id, entry in (payload.get("metrics") or {}).items():
        if not isinstance(entry, dict):
            continue
        variant_episodes = entry.get("supported_episode_count")
        if "support_status" in entry:
            support = str(entry.get("support_status"))
            if support in {"SUPPORTED", "PARTIAL"}:
                # The variant-level status is informational; the TOP1 decision
                # metric itself remains gated until M3/M4 downstream ranking.
                support = "NOT_RUN"
            rows.append({
                "experiment": experiment_id,
                "variant": variant_id,
                "metric_id": "TOP1_ACTION_DISAGREEMENT",
                "value": None,
                "support": support,
                "n_episodes": variant_episodes,
                "reason": entry.get("reason"),
            })
            continue
        for raw_key, value in entry.items():
            if raw_key in {"supported_node_count", "abstain_node_count", "supported_episode_count"}:
                continue
            metric_id = metric_map.get(raw_key, raw_key)
            row_episodes = variant_episodes
            if isinstance(value, dict):
                if value.get("supported_episodes") is not None:
                    row_episodes = value.get("supported_episodes")
                if "fixed_bin_calibration_gap" in value:
                    rows.append({
                        "experiment": experiment_id,
                        "variant": variant_id,
                        "metric_id": metric_id,
                        "value": value.get("fixed_bin_calibration_gap"),
                        "support": "SUPPORTED",
                        "n_episodes": row_episodes,
                        "reason": None,
                    })
                    continue
                support = str(value.get("support_status", "NOT_RUN"))
                if support == "SUPPORTED_FINITE_TERMS_ONLY":
                    support = "SUPPORTED"
                rows.append({
                    "experiment": experiment_id,
                    "variant": variant_id,
                    "metric_id": metric_id,
                    "value": value.get("value"),
                    "support": support,
                    "n_episodes": row_episodes,
                    "reason": (
                        value.get("reason")
                        or value.get("claim")
                        or value.get("abstain_reason")
                        or "METRICS_DICT_DETAIL_IN_EXP2_FULL_DEVELOPMENT_METRICS_JSON"
                    ),
                })
            else:
                rows.append({
                    "experiment": experiment_id,
                    "variant": variant_id,
                    "metric_id": metric_id,
                    "value": value,
                    "support": "SUPPORTED",
                    "n_episodes": row_episodes,
                    "reason": None,
                })
    return tuple(rows)


def write_from_global_metrics(
    *,
    experiment_id: str,
    output_root: Path,
    metrics_path: Path,
    frozen_hashes: Mapping[str, str],
    root: Path,
    scenario_count: int = 250,
) -> dict[str, Path]:
    """Write the output-contract artifact set from a global-development metrics payload."""
    from exp.reporting.output_contract import write_experiment_artifacts

    payload = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    rows = rows_from_global_metrics(payload)
    if experiment_id == "EXP4" and not payload.get("metrics"):
        data2 = payload.get("data2") or {}
        variants = tuple((data2.get("baselines") or {}).keys())
        definitions = exp4_variant_definitions(variants)
        cohort = exp4_cohort(data2, scenario_count)
    else:
        variants = tuple(payload.get("metrics", {}).keys())
        definitions = {
            variant: {
                "variant_id": variant,
                "subexperiment": variant[:5],
                "changed_factor": variant,
                "fixed_factor": ("cohort", "seed", "support_rules"),
                "claim_scope": "DEVELOPMENT_COMPARISON_ONLY",
            }
            for variant in variants
        }
        cohort = {
            "dataset_id": payload.get("dataset", "DATA2"),
            "split": payload.get("split", "DEVELOPMENT"),
            "episode_count": payload.get("episode_count", 0),
            "node_count": payload.get("node_count", 0),
            "scenario_count_per_node": scenario_count,
            "seed": 0,
        }
    return write_experiment_artifacts(
        experiment_id=experiment_id,
        output_root=output_root,
        metric_rows=rows,
        cohort=cohort,
        variants=variants,
        variant_definitions=definitions,
        frozen_hashes=frozen_hashes,
        config_hash=payload.get("artifact_hash", ""),
        interpretation=(
            f"{experiment_id} global development evidence with explicit "
            "NOT_RUN/BLOCKED/ABSTAIN gates; no zero-fill and no renormalization."
        ),
        claim_scope="DEVELOPMENT_COMPARISON_ONLY",
        limitations=(
            "Metrics with null values carry their gate reason verbatim.",
            "Passenger components stay ABSTAIN/BLOCKED until frozen.",
            "Authoritative ranking stays forbidden at the M4 gate.",
        ),
        omega_insight=(
            "Development evidence supports representation and process "
            "comparisons; operational action value requires the frozen "
            "consequence-to-monetary mapping."
        ),
        root=root,
    )
