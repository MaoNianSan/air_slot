"""M3 Stage-II transition, support, objective and parity tests (V2 Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from model.M2.consequence_service import (
    ConsequenceReferenceBinding,
    M2ConsequenceService,
    native_consequence_vector,
)
from model.M3.solver import solve_with_highs
from model.M3.stage2 import (
    LAMBDA_GRID,
    LAMBDA_NOMINAL,
    RecoveryPolicy,
    action_grid,
    expected_objective,
    objective_by_grid,
    solve_recovery,
)
from model.M3.support import (
    HEADROOM_QUANTILE_SENSITIVITY,
    TURNAROUND_QUANTILE_SENSITIVITY,
    TrainQuantileRule,
    build_headroom_summary,
    floor_to_grid,
    max_recovery_minutes,
    turnaround_lower_bound_minutes,
)
from model.M3.transition import (
    TransitionContext,
    apply_recovery,
    effective_recovery,
    off_block_boundary,
    scenario_headroom,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    HeadroomSummary,
    HistoryScope,
    SolverStatus,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState
from model.common.errors import ContractError


STAGE = OperationalStage.POST_IB_PRE_OB
TURN = OperationalStage.POST_IB_PRE_OB
PRE = OperationalStage.PRE_IB


@dataclass(frozen=True)
class _Registry:
    """Minimal CU registry contract used by the M2 consequence service."""

    scales: dict[str, float]
    registry_id: str = "TEST_CU_REGISTRY"
    registry_hash: str = "sha256:test-cu-registry"

    def scale(self, component: str) -> float:
        return self.scales[component]


def _scales(value: float = 1.0) -> dict[str, float]:
    return {component: value for component in CONSEQUENCE_COMPONENTS}


def _binding(**overrides) -> ConsequenceReferenceBinding:
    values = {
        "reference_id": "node-1",
        "turnaround_reference_minutes": 20.0,
        "taxi_reference_minutes": 0.0,
        "expected_pax": 100.0,
        "connection_share": 0.5,
        "downstream_exposure": 2.0,
        "itinerary_threshold_minutes": 45.0,
        "service_threshold_minutes": 180.0,
    }
    values.update(overrides)
    return ConsequenceReferenceBinding(**values)


def _service(
    *,
    node_id: str = "node-1",
    scale: float = 1.0,
    binding: ConsequenceReferenceBinding | None = None,
) -> M2ConsequenceService:
    return M2ConsequenceService(
        _Registry(_scales(scale)),
        {node_id: binding or _binding()},
    )


def _minimal_service(scale: float = 1.0) -> M2ConsequenceService:
    """Service isolating the F_execution + P_time objective terms."""

    return _service(
        scale=scale,
        binding=_binding(
            turnaround_reference_minutes=0.0,
            expected_pax=1.0,
            connection_share=0.0,
            downstream_exposure=0.0,
            itinerary_threshold_minutes=1000.0,
            service_threshold_minutes=1000.0,
        ),
    )


def _representation() -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _state(
    *,
    node_id: str = "node-1",
    stage: OperationalStage = STAGE,
    t_ib: float | None = 5.0,
    d_ob: float | None = 10.0,
    d_tx: float | None = 0.0,
    weight: float = 1.0,
    support: SupportState = SupportState.SUPPORTED,
) -> StateScenario:
    d_to = None
    if d_ob is not None and d_tx is not None:
        d_to = d_ob + d_tx
    return StateScenario(
        scenario_id=0,
        scenario_weight=weight,
        stage=stage,
        t_ib_minutes=t_ib,
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        d_to_minutes=d_to,
        support=support,
    )


def _state_set(
    *,
    node_id: str = "node-1",
    stage: OperationalStage = STAGE,
    t_ib: float | None = 5.0,
    d_ob: float | None = 10.0,
    d_tx: float | None = 0.0,
    support: SupportState = SupportState.SUPPORTED,
) -> StateScenarioSet:
    return StateScenarioSet(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id=node_id,
        stage=stage,
        representation=_representation(),
        scenarios=(
            _state(
                node_id=node_id,
                stage=stage,
                t_ib=t_ib,
                d_ob=d_ob,
                d_tx=d_tx,
                support=support,
            ),
        ),
    )


def _context(turnaround_lower_bound: float = 0.0) -> TransitionContext:
    return TransitionContext(
        sobt_minutes=0.0,
        turnaround_lower_bound_minutes=turnaround_lower_bound,
    )


def _headroom_summary(
    *, u_max: float = 10.0, turnaround_lower_bound_q: float = 0.0
) -> HeadroomSummary:
    return HeadroomSummary(
        u_max=u_max,
        turnaround_lower_bound_q=turnaround_lower_bound_q,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id="TEST_TRAIN_SUPPORT",
        floor_to_minutes=5.0,
    )


# ---------------------------------------------------------------------------
# Native consequence callback
# ---------------------------------------------------------------------------


def test_native_consequence_formulas_follow_section_4() -> None:
    state = _state(t_ib=60.0, d_ob=50.0, d_tx=10.0)
    native = native_consequence_vector(state, _binding())
    assert native == {
        "F_continuity": 40.0,
        "F_execution": 50.0,
        "F_propagation": 120.0,
        "P_time": 6000.0,
        "P_itinerary": 50.0,
        "P_service": 0.0,
        "R_operating": 10.0,
    }


def test_cu_mapping_uses_registry_scales() -> None:
    service = _service(scale=2.0)
    state = _state(t_ib=60.0, d_ob=50.0, d_tx=10.0)
    scenario = service.consequence_scenario(state, node_id="node-1")
    assert scenario.native_components == {
        "F_continuity": 40.0,
        "F_execution": 50.0,
        "F_propagation": 120.0,
        "P_time": 6000.0,
        "P_itinerary": 50.0,
        "P_service": 0.0,
        "R_operating": 10.0,
    }
    assert scenario.cu_components == {
        "F_continuity": 20.0,
        "F_execution": 25.0,
        "F_propagation": 60.0,
        "P_time": 3000.0,
        "P_itinerary": 25.0,
        "P_service": 0.0,
        "R_operating": 5.0,
    }


def test_native_consequence_requires_state_quantities() -> None:
    service = _service()
    state = _state(d_ob=None, d_tx=10.0)
    with pytest.raises(ContractError, match="M2_CONSEQUENCE_MISSING_STATE_QUANTITY"):
        service.consequence_scenario(state, node_id="node-1")


def test_native_consequence_requires_binding() -> None:
    service = M2ConsequenceService(_Registry(_scales()), {})
    with pytest.raises(ContractError, match="M2_CONSEQUENCE_REFERENCE_MISSING"):
        service.consequence_scenario(_state(), node_id="node-1")


def test_d_to_identity_is_enforced_at_contract_boundary() -> None:
    with pytest.raises(ValidationError, match="STATE_SCENARIO_D_TO_IDENTITY_VIOLATION"):
        StateScenario(
            scenario_id=0,
            scenario_weight=1.0,
            stage=STAGE,
            t_ib_minutes=5.0,
            d_ob_minutes=50.0,
            d_tx_minutes=10.0,
            d_to_minutes=99.0,
        )


# ---------------------------------------------------------------------------
# Transition and Train-derived support
# ---------------------------------------------------------------------------


def test_transition_invariants() -> None:
    state = _state(t_ib=30.0, d_ob=40.0, d_tx=10.0)
    context = TransitionContext(
        sobt_minutes=100.0, turnaround_lower_bound_minutes=20.0
    )
    assert off_block_boundary(state, context) == 100.0
    assert scenario_headroom(state, context) == 40.0
    assert effective_recovery(state, context, 25.0) == 25.0
    assert effective_recovery(state, context, 60.0) == 40.0
    after = apply_recovery(state, context, 25.0)
    assert after.t_ib_minutes == state.t_ib_minutes
    assert after.d_tx_minutes == state.d_tx_minutes
    assert after.d_ob_minutes == 15.0
    assert after.d_to_minutes == after.d_ob_minutes + after.d_tx_minutes
    assert after.d_to_minutes == 25.0


def test_headroom_is_zero_when_off_block_boundary_binds() -> None:
    state = _state(t_ib=90.0, d_ob=10.0, d_tx=0.0)
    context = TransitionContext(
        sobt_minutes=100.0, turnaround_lower_bound_minutes=20.0
    )
    assert scenario_headroom(state, context) == 0.0
    after = apply_recovery(state, context, 30.0)
    assert after.d_ob_minutes == 10.0
    assert after.d_to_minutes == 10.0


def test_negative_recovery_is_rejected() -> None:
    with pytest.raises(ContractError, match="M3_TRANSITION_NEGATIVE_ACTION"):
        effective_recovery(_state(), _context(), -1.0)


def test_train_quantiles_follow_linear_interpolation_and_predefined_grid() -> None:
    assert turnaround_lower_bound_minutes([10.0, 20.0, 30.0, 40.0]) == 16.0
    assert (
        turnaround_lower_bound_minutes([10.0, 20.0, 30.0, 40.0], quantile=0.10)
        == 13.0
    )
    assert (
        turnaround_lower_bound_minutes([10.0, 20.0, 30.0, 40.0], quantile=0.30)
        == 19.0
    )
    assert TURNAROUND_QUANTILE_SENSITIVITY == (0.10, 0.30)
    assert HEADROOM_QUANTILE_SENSITIVITY == (0.80, 0.95)
    with pytest.raises(ContractError, match="M3_TURNAROUND_QUANTILE_OUTSIDE"):
        turnaround_lower_bound_minutes([10.0, 20.0], quantile=0.50)
    with pytest.raises(ContractError, match="M3_HEADROOM_QUANTILE_OUTSIDE"):
        TrainQuantileRule(headroom_quantile=0.50).validate()


def test_umax_uses_only_positive_headroom_and_floor_to_five() -> None:
    assert floor_to_grid(37.0) == 35.0
    assert max_recovery_minutes([10.0, 20.0, 30.0, 40.0]) == 35.0
    assert max_recovery_minutes([-5.0, 0.0, 10.0, 20.0]) == 15.0
    with pytest.raises(ContractError, match="M3_NO_POSITIVE_TRAIN_HEADROOM"):
        max_recovery_minutes([0.0, -1.0])


def test_headroom_summary_materialization() -> None:
    summary = build_headroom_summary(
        turnaround_minutes=[10.0, 20.0, 30.0, 40.0],
        headroom_minutes=[5.0, 10.0, 20.0, 40.0],
        source_id="UNIT_TEST_TRAIN_SAMPLE",
    )
    assert summary.u_max == 30.0
    assert summary.turnaround_lower_bound_q == 16.0
    assert summary.turnaround_quantile == 0.20
    assert summary.headroom_quantile == 0.90
    assert summary.headroom_positive_n == 4


# ---------------------------------------------------------------------------
# Stage-II objective and decision
# ---------------------------------------------------------------------------


def test_action_grid_is_finite_and_floor_aligned() -> None:
    assert action_grid(10.0) == (0.0, 5.0, 10.0)
    assert action_grid(0.0) == (0.0,)
    with pytest.raises(ContractError, match="M3_ACTION_GRID_U_MAX_NOT_ON_FLOOR_GRID"):
        action_grid(12.0)


def test_objective_has_effort_term_and_rejects_above_umax() -> None:
    service = _minimal_service()
    state_set = _state_set()
    context = _context()
    j0 = expected_objective(
        state_set, context=context, service=service, u=0.0, u_max=10.0
    )
    j5 = expected_objective(
        state_set, context=context, service=service, u=5.0, u_max=10.0
    )
    assert j5 == pytest.approx(j0 - 2.0 * 5.0 / 9.0 + 0.25 * 5.0 / 10.0)
    with pytest.raises(ContractError, match="M3_OBJECTIVE_ACTION_ABOVE_U_MAX"):
        expected_objective(
            state_set, context=context, service=service, u=15.0, u_max=10.0
        )
    with pytest.raises(ContractError, match="M3_OBJECTIVE_POSITIVE_ACTION_WITH_ZERO"):
        expected_objective(
            state_set, context=context, service=service, u=5.0, u_max=0.0
        )


def test_objective_rejects_abstaining_scenario() -> None:
    service = _minimal_service()
    state_set = _state_set(support=SupportState.ABSTAIN)
    with pytest.raises(ContractError, match="M3_OBJECTIVE_UNSUPPORTED_SCENARIO"):
        expected_objective(
            state_set, context=_context(), service=service, u=0.0, u_max=10.0
        )


def test_stage2_selects_interior_breakpoint_and_reports_recoverable_value() -> None:
    service = _minimal_service(scale=1.0)
    state_set = _state_set(t_ib=5.0, d_ob=10.0)
    decision = solve_recovery(
        state_set,
        context=_context(),
        service=service,
        headroom_summary=_headroom_summary(),
    )
    assert decision.actionable_status is TypedStatus.SUPPORTED
    assert decision.solver_status is SolverStatus.PYOMO_HIGHS
    assert decision.action_grid == (0.0, 5.0, 10.0)
    assert decision.u_star == 5.0
    assert decision.j_star is not None
    assert decision.j_zero is not None
    assert decision.recoverable_value == pytest.approx(
        decision.j_zero - decision.j_star
    )
    assert decision.recoverable_value > 0.0
    assert "M3_A00_BASELINE_NEVER_A_RECOMMENDATION" in decision.reason_codes
    assert "M3_LOCAL_RECOVERY_SELECTED" in decision.reason_codes


def test_stage2_tie_prefers_smaller_action_and_keeps_a00_as_baseline() -> None:
    # 2 / (9 * S) == lambda / U_max at S = 8.888..., so u = 0 and u = 5 tie.
    service = _minimal_service(scale=8.88888888888889)
    decision = solve_recovery(
        _state_set(t_ib=5.0, d_ob=10.0),
        context=_context(),
        service=service,
        headroom_summary=_headroom_summary(),
    )
    assert decision.u_star == 0.0
    assert decision.recoverable_value == pytest.approx(0.0, abs=1e-12)
    assert "M3_A00_BASELINE_NEVER_A_RECOMMENDATION" in decision.reason_codes
    assert "M3_BASELINE_ACTION_SELECTED_NO_NEW_INTERVENTION" in decision.reason_codes


def test_stage2_zero_umax_returns_baseline_only() -> None:
    decision = solve_recovery(
        _state_set(t_ib=5.0, d_ob=10.0),
        context=_context(),
        service=_minimal_service(),
        headroom_summary=_headroom_summary(u_max=0.0),
    )
    assert decision.action_grid == (0.0,)
    assert decision.u_star == 0.0
    assert decision.recoverable_value == pytest.approx(0.0)
    assert "M3_ZERO_TRAIN_U_MAX" in decision.reason_codes


def test_actionable_stage_requires_matching_headroom_summary() -> None:
    with pytest.raises(ContractError, match="M3_HEADROOM_SUMMARY_REQUIRED"):
        solve_recovery(
            _state_set(),
            context=_context(),
            service=_minimal_service(),
        )
    with pytest.raises(
        ContractError, match="M3_TRANSITION_CONTEXT_HEADROOM_SUMMARY_MISMATCH"
    ):
        solve_recovery(
            _state_set(),
            context=_context(turnaround_lower_bound=7.0),
            service=_minimal_service(),
            headroom_summary=_headroom_summary(turnaround_lower_bound_q=0.0),
        )


@pytest.mark.parametrize(
    "stage",
    (OperationalStage.POST_OB_PRE_TO, OperationalStage.COMPLETED),
)
def test_taxi_and_completed_stages_have_zero_action_set(
    stage: OperationalStage,
) -> None:
    decision = solve_recovery(
        _state_set(stage=stage),
        context=_context(),
        service=_service(),
    )
    assert decision.actionable_status is TypedStatus.NOT_ACTIONABLE
    assert decision.action_grid == (0.0,)
    assert decision.u_star == 0.0
    assert decision.recoverable_value is None
    assert decision.solver_status is SolverStatus.NOT_RUN
    assert decision.reason_codes == (
        "M3_STAGE_NOT_ACTIONABLE_LOCAL_ACTION_SET_IS_ZERO",
    )


def test_recovery_policy_grid_is_manuscript_predefined() -> None:
    assert LAMBDA_NOMINAL == 0.25
    assert LAMBDA_GRID == (0.10, 0.25, 0.50, 1.00)
    with pytest.raises(ContractError, match="M3_LAMBDA_OUTSIDE_MANUSCRIPT_GRID"):
        RecoveryPolicy(lambda_policy=0.20).validate()


def test_objective_table_is_complete_and_sorted() -> None:
    table = objective_by_grid(
        _state_set(),
        context=_context(),
        service=_minimal_service(),
        u_max=10.0,
    )
    assert tuple(u for u, _ in table) == (0.0, 5.0, 10.0)


# ---------------------------------------------------------------------------
# Enumeration / HiGHS parity
# ---------------------------------------------------------------------------


def test_highs_parity_matches_enumeration_on_interior_case() -> None:
    result = solve_with_highs(
        _state_set(),
        context=_context(),
        service=_minimal_service(),
        headroom_summary=_headroom_summary(),
    )
    assert result.formal_solver == SolverStatus.PYOMO_HIGHS.value
    assert result.parity_oracle == SolverStatus.EXACT_ENUMERATION.value
    assert result.u_star_formal == result.u_star_oracle == 5.0
    assert result.objective_parity
    assert result.u_star_parity
    assert result.recoverable_value_parity
    assert result.objective_absolute_error <= 1e-6
    assert result.recoverable_value_absolute_error <= 1e-6
    assert not result.tie_break_applied
    assert result.near_tie_candidate_count == 1


def test_highs_parity_keeps_smaller_action_on_tie() -> None:
    result = solve_with_highs(
        _state_set(),
        context=_context(),
        service=_minimal_service(scale=8.88888888888889),
        headroom_summary=_headroom_summary(),
    )
    assert result.u_star_oracle == 0.0
    assert result.u_star_formal == 0.0
    assert result.u_star_parity
    assert result.objective_parity
    assert result.tie_break_applied
    assert result.near_tie_candidate_count >= 2


def test_highs_parity_rejects_non_actionable_stage() -> None:
    with pytest.raises(
        ContractError, match="M3_HIGHS_REQUIRES_ACTIONABLE_STAGE"
    ):
        solve_with_highs(
            _state_set(stage=OperationalStage.POST_OB_PRE_TO),
            context=_context(),
            service=_service(),
            headroom_summary=_headroom_summary(),
        )
