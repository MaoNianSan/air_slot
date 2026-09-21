"""M3 Stage-II recovery decision (Phase 3, post-R2 solver authority).

Manuscript section 4 Stage-II problem, defined over the finite
five-minute grid:

``J(u; lambda) = sum_s w_s Phi_C(C^{CU}_{i,s}(u)) + lambda * u / U_max``,
``u* = argmin_{u in U_i(theta)} J(u; lambda)`` (ties resolve to the smaller
``u``), ``V = J(0) - J(u*)``.

The production authority is exact enumeration of the finite action grid
(``enumerate_recovery_decision``), per the post-R2 ruling
``HUMAN_GATE_B0A_SOLVER_AUTHORITY_RULING_20260919``. The Pyomo+HiGHS backend
(``model.M3.solver``) is retained strictly as an independent parity /
regression tool and for historical-artifact compatibility; it never produces
a canonical Stage-II decision. The baseline action ``u = 0`` is the
no-new-intervention counterfactual: it is reported as a typed baseline
outcome, never as a recommendation of a template action.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from model.M2.comparison_support import PRIMARY_AGGREGATION_VIEW, phi_c
from model.M2.consequence_service import M2ConsequenceService
from model.common.decision_contracts import (
    HeadroomSummary,
    RecoveryDecision,
    SolverStatus,
    StateScenarioSet,
    TypedStatus,
)
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel
from model.M3.transition import TransitionContext, apply_recovery
from model.PRE.decision_environment import is_actionable


__all__ = [
    "LAMBDA_GRID",
    "LAMBDA_NOMINAL",
    "LAMBDA_SENSITIVITY",
    "RecoveryPolicy",
    "action_grid",
    "consequence_value",
    "enumerate_recovery_decision",
    "expected_objective",
    "objective_by_grid",
    "solve_recovery",
]


LAMBDA_NOMINAL = 0.25
LAMBDA_SENSITIVITY: tuple[float, ...] = (0.10, 0.50, 1.00)
LAMBDA_GRID: tuple[float, ...] = (
    LAMBDA_SENSITIVITY[0],
    LAMBDA_NOMINAL,
    LAMBDA_SENSITIVITY[1],
    LAMBDA_SENSITIVITY[2],
)


class RecoveryPolicy(FrozenModel):
    """Recovery-effort trade-off specification (manuscript-predefined grid)."""

    lambda_policy: float = Field(default=LAMBDA_NOMINAL, gt=0.0)
    allowed_lambdas: tuple[float, ...] = LAMBDA_GRID
    aggregation_view: str = PRIMARY_AGGREGATION_VIEW

    def validate(self) -> "RecoveryPolicy":
        if not any(
            abs(self.lambda_policy - allowed) <= 1e-9 for allowed in self.allowed_lambdas
        ):
            raise ContractError(
                f"M3_LAMBDA_OUTSIDE_MANUSCRIPT_GRID:{self.lambda_policy}"
            )
        return self


def action_grid(u_max: float, *, floor_to_minutes: float = 5.0) -> tuple[float, ...]:
    """``U = {0, floor, 2*floor, ..., U_max}``."""

    if u_max < 0.0:
        raise ContractError("M3_ACTION_GRID_NEGATIVE_U_MAX")
    if floor_to_minutes <= 0.0:
        raise ContractError("M3_ACTION_GRID_NON_POSITIVE_FLOOR")
    count = int(round(float(u_max) / float(floor_to_minutes)))
    if abs(count * floor_to_minutes - float(u_max)) > 1e-6:
        raise ContractError("M3_ACTION_GRID_U_MAX_NOT_ON_FLOOR_GRID")
    return tuple(float(index * floor_to_minutes) for index in range(count + 1))


def consequence_value(
    state_after,
    *,
    service: M2ConsequenceService,
    node_id: str,
    view: str = PRIMARY_AGGREGATION_VIEW,
) -> float:
    """``Phi_C(C^{CU})`` for one post-transition scenario state."""

    scenario = service.consequence_scenario(
        state_after, node_id=node_id, support=state_after.support
    )
    return phi_c(scenario.cu_components, view=view)


def expected_objective(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    u: float,
    u_max: float,
    lambda_policy: float = LAMBDA_NOMINAL,
    view: str = PRIMARY_AGGREGATION_VIEW,
) -> float:
    """``J(u; lambda)`` for one proposed recovery intensity."""

    if u < 0.0:
        raise ContractError("M3_OBJECTIVE_NEGATIVE_ACTION")
    if u_max < 0.0:
        raise ContractError("M3_OBJECTIVE_NEGATIVE_U_MAX")
    if u > 0.0 and u_max == 0.0:
        raise ContractError("M3_OBJECTIVE_POSITIVE_ACTION_WITH_ZERO_U_MAX")
    if u > u_max + 1e-9:
        raise ContractError("M3_OBJECTIVE_ACTION_ABOVE_U_MAX")
    total = 0.0
    for scenario in state_set.scenarios:
        if scenario.support is SupportState.ABSTAIN:
            raise ContractError(
                f"M3_OBJECTIVE_UNSUPPORTED_SCENARIO:{scenario.scenario_id}"
            )
        after = apply_recovery(scenario, context, u)
        value = consequence_value(
            after, service=service, node_id=state_set.node_id, view=view
        )
        total += scenario.scenario_weight * value
    if u_max > 0.0:
        total += float(lambda_policy) * float(u) / float(u_max)
    return total


def objective_by_grid(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    u_max: float,
    policy: RecoveryPolicy | None = None,
    floor_to_minutes: float = 5.0,
) -> tuple[tuple[float, float], ...]:
    """Exact ``(u, J(u))`` table over the complete finite grid."""

    active = (policy or RecoveryPolicy()).validate()
    grid = action_grid(u_max, floor_to_minutes=floor_to_minutes)
    return tuple(
        (
            u,
            expected_objective(
                state_set,
                context=context,
                service=service,
                u=u,
                u_max=u_max,
                lambda_policy=active.lambda_policy,
                view=active.aggregation_view,
            ),
        )
        for u in grid
    )


_NUMERICAL_TIE_DIAGNOSTIC_TOLERANCE = 1e-6


def _not_actionable_decision(state_set: StateScenarioSet) -> RecoveryDecision:
    return RecoveryDecision(
        episode_id=state_set.episode_id,
        chain_id=state_set.chain_id,
        node_id=state_set.node_id,
        representation_id=state_set.representation.representation_id,
        stage=state_set.stage,
        actionable_status=TypedStatus.NOT_ACTIONABLE,
        action_grid=(0.0,),
        u_star=0.0,
        solver_status=SolverStatus.NOT_RUN,
        tie_break_applied=False,
        near_tie_candidate_count=0,
        reason_codes=("M3_STAGE_NOT_ACTIONABLE_LOCAL_ACTION_SET_IS_ZERO",),
    )


def enumerate_recovery_decision(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary | None = None,
    policy: RecoveryPolicy | None = None,
) -> RecoveryDecision:
    """Independent exact oracle over the complete finite action grid."""

    active = (policy or RecoveryPolicy()).validate()
    if not is_actionable(state_set.stage):
        return _not_actionable_decision(state_set)
    if headroom_summary is None:
        raise ContractError("M3_HEADROOM_SUMMARY_REQUIRED_FOR_ACTIONABLE_STAGE")
    if abs(
        headroom_summary.turnaround_lower_bound_q - context.turnaround_lower_bound_minutes
    ) > _NUMERICAL_TIE_DIAGNOSTIC_TOLERANCE:
        raise ContractError("M3_TRANSITION_CONTEXT_HEADROOM_SUMMARY_MISMATCH")

    table = objective_by_grid(
        state_set,
        context=context,
        service=service,
        u_max=headroom_summary.u_max,
        policy=active,
        floor_to_minutes=headroom_summary.floor_to_minutes,
    )
    grid = tuple(u for u, _ in table)
    u_star, j_star = min(table, key=lambda item: (item[1], item[0]))
    j_zero = table[0][1]
    recoverable = j_zero - j_star
    near_tie_count = sum(
        1
        for _, objective in table
        if objective <= j_star + _NUMERICAL_TIE_DIAGNOSTIC_TOLERANCE
    )
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
        j_star=j_star,
        recoverable_value=recoverable,
        lambda_policy=active.lambda_policy,
        solver_status=SolverStatus.EXACT_ENUMERATION,
        tie_break_applied=near_tie_count > 1,
        near_tie_candidate_count=near_tie_count,
        reason_codes=tuple(reasons),
    )


def solve_recovery(
    state_set: StateScenarioSet,
    *,
    context: TransitionContext,
    service: M2ConsequenceService,
    headroom_summary: HeadroomSummary | None = None,
    policy: RecoveryPolicy | None = None,
    solver_backend: Callable[..., RecoveryDecision] | None = None,
) -> RecoveryDecision:
    """Solve Stage II with the frozen enumeration production authority.

    ``solver_backend`` is an internal injection point used by parity and
    reconciliation tooling to substitute a different backend (e.g. the
    Pyomo+HiGHS parity solver) without changing scientific inputs. Production
    callers leave it unset and always receive the exact-enumeration decision.
    """

    if not is_actionable(state_set.stage):
        return _not_actionable_decision(state_set)
    if solver_backend is not None:
        return solver_backend(
            state_set,
            context=context,
            service=service,
            headroom_summary=headroom_summary,
            policy=policy,
        )
    return enumerate_recovery_decision(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom_summary,
        policy=policy,
    )
