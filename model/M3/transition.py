"""M3 Stage-II action-conditioned state transition (Phase 3).

Manuscript section 4 transition, applied per scenario:

``AOBT^0 = SOBT + D_OB``,
``LB^OB = max(SOBT, T_IB + T^{turn,lb})``,
``H = [AOBT^0 - LB^OB]_+``,
``r(u) = min(u, H)``,
``AOBT(u) = AOBT^0 - r(u)``,
``D^OB(u) = max(AOBT(u) - SOBT, 0)``,
``T^IB(u) = T^IB(0)``, ``D^TX(u) = D^TX(0)``,
``D^TO(u) = D^OB(u) + D^TX(0)``.

The transition never touches taxi or the predecessor in-block state, and it
never reduces a consequence component directly: the post-action state is passed
through the same M2 consequence map as the baseline state.
"""

from __future__ import annotations

from pydantic import Field

from model.common.decision_contracts import StateScenario
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


__all__ = [
    "TransitionContext",
    "apply_recovery",
    "effective_recovery",
    "off_block_boundary",
    "scenario_headroom",
]


class TransitionContext(FrozenModel):
    """Node-level schedule and Train-derived turnaround boundary."""

    sobt_minutes: float
    turnaround_lower_bound_minutes: float = Field(ge=0.0)
    reference_id: str = Field(default="M3_TRAIN_TURNAROUND_LOWER_BOUND", min_length=1)


def _quantity(value: float | None, name: str, scenario_id: int) -> float:
    if value is None:
        raise ContractError(f"M3_TRANSITION_MISSING_QUANTITY:{scenario_id}:{name}")
    return float(value)


def off_block_boundary(
    state: StateScenario, context: TransitionContext
) -> float:
    """``LB^OB = max(SOBT, T_IB + T^{turn,lb})``."""

    t_ib = _quantity(state.t_ib_minutes, "T_IB", state.scenario_id)
    return max(
        context.sobt_minutes, t_ib + context.turnaround_lower_bound_minutes
    )


def scenario_headroom(state: StateScenario, context: TransitionContext) -> float:
    """``H = [AOBT^0 - LB^OB]_+`` with ``AOBT^0 = SOBT + D_OB``."""

    d_ob = _quantity(state.d_ob_minutes, "D_OB", state.scenario_id)
    aobt0 = context.sobt_minutes + d_ob
    return max(aobt0 - off_block_boundary(state, context), 0.0)


def effective_recovery(
    state: StateScenario, context: TransitionContext, u: float
) -> float:
    """``r(u) = min(u, H)``; proposed intensity is not the feasible amount."""

    if u < 0.0:
        raise ContractError("M3_TRANSITION_NEGATIVE_ACTION")
    return min(float(u), scenario_headroom(state, context))


def apply_recovery(
    state: StateScenario, context: TransitionContext, u: float
) -> StateScenario:
    """Return the post-action scenario state ``S(u)`` for one scenario."""

    d_ob = _quantity(state.d_ob_minutes, "D_OB", state.scenario_id)
    d_tx = _quantity(state.d_tx_minutes, "D_TX", state.scenario_id)
    d_ob_after = max(d_ob - effective_recovery(state, context, u), 0.0)
    return StateScenario(
        scenario_id=state.scenario_id,
        scenario_weight=state.scenario_weight,
        stage=state.stage,
        t_ib_minutes=state.t_ib_minutes,
        d_ob_minutes=d_ob_after,
        d_tx_minutes=d_tx,
        d_to_minutes=d_ob_after + d_tx,
        tx_reference_minutes=state.tx_reference_minutes,
        support=state.support,
        ib_observed=state.ib_observed,
        ob_observed=state.ob_observed,
        tx_observed=state.tx_observed,
    )
