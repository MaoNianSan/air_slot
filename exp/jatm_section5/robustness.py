"""Development-only OFAT robustness for Stage-II recovery."""

from __future__ import annotations

from collections.abc import Sequence

from model.M3.stage2 import (
    LAMBDA_GRID,
    LAMBDA_NOMINAL,
    RecoveryPolicy,
    expected_objective,
    solve_recovery,
)
from model.common.decision_contracts import HeadroomSummary
from model.PRE.decision_environment import action_stage_class

from .contracts import ReferenceRecoveryCohort
from .recovery_value import transition_context


LAMBDA_LEVELS = tuple(float(value) for value in LAMBDA_GRID)
TURNAROUND_LEVELS = {"Q10": 34.0, "Q20": 41.0, "Q30": 47.0}
U_MAX_LEVELS = {"Q80": 25.0, "Q90": 45.0, "Q95": 75.0}


def _headroom(
    nominal: HeadroomSummary,
    *,
    turnaround: float,
    u_max: float,
    source_suffix: str,
) -> HeadroomSummary:
    return HeadroomSummary(
        u_max=float(u_max),
        turnaround_lower_bound_q=float(turnaround),
        turnaround_quantile=float(nominal.turnaround_quantile),
        headroom_quantile=float(nominal.headroom_quantile),
        headroom_positive_n=int(nominal.headroom_positive_n),
        source_id=f"{nominal.source_id}:{source_suffix}",
        floor_to_minutes=float(nominal.floor_to_minutes),
    )


def _median(values: Sequence[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    return ordered[len(ordered) // 2]


def _stage_summary(
    stage: str,
    rows: Sequence[dict[str, object]],
    *,
    reference_value: float,
) -> dict[str, object]:
    values = [float(row["V"]) for row in rows]
    positive_u = [float(row["u_star"]) for row in rows if float(row["u_star"]) > 0.0]
    delta = sum(float(row["delta_J"]) for row in rows)
    return {
        "stage": stage,
        "N": len(rows),
        "median_V": _median(values),
        "positive_V_share": (
            sum(value > 0.0 for value in values) / len(values) if values else None
        ),
        "activation_share": (
            len(positive_u) / len(rows) if rows else None
        ),
        "median_positive_u": _median(positive_u),
        "delta_J": delta,
        "L_rec": None if reference_value <= 0.0 else delta / reference_value,
        "A5": (
            sum(float(row["within_5"]) for row in rows) / len(rows)
            if rows
            else None
        ),
    }


def run_robustness(
    cohort: ReferenceRecoveryCohort,
    *,
    service,
    nominal_headroom: HeadroomSummary,
) -> list[dict[str, object]]:
    if not cohort.nodes:
        return []
    reference_value_total = sum(
        float(item.reference_recoverable_value) for item in cohort.nodes
    )
    configs: list[tuple[str, str, float, float, float]] = []
    for level in LAMBDA_LEVELS:
        configs.append(
            (
                "lambda",
                f"{level:g}",
                level,
                float(nominal_headroom.turnaround_lower_bound_q),
                float(nominal_headroom.u_max),
            )
        )
    for level, value in TURNAROUND_LEVELS.items():
        configs.append(
            (
                "turnaround_lower_bound",
                level,
                float(LAMBDA_NOMINAL),
                float(value),
                float(nominal_headroom.u_max),
            )
        )
    for level, value in U_MAX_LEVELS.items():
        configs.append(
            (
                "u_max",
                level,
                float(LAMBDA_NOMINAL),
                float(nominal_headroom.turnaround_lower_bound_q),
                float(value),
            )
        )

    output: list[dict[str, object]] = []
    for axis, level, lambda_value, turnaround, u_max in configs:
        headroom = _headroom(
            nominal_headroom,
            turnaround=turnaround,
            u_max=u_max,
            source_suffix=f"{axis}:{level}",
        )
        grouped: dict[str, list[dict[str, object]]] = {"PRE": [], "TURN": []}
        for item in cohort.nodes:
            node = item.node
            context = transition_context(node, headroom)
            decision = solve_recovery(
                node.state("HISTORY_JOINT"),
                context=context,
                service=service,
                headroom_summary=headroom,
                policy=RecoveryPolicy(lambda_policy=lambda_value),
            )
            if decision.u_star is None:
                continue
            if decision.recoverable_value is None:
                continue
            nominal_action = float(item.reference_decision.u_star or 0.0)
            feasible_nominal_action = min(nominal_action, float(u_max))
            robust_action = float(decision.u_star)
            robust_objective = expected_objective(
                node.state("HISTORY_JOINT"),
                context=context,
                service=service,
                u=robust_action,
                u_max=u_max,
                lambda_policy=lambda_value,
            )
            nominal_action_objective = expected_objective(
                node.state("HISTORY_JOINT"),
                context=context,
                service=service,
                u=feasible_nominal_action,
                u_max=u_max,
                lambda_policy=lambda_value,
            )
            grouped[action_stage_class(node.stage)].append(
                {
                    "V": decision.recoverable_value,
                    "u_star": robust_action,
                    "delta_J": robust_objective - nominal_action_objective,
                    "within_5": abs(robust_action - feasible_nominal_action) <= 5.0 + 1e-9,
                }
            )
        for stage, rows in grouped.items():
            if not rows:
                continue
            stage_reference = sum(
                float(item.reference_recoverable_value)
                for item in cohort.nodes
                if action_stage_class(item.node.stage) == stage
            )
            output.append(
                {
                    "axis": axis,
                    "level": level,
                    **_stage_summary(stage, rows, reference_value=stage_reference),
                }
            )
    return output


__all__ = [
    "LAMBDA_LEVELS",
    "TURNAROUND_LEVELS",
    "U_MAX_LEVELS",
    "run_robustness",
]
