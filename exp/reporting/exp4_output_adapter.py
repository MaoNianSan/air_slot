"""EXP4 full-Development metrics payload adapter for OUTPUT_CONTRACT_20260823.

The Exp4 global-development metrics payload is keyed by ``data2.baselines``
instead of a top-level ``metrics`` dict.  This module adapts that shape into
registered contract metric rows, variant definitions, and the cohort card.
"""

from __future__ import annotations

from typing import Any, Mapping


LEAD_TIME_POLICY_REASON = (
    "FORMAL_EXP4_GRID_IS_DISTINCT_FROM_M1_MODEL_HORIZON_NO_IMPLICIT_INTERPOLATION"
)
FORMAL_RECOMMENDATION_GATE_REASON = "M4_MAPPING_AND_TAIL_GATED"
E2E_NOT_RUN_REASON = "FAST_CONTRACT_RUN_NO_PIPELINE_TIMINGS"
DATA1_GATE_REASON = "DATA1_M1_PREDICTIVE_LABEL_PATH_UNAVAILABLE_BY_CONTRACT"
DATA1_VARIANT_ID = "DATA1_BOUNDED_SMOKE"


def rows_from_exp4_global_metrics(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Adapt the Exp4 full-Development metrics payload into contract rows."""
    rows: list[dict[str, Any]] = []
    baselines = ((payload.get("data2") or {}).get("baselines") or {})
    data2_episodes = (payload.get("data2") or {}).get("episode_count")
    for baseline_id, entry in baselines.items():
        if not isinstance(entry, dict):
            continue
        mae = entry.get("mae_minutes")
        crps = entry.get("crps_minutes")
        entry_episodes = entry.get("supported_episode_count")
        episodes = entry_episodes if entry_episodes is not None else data2_episodes
        rows.append({
            "experiment": "EXP4", "variant": str(baseline_id),
            "metric_id": "MAE_MINUTES", "value": mae,
            "support": "SUPPORTED" if mae is not None else "NOT_RUN",
            "n_episodes": episodes if mae is not None else None,
            "reason": None if mae is not None else "FAST_CONTRACT_RUN_NO_OBSERVED_TARGET_ARTIFACT",
        })
        rows.append({
            "experiment": "EXP4", "variant": str(baseline_id),
            "metric_id": "CRPS", "value": crps,
            "support": "SUPPORTED" if crps is not None else "NOT_RUN",
            "n_episodes": episodes if crps is not None else None,
            "reason": (
                entry.get("crps_scope")
                if crps is not None
                else (
                    entry.get("crps_scope")
                    or "FAST_CONTRACT_RUN_NO_FROZEN_PREDICTIVE_DISTRIBUTION"
                )
            ),
        })
        rows.append({
            "experiment": "EXP4", "variant": str(baseline_id),
            "metric_id": "LEAD_TIME_CONTRACT", "value": True,
            "support": "SUPPORTED", "n_episodes": episodes,
            "reason": LEAD_TIME_POLICY_REASON,
        })
        rows.append({
            "experiment": "EXP4", "variant": str(baseline_id),
            "metric_id": "FORMAL_RECOMMENDATION_AVAILABILITY", "value": None,
            "support": "NOT_RUN", "reason": FORMAL_RECOMMENDATION_GATE_REASON,
        })
        for metric_id in (
            "E2E_P50_SECONDS", "E2E_P95_SECONDS", "E2E_P99_SECONDS",
            "WITHIN_60S", "WITHIN_120S", "WITHIN_300S",
        ):
            rows.append({
                "experiment": "EXP4", "variant": str(baseline_id),
                "metric_id": metric_id, "value": None,
                "support": "NOT_RUN", "reason": E2E_NOT_RUN_REASON,
            })
    predictive = ((payload.get("data1") or {}).get("predictive_metrics") or {})
    rows.append({
        "experiment": "EXP4", "variant": DATA1_VARIANT_ID,
        "metric_id": "DATA1_DATA2_SEMANTIC_GATE", "value": None,
        "support": "NOT_RUN",
        "reason": predictive.get("reason") or DATA1_GATE_REASON,
    })
    return tuple(rows)


def exp4_variant_definitions(
    variants: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    definitions = {
        variant: {
            "variant_id": variant,
            "subexperiment": "EXP4A",
            "changed_factor": f"baseline={variant}",
            "fixed_factor": ("cohort", "seed", "lead_time_grid", "support_rules"),
            "claim_scope": "DEVELOPMENT_COMPARISON_ONLY",
        }
        for variant in variants
    }
    definitions[DATA1_VARIANT_ID] = {
        "variant_id": DATA1_VARIANT_ID,
        "subexperiment": "EXP4C",
        "changed_factor": "data_environment=data1_2019",
        "fixed_factor": ("non_pooled", "semantic_gate"),
        "claim_scope": "BOUNDED_EXTERNAL_APPLICABILITY_SMOKE_ONLY",
    }
    return definitions


def exp4_cohort(data2: Mapping[str, Any], scenario_count: int) -> dict[str, Any]:
    return {
        "dataset_id": "DATA2",
        "split": data2.get("split", "DEVELOPMENT"),
        "episode_count": data2.get("episode_count", 0),
        "node_count": data2.get("node_count", 0),
        "scenario_count_per_node": scenario_count,
        "seed": 0,
    }
