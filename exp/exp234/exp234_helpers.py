"""Exp234 pure helpers (mechanical extraction from development_execution.py).

Frozen M3 structural template map and small numeric/utility helpers shared by
the Exp234 development executor and the Exp3.7 LLM audit V2. No scientific
logic lives here beyond the frozen template map.
"""
from __future__ import annotations

import json

from exp.exp2.metrics import (
    action_gap_distortion,
    pairwise_ranking_reversal_rate,
    ranking_at_3_overlap,
    reference_objective_selection_penalty,
    top1_disagreement,
)
from model.M3.response import action_post_consequences

FULL_SCOPE = ("F_continuity", "F_execution", "F_propagation", "P_time", "R_operating")
FLIGHT_SCOPE = ("F_continuity", "F_execution", "F_propagation")

FULL_SCOPE = ("F_continuity", "F_execution", "F_propagation", "P_time", "R_operating")
FLIGHT_SCOPE = ("F_continuity", "F_execution", "F_propagation")
def _action_map_from_pre(candidates, pre_rows, rho_table: dict[str, list[float]],
                         scope: tuple[str, ...]) -> dict:
    weights = [row["scenario_weight"] for row in pre_rows]
    action_map = {}
    for candidate in candidates:
        values = [
            _post_scope(pre_rows[index], candidate, rho_table[candidate.template_id][index], scope)
            for index in range(len(pre_rows))
        ]
        action_map[candidate.template_id] = _distributional(values, weights)
    return action_map
def _post_scope(pre: dict, candidate, rho: float, scope: tuple[str, ...]) -> float | None:
    """Post-action CU over a scope for one scenario (None when a parent abstains)."""
    pre_by_component = {name: pre["components"].get(name) for name in scope}
    if any(value is None for value in pre_by_component.values()):
        return None
    post = action_post_consequences(
        pre_by_component=pre_by_component,
        mitigation=candidate.mitigation,
        induced=candidate.induced,
        rho=rho,
        induced_score_to_cu=0.10,
        included_components=scope,
    )
    return float(sum(post.values()))
def _distributional(values: list[float | None], weights: list[float]) -> float | None:
    if any(value is None for value in values):
        return None
    return float(sum(weight * value for value, weight in zip(values, weights)))
def _component_means(pre_rows: list[dict]) -> dict[str, float | None]:
    means = {}
    for name in FULL_SCOPE:
        values = [row["components"].get(name) for row in pre_rows]
        means[name] = None if any(value is None for value in values) else float(
            sum(values) / len(values)
        )
    return means
def _mean_metrics(reference: dict[str, float], variant: dict[str, float]) -> dict:
    return {
        "action_gap_distortion": action_gap_distortion(reference, variant),
        "pairwise_ranking_reversal_rate": pairwise_ranking_reversal_rate(reference, variant),
        "top1_disagreement": top1_disagreement(reference, variant),
        "ranking_at_3_overlap": ranking_at_3_overlap(reference, variant),
        "reference_objective_selection_penalty": reference_objective_selection_penalty(
            reference, variant
        ),
    }
def _flatten_rows(rows: list[dict]) -> dict[str, list]:
    """Flatten per-node rows into parquet columns (nested maps as JSON text)."""
    columns: dict[str, list] = {}
    for row in rows:
        for name, value in row.items():
            columns.setdefault(name, []).append(
                json.dumps(value, sort_keys=True)
                if isinstance(value, dict) else value
            )
    return columns
def _mean_of_optionals(values: list[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    return None if not present else sum(present) / len(present)
def _spread(components: dict[str, float | None]) -> float | None:
    values = [value for value in components.values() if value is not None]
    return None if not values else max(values) - min(values)
_ACTION_META = {
    "A00": ("null", 0, ()),
    "A11": ("timing_passenger_coordination", 5, ("FLIGHT", "PAX")),
    "A13": ("flight_execution", 5, ("FLIGHT",)),
    "A21": ("timing", 10, ("FLIGHT",)),
    "A22": ("capacity_coordination", 15, ("ATFM",)),
    "A23": ("capacity_coordination", 10, ("ATFM",)),
    "A31": ("passenger_recovery", 10, ("PAX",)),
    "A32": ("passenger_recovery", 5, ("PAX", "GROUND")),
    "A33": ("passenger_service", 0, ("PAX",)),
    "A41": ("ground_recovery", 10, ("GROUND",)),
    "A42": ("ground_recovery", 10, ("GROUND",)),
    "A43": ("ground_recovery", 20, ("GROUND",)),
    "A51": ("aircraft_recovery", 30, ("AIRCRAFT",)),
    "A52": ("aircraft_recovery", 30, ("AIRCRAFT",)),
    "A53": ("aircraft_recovery", 45, ("AIRCRAFT",)),
    "A54": ("aircraft_recovery", 45, ("AIRCRAFT",)),
    "A55": ("aircraft_recovery", 60, ("AIRCRAFT",)),
    "A61": ("crew_recovery", 20, ("CREW",)),
    "A62": ("crew_recovery", 30, ("CREW",)),
    "A63": ("crew_recovery", 45, ("CREW",)),
    "A64": ("crew_recovery", 30, ("CREW",)),
    "A71": ("extreme_local_network", 10, ("NETWORK", "CANCEL")),
    "A72": ("extreme_local_network", 15, ("NETWORK", "CANCEL")),
}
def _action_family(template_id: str) -> str:
    return _ACTION_META.get(template_id, ("", 0, ()))[0]
def _preparation(template_id: str) -> float:
    return _ACTION_META.get(template_id, ("", 0, ()))[1]
def _authority(template_id: str) -> list[str]:
    return list(_ACTION_META.get(template_id, ("", 0, ()))[2])
