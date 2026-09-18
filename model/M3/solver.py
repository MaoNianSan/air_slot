"""Development-time Pyomo + HiGHS parity backend for M3 Stage II.

The formal Stage-II path is complete enumeration over the finite five-minute
action grid (:func:`model.M3.stage2.solve_recovery`). This module exists only to
re-solve representative PRE/TURN instances with a mathematical-programming
backend and verify that the solver reproduces the enumeration optimum and
objective. It is never the paper-primary production path and is never run per
Final-Test row.

The parity model is an exact one-hot representation of the finite action grid:
``sum_i y_i = 1``, ``u = sum_i u_i y_i``, ``y_i in {0,1}`` and
``min sum_i J(u_i) y_i``. The cost coefficients ``J(u_i)`` are produced by the
same M2 consequence map and transition as the enumeration path, so the check
isolates the optimizer's selection rather than re-deriving the science.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pyomo.environ as pyo
from pyomo.contrib.appsi.base import TerminationCondition
from pyomo.contrib.appsi.solvers.highs import Highs

from model.M2.consequence_service import M2ConsequenceService
from model.M3.stage2 import (
    RecoveryPolicy,
    objective_by_grid,
    solve_recovery,
)
from model.M3.transition import TransitionContext
from model.PRE.decision_environment import is_actionable
from model.common.decision_contracts import (
    HeadroomSummary,
    SolverStatus,
    StateScenarioSet,
)
from model.common.errors import ContractError


__all__ = [
    "HIGH_SPARITY_TOLERANCE",
    "HighsParityResult",
    "solve_with_highs",
]


#: Numeric tolerance for u* and objective parity. The enumeration and the
#: solver both operate on the same float cost table, so the bound is tight.
HIGH_SPARITY_TOLERANCE = 1e-6

#: Secondary lexicographic weight. It breaks exact objective ties toward the
#: smaller intervention without changing the primary objective ordering.
_TIE_BREAK_EPSILON = 1e-9


@dataclass(frozen=True)
class HighsParityResult:
    """One representative-node enumeration/HiGHS parity record."""

    node_id: str
    stage: str
    representation_id: str
    action_count: int
    solver_status: str
    termination_condition: str
    u_star_enumeration: float
    u_star_highs: float
    j_zero: float
    j_star_enumeration: float
    j_star_highs: float
    recoverable_value_enumeration: float
    recoverable_value_highs: float
    objective_absolute_error: float
    u_star_parity: bool
    objective_parity: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize the record for diagnostics JSON."""

        return asdict(self)


def solve_with_highs(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary,
    policy: RecoveryPolicy | None = None,
) -> HighsParityResult:
    """Re-solve one actionable node with HiGHS and compare to enumeration.

    Only PRE/TURN nodes are admitted: TAXI/COMP have the zero action set and no
    optimization problem to check. A non-optimal solver termination is a hard
    error rather than an implicit fallback to ``u = 0``.
    """

    if not is_actionable(state_set.stage):
        raise ContractError("M3_HIGHS_PARITY_REQUIRES_ACTIONABLE_STAGE")
    if headroom_summary is None:
        raise ContractError("M3_HIGHS_PARITY_HEADROOM_SUMMARY_REQUIRED")
    if (
        abs(
            headroom_summary.turnaround_lower_bound_q
            - context.turnaround_lower_bound_minutes
        )
        > HIGH_SPARITY_TOLERANCE
    ):
        raise ContractError("M3_HIGHS_PARITY_HEADROOM_SUMMARY_MISMATCH")

    active_policy = (policy or RecoveryPolicy()).validate()
    enumeration = solve_recovery(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=active_policy,
    )
    if enumeration.solver_status is not SolverStatus.EXACT_ENUMERATION:
        raise ContractError("M3_HIGHS_PARITY_ENUMERATION_PATH_UNAVAILABLE")
    if enumeration.u_star is None or enumeration.j_star is None:
        raise ContractError("M3_HIGHS_PARITY_ENUMERATION_OUTPUT_MISSING")

    table = objective_by_grid(
        state_set,
        context=context,
        service=service,
        u_max=headroom_summary.u_max,
        policy=active_policy,
        floor_to_minutes=headroom_summary.floor_to_minutes,
    )
    grid = tuple(u for u, _ in table)
    costs = tuple(cost for _, cost in table)

    model = pyo.ConcreteModel(name=f"m3_stage2_parity_{state_set.node_id}")
    model.actions = pyo.Set(initialize=range(len(grid)))
    model.select = pyo.Var(model.actions, domain=pyo.Binary)
    model.u = pyo.Var(domain=pyo.NonNegativeReals, bounds=(0.0, float(grid[-1])))
    model.choose_one = pyo.Constraint(
        expr=sum(model.select[index] for index in model.actions) == 1
    )
    model.link_u = pyo.Constraint(
        expr=model.u
        == sum(grid[index] * model.select[index] for index in model.actions)
    )
    model.objective = pyo.Objective(
        expr=sum(costs[index] * model.select[index] for index in model.actions)
        + _TIE_BREAK_EPSILON * model.u,
        sense=pyo.minimize,
    )

    solver = Highs()
    results = solver.solve(model)
    termination = str(results.termination_condition)
    if results.termination_condition is not TerminationCondition.optimal:
        raise ContractError(f"M3_HIGHS_PARITY_NOT_OPTIMAL:{termination}")

    selected = [
        index
        for index in model.actions
        if pyo.value(model.select[index]) > 0.5
    ]
    if len(selected) != 1:
        raise ContractError("M3_HIGHS_PARITY_SELECTION_NOT_SINGLETON")
    selected_index = selected[0]
    u_highs = float(grid[selected_index])
    j_highs = float(costs[selected_index])
    j_zero = float(enumeration.j_zero)
    recoverable_highs = j_zero - j_highs

    u_star_parity = (
        abs(u_highs - float(enumeration.u_star)) <= HIGH_SPARITY_TOLERANCE
    )
    objective_error = abs(j_highs - float(enumeration.j_star))
    objective_parity = objective_error <= HIGH_SPARITY_TOLERANCE
    return HighsParityResult(
        node_id=state_set.node_id,
        stage=state_set.stage.value,
        representation_id=state_set.representation.representation_id,
        action_count=len(grid),
        solver_status=SolverStatus.HIGHS_PARITY.value,
        termination_condition=termination,
        u_star_enumeration=float(enumeration.u_star),
        u_star_highs=u_highs,
        j_zero=j_zero,
        j_star_enumeration=float(enumeration.j_star),
        j_star_highs=j_highs,
        recoverable_value_enumeration=float(enumeration.recoverable_value),
        recoverable_value_highs=recoverable_highs,
        objective_absolute_error=objective_error,
        u_star_parity=u_star_parity,
        objective_parity=objective_parity,
    )
