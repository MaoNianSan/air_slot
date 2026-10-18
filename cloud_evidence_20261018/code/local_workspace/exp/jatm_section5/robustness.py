 """Development-only OFAT robustness for Stage-II recovery."""

from __future__ import annotations

from collections.abc import Sequence

from model.M3.stage2 import LAMBDA_GRID, LAMBDA_NOMINAL, RecoveryPolicy, solve_recovery
from model.M3.support import HEADROOM_QUANTILE_NOMINAL, TURNAROUND_QUANTILE_NOMINAL
from model.common.decision_contracts import HeadroomSummary

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


def _summary(stage: str, decisions) -> dict[str, object]:
    values = [float(item.recoverable_value) for item in decisions]
    positive_u = [float(item.u_star) for item in decisions if float(item.u_star) > 0.0]
    return {
        "stage": stage,
        "N": len(decisions),
        "median_V": _median(values),
        "positive_V_share": (
            sum(value > 0.0 for value in values) / len(values) if values else None
        ),
        "activation_share": (
            sum(1 for item in decisions if float(item.u_star) > 0.0) / len(decisions)
            if decisions
            else None
        ),
        "median_positive_u": _median(positive_u),
        "delta_J": 0.0,
        "L_rec": None,
        "A5": 1.0,
    }


def run_robustness(
    cohort: ReferenceRecoveryCohort,
    *,
    service,
    nominal_headroom: HeadroomSummary,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    configs: list[tuple[str, str, float, float, float, float]] = []
    for level in LAMBDA_LEVELS:
        configs.append(("lambda", f"{level:g}", level, float(nominal_headroom.turnaround_lower_bound_q), float(nominal_headroom.u_max), float(LAMBDA_NOMINAL)))
    for level, value in TURNAROUND_LEVELS.items():
        configs.append(("turnaround_lower_bound", level, float(LAMBDA_NOMINAL), float(value), float(nominal_headroom.u_max), float(LAMBDA_NOMINAL)))
    for level, value in U_MAX_LEVELS.items():
        configs.append(("u_max", level, float(LAMBDA_NOMINAL), float(nominal_headroom.turnaround_lower_bound_q), float(value), float(LAMBDA_NOMINAL)))
    for axis, level, lambda_value, turnaround, u_max, _nominal_lambda in configs:
        headroom = _headroom(
            nominal_headroom,
            turnaround=turnaround,
            u_max=u_max,
            source_suffix=f"{axis}:{level}",
        )
        by_stage = {"PRE": [], "TURN": []}
        for item in cohort.nodes:
            context = transition_context(item.node, headroom)
            decision = solve_recovery(
                item.node.state("HISTORY_JOINT"),
                context=context,
                service=service,
                headroom_summary=headroom,
                policy=RecoveryPolicy(lambda_policy=lambda_value),
            )
            by_stage[item.node.stage.value].append(decision)
        for stage, decisions in by_stage.items():
            if decisions:
                output.append({"axis": axis, "level": level, **_summary(stage, decisions)})
    return output


__all__ = [
    "LAMBDA_LEVELS",
    "TURNAROUND_LEVELS",
    "U_MAX_LEVELS",
    "run_robustness",
]
