"""``ROBUSTNESS``: frozen Stage-II OFAT sensitivity on the fixed ``R*``.

This stage never reruns Stage-I and never changes canonical identities. It
starts from the reference recovery cohort published by
``REFERENCE_RECOVERY_COHORT`` and calls the frozen exact-enumeration Stage-II
service once per node, axis and level.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from model.M3.stage2 import (
    LAMBDA_GRID,
    LAMBDA_NOMINAL,
    RecoveryPolicy,
    expected_objective,
)
from model.M3.transition import TransitionContext
from model.PRE.decision_environment import action_stage_class
from model.common.decision_contracts import HeadroomSummary
from model.common.enums import OperationalStage

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..stage2_authority import production_solver_metadata, solve_production_recovery
from . import stages as S
from .codec import recovery_decision_from_payload
from .nodes import nodes_by_id
from .recovery_decisions import rows_by_variant
from .reference_cohort import actionable_cohort
from .services import FrozenScienceServices, binding_from_node
from .state_variants import state_sets_by_node

LAMBDA_LEVELS = tuple(float(value) for value in LAMBDA_GRID)
TURNAROUND_LEVELS = {"Q10": 34.0, "Q20": 41.0, "Q30": 47.0}
U_MAX_LEVELS = {"Q80": 25.0, "Q90": 45.0, "Q95": 75.0}
NOMINAL_REFERENCE_ID = "NOMINAL_STAGE2_FIXED_RSTAR_REFERENCE"


def build_robustness(
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    recovery_decisions: Mapping[str, Any],
    *,
    services: FrozenScienceServices,
) -> dict[str, Any]:
    """Evaluate the frozen one-factor-at-a-time Stage-II sensitivity grid."""

    nodes = nodes_by_id(nodes_payload)
    cohort = actionable_cohort(reference_cohort)
    _require(bool(cohort), "PHASE7_ROBUSTNESS_REFERENCE_COHORT_EMPTY")
    reference_sets = state_sets_by_node(state_variants, S.REFERENCE_VARIANT)
    reference_rows = rows_by_variant(recovery_decisions, S.REFERENCE_VARIANT)
    nominal_headroom = services.headroom_summary

    nominal_reference: dict[str, dict[str, float]] = {}
    for node_id in cohort:
        node = nodes.get(node_id)
        if node is None:
            raise TypedBlocker("PHASE7_ROBUSTNESS_NODE_NOT_MATERIALIZED", node_id)
        row = reference_rows.get(node_id)
        if row is None or row.get("decision") is None:
            raise TypedBlocker("PHASE7_ROBUSTNESS_REFERENCE_DECISION_MISSING", node_id)
        decision = recovery_decision_from_payload(row["decision"])
        if decision.u_star is None or decision.recoverable_value is None:
            raise TypedBlocker("PHASE7_ROBUSTNESS_REFERENCE_VALUE_MISSING", node_id)
        nominal_reference[node_id] = {
            "u_star": float(decision.u_star),
            "V": float(decision.recoverable_value),
        }

    nominal_reference_id = _hash_json(
        {
            "cohort": list(cohort),
            "nominal_reference": nominal_reference,
            "lambda": float(LAMBDA_NOMINAL),
            "turnaround_lower_bound_q": float(
                nominal_headroom.turnaround_lower_bound_q
            ),
            "u_max": float(nominal_headroom.u_max),
        }
    )
    configs = _configs()
    rows: list[dict[str, Any]] = []
    for axis, level, lambda_value, turnaround, u_max in configs:
        _assert_one_axis_changed(
            axis=axis,
            level=level,
            lambda_value=lambda_value,
            turnaround=turnaround,
            u_max=u_max,
            nominal_headroom=nominal_headroom,
        )
        headroom = _headroom(
            nominal_headroom,
            turnaround=turnaround,
            u_max=u_max,
            source_suffix=f"{axis}:{level}",
        )
        grouped: dict[str, list[dict[str, Any]]] = {"PRE": [], "TURN": []}
        for node_id in cohort:
            node = nodes[node_id]
            stage_class = action_stage_class(OperationalStage(node.stage))
            _require(
                stage_class in {"PRE", "TURN"},
                "PHASE7_ROBUSTNESS_NON_ACTIONABLE_STAGE",
                {"node_id": node_id, "stage": node.stage},
            )
            state_set = reference_sets.get(node_id)
            if state_set is None:
                raise TypedBlocker("PHASE7_ROBUSTNESS_STATE_SET_MISSING", node_id)
            service = services.consequence_service(
                {node.node_id: binding_from_node(node)}
            )
            context = TransitionContext(
                sobt_minutes=float(node.sobt_minutes),
                turnaround_lower_bound_minutes=float(
                    headroom.turnaround_lower_bound_q
                ),
            )
            decision = solve_production_recovery(
                state_set,
                context=context,
                service=service,
                headroom_summary=headroom,
                policy=RecoveryPolicy(lambda_policy=lambda_value),
            )
            _require(
                decision.u_star is not None
                and decision.recoverable_value is not None,
                "PHASE7_ROBUSTNESS_DECISION_TYPED",
                {"node_id": node_id, "axis": axis, "level": level},
            )
            nominal_action = float(nominal_reference[node_id]["u_star"])
            feasible_nominal_action = min(nominal_action, float(u_max))
            robust_action = float(decision.u_star)
            robust_objective = expected_objective(
                state_set,
                context=context,
                service=service,
                u=robust_action,
                u_max=float(u_max),
                lambda_policy=float(lambda_value),
            )
            nominal_action_objective = expected_objective(
                state_set,
                context=context,
                service=service,
                u=feasible_nominal_action,
                u_max=float(u_max),
                lambda_policy=float(lambda_value),
            )
            grouped[stage_class].append(
                {
                    "V": float(decision.recoverable_value),
                    "u_star": robust_action,
                    "delta_J": robust_objective - nominal_action_objective,
                    "within_5": abs(robust_action - feasible_nominal_action)
                    <= 5.0 + 1e-9,
                }
            )
        stage_rows = [
            _stage_summary(
                stage=stage,
                rows=grouped[stage],
                axis=axis,
                level=level,
                lambda_value=lambda_value,
                turnaround=turnaround,
                u_max=u_max,
                nominal_reference_id=nominal_reference_id,
                nominal_headroom=nominal_headroom,
            )
            for stage in ("PRE", "TURN")
            if grouped[stage]
        ]
        rows.extend(stage_rows)

    _require(
        bool(rows),
        "PHASE7_ROBUSTNESS_NO_ROWS",
    )
    return {
        "status": "PASS",
        "design": "ONE_FACTOR_AT_A_TIME",
        "axis_grids": {
            "lambda": [float(value) for value in LAMBDA_LEVELS],
            "turnaround_lower_bound": {
                key: float(value) for key, value in TURNAROUND_LEVELS.items()
            },
            "u_max": {key: float(value) for key, value in U_MAX_LEVELS.items()},
        },
        "nominal": {
            "lambda": float(LAMBDA_NOMINAL),
            "turnaround_lower_bound": float(
                nominal_headroom.turnaround_lower_bound_q
            ),
            "u_max": float(nominal_headroom.u_max),
        },
        "nominal_reference_id": nominal_reference_id,
        "fixed_r_star": True,
        "fixed_r_star_node_ids": list(cohort),
        "cohort_id": str(reference_cohort["cohort_id"]),
        "cohort_size": len(cohort),
        "stage1_rerun": False,
        "section4_h_capacity_called": False,
        "exact_enumeration": True,
        "node_relative_sobt": True,
        "solver": production_solver_metadata(),
        "rows": rows,
        "row_count": len(rows),
        "final_test_data_read": False,
        "taxi_comp_actions": [],
    }


def _configs() -> list[tuple[str, str, float, float, float]]:
    output: list[tuple[str, str, float, float, float]] = []
    for level in LAMBDA_LEVELS:
        output.append(
            (
                "lambda",
                f"{level:g}",
                float(level),
                float(C.NOMINAL_TURNAROUND_Q20),
                float(C.NOMINAL_U_MAX),
            )
        )
    for level, value in TURNAROUND_LEVELS.items():
        output.append(
            (
                "turnaround_lower_bound",
                level,
                float(LAMBDA_NOMINAL),
                float(value),
                float(C.NOMINAL_U_MAX),
            )
        )
    for level, value in U_MAX_LEVELS.items():
        output.append(
            (
                "u_max",
                level,
                float(LAMBDA_NOMINAL),
                float(C.NOMINAL_TURNAROUND_Q20),
                float(value),
            )
        )
    return output


def _assert_one_axis_changed(
    *,
    axis: str,
    level: str,
    lambda_value: float,
    turnaround: float,
    u_max: float,
    nominal_headroom: HeadroomSummary,
) -> None:
    if axis == "lambda":
        expected = (
            abs(turnaround - nominal_headroom.turnaround_lower_bound_q) <= 1e-9
            and abs(u_max - nominal_headroom.u_max) <= 1e-9
        )
    elif axis == "turnaround_lower_bound":
        expected = (
            abs(lambda_value - LAMBDA_NOMINAL) <= 1e-9
            and abs(u_max - nominal_headroom.u_max) <= 1e-9
        )
    elif axis == "u_max":
        expected = (
            abs(lambda_value - LAMBDA_NOMINAL) <= 1e-9
            and abs(
                turnaround - nominal_headroom.turnaround_lower_bound_q
            )
            <= 1e-9
        )
    else:
        expected = False
    _require(
        expected,
        "PHASE7_ROBUSTNESS_OFAT_VIOLATION",
        {
            "axis": axis,
            "level": level,
            "lambda": lambda_value,
            "turnaround": turnaround,
            "u_max": u_max,
        },
    )


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


def _stage_summary(
    *,
    stage: str,
    rows: Sequence[Mapping[str, Any]],
    axis: str,
    level: str,
    lambda_value: float,
    turnaround: float,
    u_max: float,
    nominal_reference_id: str,
    nominal_headroom: HeadroomSummary,
) -> dict[str, Any]:
    values = [float(row["V"]) for row in rows]
    positive_u = [float(row["u_star"]) for row in rows if float(row["u_star"]) > 0.0]
    delta = sum(float(row["delta_J"]) for row in rows)
    reference_value = sum(values)
    nominal_flag = (
        (axis == "lambda" and abs(lambda_value - LAMBDA_NOMINAL) <= 1e-9)
        or (
            axis == "turnaround_lower_bound"
            and abs(
                turnaround - nominal_headroom.turnaround_lower_bound_q
            )
            <= 1e-9
        )
        or (
            axis == "u_max"
            and abs(u_max - nominal_headroom.u_max) <= 1e-9
        )
    )
    return {
        "axis": axis,
        "level": level,
        "stage": stage,
        "nominal_flag": bool(nominal_flag),
        "nominal_reference_id": nominal_reference_id,
        "lambda": float(lambda_value),
        "turnaround_lower_bound": float(turnaround),
        "u_max": float(u_max),
        "N": len(rows),
        "median_V": _median(values),
        "IQR_V": _iqr(values),
        "P90_V": _p90(values),
        "positive_V_share": (
            sum(value > 0.0 for value in values) / len(values) if values else None
        ),
        "activation_share": (
            len(positive_u) / len(rows) if rows else None
        ),
        "median_positive_u": _median(positive_u),
        "IQR_positive_u": _iqr(positive_u),
        "P90_positive_u": _p90(positive_u),
        "delta_J": delta,
        "reference_V": reference_value,
        "L_rec": None if reference_value <= 0.0 else delta / reference_value,
        "A5": (
            sum(float(row["within_5"]) for row in rows) / len(rows)
            if rows
            else None
        ),
        "exact_enumeration": True,
        "stage1_rerun": False,
        "fixed_r_star": True,
    }


def _median(values: Sequence[float]) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    return ordered[len(ordered) // 2]


def _iqr(values: Sequence[float]) -> float | None:
    array = np.asarray([float(value) for value in values], dtype=float)
    if array.size == 0:
        return None
    return float(np.quantile(array, 0.75) - np.quantile(array, 0.25))


def _p90(values: Sequence[float]) -> float | None:
    array = np.asarray([float(value) for value in values], dtype=float)
    if array.size == 0:
        return None
    return float(np.quantile(array, 0.90))


def _hash_json(value: Any) -> str:
    body = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


__all__ = [
    "LAMBDA_LEVELS",
    "TURNAROUND_LEVELS",
    "U_MAX_LEVELS",
    "build_robustness",
]
