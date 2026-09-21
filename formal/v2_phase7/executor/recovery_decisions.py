"""``RECOVERY_DECISIONS``: formal Stage-II decisions on the fixed ``R_g*``.

The active production authority is exact enumeration over the frozen finite
action grid. Pyomo+HiGHS is retained only as an independent parity backend in
``validation/m3_enumeration_highs_parity.py`` and in representative dry-run
fixtures; production rows never invoke HiGHS and never publish row-level parity
records.

All actionable decisions are produced by the frozen
``model.M3.stage2.enumerate_recovery_decision`` service. The executor never
re-implements the objective, the transition, the feasible set or the tie rule.

Every primary variant is solved on exactly the same fixed reference cohort
``R_g*``. Nodes outside that cohort, and nodes whose stage has an empty local
action set, keep the typed ``NOT_ACTIONABLE`` decision produced by the frozen
service (``u* = 0``, ``action_grid = (0,)``, ``recoverable_value = None``); they
are never zero-filled into a positive action.

For the reference variant (``HISTORY_JOINT``) the complete objective table
``J_i^*(u)`` over the specification grid is published so that M4 can evaluate
every comparator action against the same reference objective basis.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from model.M3.stage2 import RecoveryPolicy, action_grid, objective_by_grid
from model.M3.transition import TransitionContext
from model.common.decision_contracts import (
    RecoveryDecision,
    SolverStatus,
    TypedStatus,
)

from .. import constants as C
from ..errors import TypedBlocker, _require
from ..stage2_authority import (
    has_abstaining_scenario,
    production_solver_metadata,
    solve_production_recovery,
)
from . import stages as S
from .codec import recovery_decision_from_payload, recovery_decision_to_payload
from .nodes import CanonicalNode, nodes_by_id
from .reference_cohort import ABSTAIN_TYPED_STATE, actionable_cohort
from .services import FrozenScienceServices, binding_from_node
from .state_variants import state_sets_by_node


def build_recovery_decisions(
    nodes_payload: Mapping[str, Any],
    state_variants: Mapping[str, Any],
    reference_cohort: Mapping[str, Any],
    *,
    services: FrozenScienceServices,
) -> dict[str, Any]:
    """Solve every variant on the fixed reference cohort."""

    nodes = nodes_by_id(nodes_payload)
    decision_node_ids = tuple(
        str(value) for value in reference_cohort["shortlist_node_ids"]
    )
    cohort_ids = actionable_cohort(reference_cohort)
    _require(bool(decision_node_ids), "PHASE7_RECOVERY_DECISION_NODE_SET_EMPTY")

    authority = production_solver_metadata()
    headroom = services.headroom_summary
    policy = RecoveryPolicy(lambda_policy=C.NOMINAL_LAMBDA).validate()
    rows: list[dict[str, Any]] = []
    reference_objectives: dict[str, dict[str, Any]] = {}
    violations: dict[str, list[Any]] = {
        "action_grid": [],
        "negative_recoverable_value": [],
        "non_actionable_positive_action": [],
        "reference_objective_identity": [],
        "solver_status": [],
    }
    typed_counts: dict[str, int] = {}
    row_parity_checks_executed = 0

    for variant in S.PRIMARY_STATE_VARIANTS:
        state_sets = state_sets_by_node(state_variants, variant)
        for node_id in decision_node_ids:
            node = nodes.get(node_id)
            if node is None:
                raise TypedBlocker("PHASE7_RECOVERY_NODE_NOT_MATERIALIZED", node_id)
            state_set = state_sets.get(node_id)
            if state_set is None:
                raise TypedBlocker("PHASE7_RECOVERY_STATE_SET_MISSING", node_id)
            context = TransitionContext(
                sobt_minutes=float(node.sobt_minutes),
                turnaround_lower_bound_minutes=float(
                    headroom.turnaround_lower_bound_q
                ),
            )
            service = services.consequence_service(
                {node.node_id: binding_from_node(node)}
            )
            if has_abstaining_scenario(state_set):
                typed_counts[ABSTAIN_TYPED_STATE] = (
                    typed_counts.get(ABSTAIN_TYPED_STATE, 0) + 1
                )
                rows.append(
                    _typed_row(
                        variant=variant,
                        node=node,
                        typed_state=ABSTAIN_TYPED_STATE,
                        reason_codes=(
                            "PHASE7_STAGE2_UNSUPPORTED_SCENARIO_UNDER_VARIANT",
                        ),
                    )
                )
                continue

            decision = solve_production_recovery(
                state_set,
                context=context,
                service=service,
                headroom_summary=headroom,
                policy=policy,
            )
            if decision.actionable_status is TypedStatus.NOT_ACTIONABLE:
                typed_counts[TypedStatus.NOT_ACTIONABLE.value] = (
                    typed_counts.get(TypedStatus.NOT_ACTIONABLE.value, 0) + 1
                )
                row = _typed_row(
                    variant=variant,
                    node=node,
                    typed_state=TypedStatus.NOT_ACTIONABLE.value,
                    reason_codes=decision.reason_codes,
                )
                row["decision"] = recovery_decision_to_payload(decision)
                if decision.u_star not in {0.0} or tuple(decision.action_grid) != (
                    0.0,
                ):
                    violations["non_actionable_positive_action"].append(
                        {"variant": variant, "node_id": node_id}
                    )
                if decision.solver_status is not SolverStatus.NOT_RUN:
                    violations["solver_status"].append(
                        {
                            "variant": variant,
                            "node_id": node_id,
                            "expected": SolverStatus.NOT_RUN.value,
                            "observed": decision.solver_status.value,
                        }
                    )
                rows.append(row)
                continue

            _collect_decision_violations(
                violations,
                variant=variant,
                node_id=node_id,
                decision=decision,
            )
            if len(cohort_ids) and node_id in cohort_ids:
                _require(
                    decision.u_max is not None
                    and abs(float(decision.u_max) - headroom.u_max) <= 1e-9,
                    "PHASE7_RECOVERY_U_MAX_MISMATCH",
                    {"variant": variant, "node_id": node_id},
                )
            row = {
                "variant": variant,
                "node_id": node.node_id,
                "episode_id": node.episode_id,
                "stage": node.stage,
                "actionable": True,
                "typed_state": None,
                "reason_codes": list(decision.reason_codes),
                "decision": recovery_decision_to_payload(decision),
                "parity": None,
            }
            rows.append(row)
            if variant == S.REFERENCE_VARIANT:
                table = objective_by_grid(
                    state_set,
                    context=context,
                    service=service,
                    u_max=headroom.u_max,
                    policy=policy,
                    floor_to_minutes=headroom.floor_to_minutes,
                )
                reference_objectives[node_id] = {
                    "episode_id": node.episode_id,
                    "action_grid": [float(u) for u, _ in table],
                    "objective_by_action": [
                        [float(u), float(value)] for u, value in table
                    ],
                    "j_star": float(decision.j_star),
                    "j_zero": float(decision.j_zero),
                }
                if abs(table[0][1] - float(decision.j_zero)) > C.M3_NUMERICAL_COMPARISON_TOLERANCE:
                    violations["reference_objective_identity"].append(
                        {"variant": variant, "node_id": node_id, "field": "j_zero"}
                    )

    _require_no_violations(violations)
    return {
        "reference_variant": S.REFERENCE_VARIANT,
        "cohort_id": str(reference_cohort["cohort_id"]),
        "cohort_node_ids": list(cohort_ids),
        "decision_node_ids": list(decision_node_ids),
        "primary_variants": list(S.PRIMARY_STATE_VARIANTS),
        "specification": {
            "lambda": float(policy.lambda_policy),
            "u_max": float(headroom.u_max),
            "turnaround_lower_bound_q": float(
                headroom.turnaround_lower_bound_q
            ),
            "turnaround_quantile": float(headroom.turnaround_quantile),
            "headroom_quantile": float(headroom.headroom_quantile),
            "action_floor_minutes": float(headroom.floor_to_minutes),
            "train_support_source_id": headroom.source_id,
            "u_max_by_specification": dict(C.U_MAX_BY_SPECIFICATION),
            "specification_key": "nominal",
        },
        "formal_solver": authority["stage2_primary_solver"],
        "parity_oracle": authority["parity_backend"],
        "compatibility_field_semantics": {
            "formal_solver": "ACTIVE_STAGE2_PRIMARY_SOLVER",
            "parity_oracle": "INDEPENDENT_PARITY_BACKEND_NOT_EXECUTED_PER_ROW",
        },
        "objective_perturbation": "NONE",
        "numerical_tolerance": {
            "name": "M3_NUMERICAL_COMPARISON_TOLERANCE",
            "value": float(C.M3_NUMERICAL_COMPARISON_TOLERANCE),
            "scientific_parameter": False,
        },
        "a00_never_a_recommendation": True,
        "production_rows_use_highs": False,
        "row_parity_checks_executed": row_parity_checks_executed,
        "row_count": len(rows),
        "rows": rows,
        "reference_objectives": reference_objectives,
        "typed_state_counts": dict(sorted(typed_counts.items())),
        "invariants": {
            "action_grid_violations": violations["action_grid"],
            # Legacy schema slots: production rows no longer execute per-row
            # HiGHS comparisons; the standalone parity validator owns them.
            "solver_oracle_action_disagreements": [],
            "solver_oracle_objective_disagreements": [],
            "solver_oracle_value_disagreements": [],
            "negative_recoverable_values": violations[
                "negative_recoverable_value"
            ],
            "non_actionable_positive_actions": violations[
                "non_actionable_positive_action"
            ],
            "reference_objective_identity_violations": violations[
                "reference_objective_identity"
            ],
            "solver_status_violations": violations["solver_status"],
            "row_parity_checks_executed": row_parity_checks_executed,
            "status": "PASS",
        },
        **authority,
    }


def _typed_row(
    *,
    variant: str,
    node: CanonicalNode,
    typed_state: str,
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "variant": variant,
        "node_id": node.node_id,
        "episode_id": node.episode_id,
        "stage": node.stage,
        "actionable": False,
        "typed_state": typed_state,
        "reason_codes": [str(code) for code in reason_codes],
        "decision": None,
        "parity": None,
    }


def _collect_decision_violations(
    violations: dict[str, list[Any]],
    *,
    variant: str,
    node_id: str,
    decision: RecoveryDecision,
) -> None:
    context = {"variant": variant, "node_id": node_id}
    if decision.solver_status is not SolverStatus.EXACT_ENUMERATION:
        violations["solver_status"].append(
            {
                **context,
                "expected": SolverStatus.EXACT_ENUMERATION.value,
                "observed": decision.solver_status.value,
            }
        )
    if decision.recoverable_value is None or (
        float(decision.recoverable_value)
        < -C.M3_NUMERICAL_COMPARISON_TOLERANCE
    ):
        violations["negative_recoverable_value"].append(context)
    expected_grid = action_grid(float(decision.u_max or 0.0))
    if tuple(decision.action_grid) != expected_grid:
        violations["action_grid"].append(
            {
                **context,
                "u_max": decision.u_max,
                "action_grid_size": len(decision.action_grid),
            }
        )
    elif decision.u_star not in set(decision.action_grid):
        violations["action_grid"].append({**context, "u_star": decision.u_star})


def _require_no_violations(violations: Mapping[str, Sequence[Any]]) -> None:
    failed = {
        name: list(values) for name, values in violations.items() if values
    }
    if failed:
        raise TypedBlocker("PHASE7_STAGE2_INVARIANT_VIOLATION", failed)


def rows_by_variant(
    payload: Mapping[str, Any], variant: str
) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["node_id"]): row
        for row in payload["rows"]
        if row["variant"] == variant
    }


def recovery_decisions_by_node(
    payload: Mapping[str, Any], variant: str
) -> dict[str, RecoveryDecision]:
    resolved: dict[str, RecoveryDecision] = {}
    for node_id, row in rows_by_variant(payload, variant).items():
        if row.get("decision") is None:
            continue
        resolved[node_id] = recovery_decision_from_payload(row["decision"])
    return resolved


def reference_objective_lookup(
    payload: Mapping[str, Any], node_id: str
) -> dict[tuple[str, float], float]:
    table = payload["reference_objectives"][node_id]
    return {
        (node_id, float(action)): float(objective)
        for action, objective in table["objective_by_action"]
    }


__all__ = [
    "build_recovery_decisions",
    "recovery_decisions_by_node",
    "reference_objective_lookup",
    "rows_by_variant",
]
