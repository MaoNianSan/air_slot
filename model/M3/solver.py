"""M3 Stage-II Pyomo + HiGHS parity backend.

The Stage-II production authority is exact enumeration of the finite
five-minute action grid (post-R2 ruling
``HUMAN_GATE_B0A_SOLVER_AUTHORITY_RULING_20260919``). This module retains the
Pyomo one-hot model solved by HiGHS strictly as an independent parity /
regression backend and for historical-artifact compatibility; it must never
produce a canonical Stage-II decision.

The model is mathematically identical to enumeration:

``sum_m y_m = 1``, ``u = sum_m u_m y_m``, ``y_m in {0,1}`` and
``min sum_m J(u_m) y_m``. The frozen tie rule is
``u* = min{u in U_i(theta) : J_i(u) = min J_i}`` and is implemented as a
second lexicographic solve inside ``J <= J* + tau``. ``tau`` is only a numerical
comparison tolerance; it is not a scientific parameter and never perturbs the
objective used to define ``J*``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pyomo.environ as pyo
from pyomo.contrib.appsi.base import TerminationCondition
from pyomo.contrib.appsi.solvers.highs import Highs

from model.M2.consequence_service import M2ConsequenceService
from model.M3.stage2 import (
    RecoveryPolicy,
    enumerate_recovery_decision,
    objective_by_grid,
)
from model.M3.transition import TransitionContext
from model.PRE.decision_environment import is_actionable
from model.common.decision_contracts import (
    HeadroomSummary,
    RecoveryDecision,
    SolverStatus,
    StateScenarioSet,
    TypedStatus,
)
from model.common.errors import ContractError


__all__ = [
    "HIGH_SPARITY_TOLERANCE",
    "M3_NUMERICAL_COMPARISON_TOLERANCE",
    "HighsParityResult",
    "solve_stage2_with_highs",
    "solve_with_highs",
]


#: Numeric comparison tolerance for action parity, objective parity and the
#: lexicographic second-stage feasibility cut. It is explicitly not a
#: scientific parameter.
M3_NUMERICAL_COMPARISON_TOLERANCE = 1e-6

#: Legacy misspelled alias retained for older diagnostics imports.
HIGH_SPARITY_TOLERANCE = M3_NUMERICAL_COMPARISON_TOLERANCE


@dataclass(frozen=True)
class HighsParityResult:
    """One HiGHS-parity versus exact-enumeration comparison record.

    Field names are SEALED COMPATIBILITY LABELS: ``formal_*`` denotes the
    Pyomo+HiGHS parity backend and ``oracle_*`` the exact-enumeration
    production authority, historically labelled. The parity checks here are
    diagnostics only and never change the authority of the enumeration
    decision.
    """

    node_id: str
    stage: str
    representation_id: str
    action_count: int
    formal_solver: str
    parity_oracle: str
    termination_condition: str
    u_star_formal: float
    u_star_oracle: float
    j_zero: float
    j_star_formal: float
    j_star_oracle: float
    recoverable_value_formal: float
    recoverable_value_oracle: float
    objective_absolute_error: float
    recoverable_value_absolute_error: float
    u_star_parity: bool
    objective_parity: bool
    recoverable_value_parity: bool
    tie_break_applied: bool
    near_tie_candidate_count: int

    def to_dict(self) -> dict[str, object]:
        """Serialize the record for diagnostics JSON."""

        return asdict(self)


def _require_actionable_inputs(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    headroom_summary: HeadroomSummary | None,
) -> None:
    if not is_actionable(state_set.stage):
        raise ContractError("M3_HIGHS_REQUIRES_ACTIONABLE_STAGE")
    if headroom_summary is None:
        raise ContractError("M3_HEADROOM_SUMMARY_REQUIRED_FOR_ACTIONABLE_STAGE")
    if (
        abs(
            headroom_summary.turnaround_lower_bound_q
            - context.turnaround_lower_bound_minutes
        )
        > M3_NUMERICAL_COMPARISON_TOLERANCE
    ):
        raise ContractError("M3_TRANSITION_CONTEXT_HEADROOM_SUMMARY_MISMATCH")


def _objective_and_grid(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary,
    policy: RecoveryPolicy,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    table = objective_by_grid(
        state_set,
        context=context,
        service=service,
        u_max=headroom_summary.u_max,
        policy=policy,
        floor_to_minutes=headroom_summary.floor_to_minutes,
    )
    return (
        tuple(u for u, _ in table),
        tuple(float(cost) for _, cost in table),
    )


def solve_stage2_with_highs(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary | None = None,
    policy: RecoveryPolicy | None = None,
) -> RecoveryDecision:
    """Solve one actionable PRE/TURN node with the formal HiGHS authority."""

    _require_actionable_inputs(
        state_set, context=context, headroom_summary=headroom_summary
    )
    assert headroom_summary is not None
    active_policy = (policy or RecoveryPolicy()).validate()
    grid, costs = _objective_and_grid(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=active_policy,
    )

    model = pyo.ConcreteModel(name=f"m3_stage2_formal_{state_set.node_id}")
    model.actions = pyo.Set(initialize=range(len(grid)))
    model.select = pyo.Var(model.actions, domain=pyo.Binary)
    model.choose_one = pyo.Constraint(
        expr=sum(model.select[index] for index in model.actions) == 1
    )
    model.cost_expression = pyo.Expression(
        expr=sum(costs[index] * model.select[index] for index in model.actions)
    )
    model.objective = pyo.Objective(
        expr=model.cost_expression,
        sense=pyo.minimize,
    )

    solver = Highs()
    first_results = solver.solve(model)
    first_termination = str(first_results.termination_condition)
    if first_results.termination_condition is not TerminationCondition.optimal:
        raise ContractError(f"M3_HIGHS_FORMAL_NOT_OPTIMAL:{first_termination}")

    exact_grid_minimum = min(costs)
    j_star = float(pyo.value(model.cost_expression))
    if abs(j_star - exact_grid_minimum) > M3_NUMERICAL_COMPARISON_TOLERANCE:
        raise ContractError(
            "M3_HIGHS_FORMAL_OBJECTIVE_BELOW_OR_ABOVE_GRID_MINIMUM:"
            f"{j_star}:{exact_grid_minimum}"
        )

    near_optimal_indices = tuple(
        index
        for index, cost in enumerate(costs)
        if cost <= j_star + M3_NUMERICAL_COMPARISON_TOLERANCE
    )
    if not near_optimal_indices:
        raise ContractError("M3_HIGHS_TIE_FEASIBLE_SET_EMPTY")

    # Lexicographic second stage: keep the optimal objective value, then choose
    # the smallest recovery intensity by minimizing u directly.
    model.objective.deactivate()
    model.near_optimal = pyo.Constraint(
        expr=model.cost_expression
        <= j_star + M3_NUMERICAL_COMPARISON_TOLERANCE
    )
    model.tie_objective = pyo.Objective(
        expr=sum(grid[index] * model.select[index] for index in model.actions),
        sense=pyo.minimize,
    )
    second_results = solver.solve(model)
    second_termination = str(second_results.termination_condition)
    if second_results.termination_condition is not TerminationCondition.optimal:
        raise ContractError(f"M3_HIGHS_TIE_BREAK_NOT_OPTIMAL:{second_termination}")

    selected = [
        index
        for index in model.actions
        if pyo.value(model.select[index]) > 0.5
    ]
    if len(selected) != 1:
        raise ContractError("M3_HIGHS_FORMAL_SELECTION_NOT_SINGLETON")
    selected_index = selected[0]
    if selected_index != near_optimal_indices[0]:
        raise ContractError(
            "M3_HIGHS_TIE_BREAK_RULE_VIOLATION:"
            f"{selected_index}:{near_optimal_indices[0]}"
        )

    u_star = float(grid[selected_index])
    selected_objective = float(costs[selected_index])
    j_zero = float(costs[0])
    recoverable = j_zero - selected_objective
    tie_break_applied = len(near_optimal_indices) > 1
    reasons = ["M3_A00_BASELINE_NEVER_A_RECOMMENDATION"]
    if u_star == 0.0:
        reasons.append("M3_BASELINE_ACTION_SELECTED_NO_NEW_INTERVENTION")
    else:
        reasons.append("M3_LOCAL_RECOVERY_SELECTED")
    if headroom_summary.u_max == 0.0:
        reasons.append("M3_ZERO_TRAIN_U_MAX")

    return RecoveryDecision(
        episode_id=state_set.episode_id,
        chain_id=state_set.chain_id,
        node_id=state_set.node_id,
        representation_id=state_set.representation.representation_id,
        stage=state_set.stage,
        actionable_status=TypedStatus.SUPPORTED,
        headroom_summary=headroom_summary,
        action_grid=grid,
        u_max=headroom_summary.u_max,
        u_star=u_star,
        j_zero=j_zero,
        j_star=selected_objective,
        recoverable_value=recoverable,
        lambda_policy=active_policy.lambda_policy,
        solver_status=SolverStatus.PYOMO_HIGHS,
        tie_break_applied=tie_break_applied,
        near_tie_candidate_count=len(near_optimal_indices),
        reason_codes=tuple(reasons),
    )


def solve_with_highs(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary,
    policy: RecoveryPolicy | None = None,
) -> HighsParityResult:
    """Compare the HiGHS parity backend with the exact enumeration authority."""

    highs_decision = solve_stage2_with_highs(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=policy,
    )
    enumeration_decision = enumerate_recovery_decision(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=policy,
    )
    if highs_decision.j_star is None or highs_decision.recoverable_value is None:
        raise ContractError("M3_HIGHS_PARITY_OUTPUT_MISSING")
    if (
        enumeration_decision.j_star is None
        or enumeration_decision.recoverable_value is None
    ):
        raise ContractError("M3_ENUMERATION_OUTPUT_MISSING")
    objective_error = abs(
        float(highs_decision.j_star) - float(enumeration_decision.j_star)
    )
    recoverable_error = abs(
        float(highs_decision.recoverable_value)
        - float(enumeration_decision.recoverable_value)
    )
    return HighsParityResult(
        node_id=state_set.node_id,
        stage=state_set.stage.value,
        representation_id=state_set.representation.representation_id,
        action_count=len(highs_decision.action_grid),
        formal_solver=SolverStatus.PYOMO_HIGHS.value,
        parity_oracle=SolverStatus.EXACT_ENUMERATION.value,
        termination_condition="optimal",
        u_star_formal=float(highs_decision.u_star),
        u_star_oracle=float(enumeration_decision.u_star),
        j_zero=float(enumeration_decision.j_zero),
        j_star_formal=float(highs_decision.j_star),
        j_star_oracle=float(enumeration_decision.j_star),
        recoverable_value_formal=float(highs_decision.recoverable_value),
        recoverable_value_oracle=float(enumeration_decision.recoverable_value),
        objective_absolute_error=objective_error,
        recoverable_value_absolute_error=recoverable_error,
        u_star_parity=highs_decision.u_star == enumeration_decision.u_star,
        objective_parity=objective_error <= M3_NUMERICAL_COMPARISON_TOLERANCE,
        recoverable_value_parity=(
            recoverable_error <= M3_NUMERICAL_COMPARISON_TOLERANCE
        ),
        tie_break_applied=bool(enumeration_decision.tie_break_applied),
        near_tie_candidate_count=int(
            enumeration_decision.near_tie_candidate_count or 0
        ),
    )
