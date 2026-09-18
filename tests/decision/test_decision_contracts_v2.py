"""Tests for the shared V2 decision contracts (Phase 1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from model.common.decision_contracts import (
    ATTENTION_ACTIVATION_EVENTS,
    NOMINAL_COMMON_SUPPORT_MASS,
    PREDEFINED_COMMON_SUPPORT_SENSITIVITY,
    AttentionDecision,
    AttentionEntry,
    ComparisonSupport,
    ConsequenceComponentProfile,
    ConsequenceScenario,
    ConsequenceScenarioSet,
    DecisionEvaluation,
    EvaluationFamily,
    HeadroomSummary,
    HistoryScope,
    PrioritySignal,
    RecoveryDecision,
    SignalKind,
    SolverStatus,
    StateRepresentationSpec,
    StateScenario,
    StateScenarioSet,
    TemporalKind,
    TypedStatus,
    UncertaintyKind,
)
from model.common.enums import OperationalStage, SupportState


def _history_joint() -> StateRepresentationSpec:
    return StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )


def _point(temporal: TemporalKind = TemporalKind.CURRENT) -> StateRepresentationSpec:
    payload = dict(temporal=temporal, uncertainty=UncertaintyKind.POINT)
    if temporal is TemporalKind.HISTORY:
        payload.update(history_capacity=16, history_scope=HistoryScope.FULL_PREFIX)
    return StateRepresentationSpec(**payload)


def _scenario(scenario_id: int, weight: float, d_ob: float, d_tx: float) -> StateScenario:
    return StateScenario(
        scenario_id=scenario_id,
        scenario_weight=weight,
        stage=OperationalStage.POST_IB_PRE_OB,
        t_ib_minutes=0.0,
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        d_to_minutes=d_ob + d_tx,
        support=SupportState.SUPPORTED,
    )


def _scenario_set(spec: StateRepresentationSpec, scenarios) -> StateScenarioSet:
    return StateScenarioSet(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        stage=OperationalStage.POST_IB_PRE_OB,
        representation=spec,
        scenarios=scenarios,
    )


def test_representation_spec_encodes_temporal_and_uncertainty_dimensions():
    spec = _history_joint()
    assert spec.representation_id == "HISTORY_H16:JOINT"
    assert spec.temporal is TemporalKind.HISTORY
    assert _point().representation_id == "CURRENT:POINT"

    with pytest.raises(ValidationError):
        StateRepresentationSpec(
            temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=32,
            history_scope=HistoryScope.FULL_PREFIX,
        )
    with pytest.raises(ValidationError):
        StateRepresentationSpec(
            temporal=TemporalKind.CURRENT,
            uncertainty=UncertaintyKind.POINT,
            history_capacity=16,
        )
    with pytest.raises(ValidationError):
        StateRepresentationSpec(
            temporal=TemporalKind.HISTORY,
            uncertainty=UncertaintyKind.JOINT,
            history_capacity=16,
        )


def test_state_scenario_enforces_d_to_identity():
    with pytest.raises(ValidationError):
        StateScenario(
            scenario_id=0,
            scenario_weight=0.5,
            stage=OperationalStage.PRE_IB,
            d_ob_minutes=10.0,
            d_tx_minutes=5.0,
            d_to_minutes=99.0,
        )
    scenario = _scenario(0, 0.5, 10.0, 5.0)
    assert scenario.D_TO == pytest.approx(15.0)
    assert scenario.D_OB == pytest.approx(10.0)
    assert scenario.D_TX == pytest.approx(5.0)
    assert scenario.is_realized is False


def test_state_scenario_set_rejects_zero_weight_and_unnormalised_mass():
    balanced = (
        _scenario(0, 0.5, 1.0, 0.0),
        _scenario(1, 0.4, 2.0, 0.0),
        _scenario(2, 0.1, 3.0, 0.0),
    )
    assert sum(item.scenario_weight for item in balanced) == pytest.approx(1.0)
    assert _scenario_set(_point(), balanced)

    with pytest.raises(ValidationError):
        _scenario_set(
            _point(),
            (
                _scenario(0, 0.5, 1.0, 0.0),
                _scenario(1, 0.4, 2.0, 0.0),
                _scenario(2, 0.0, 3.0, 0.0),
            ),
        )

    with pytest.raises(ValidationError):
        _scenario_set(_point(), (_scenario(0, 0.5, 1.0, 0.0),))

    with pytest.raises(ValidationError):
        _scenario_set(
            _point(),
            (_scenario(0, 0.5, 1.0, 0.0), _scenario(0, 0.5, 2.0, 0.0)),
        )

    with pytest.raises(ValidationError):
        _scenario_set(_point(), ())


def test_realized_milestones_replace_uncertainty():
    realized = StateScenario(
        scenario_id=0,
        scenario_weight=1.0,
        stage=OperationalStage.POST_IB_PRE_OB,
        t_ib_minutes=32.0,
        d_ob_minutes=12.0,
        d_tx_minutes=8.0,
        d_to_minutes=20.0,
        ib_observed=True,
        ob_observed=True,
    )
    assert realized.is_realized is True
    collapsed = _scenario_set(_point(), (realized,))
    assert collapsed.scenarios[0].is_realized is True

    with pytest.raises(ValidationError):
        _scenario_set(
            _point(TemporalKind.HISTORY),
            (
                StateScenario(
                    scenario_id=0,
                    scenario_weight=0.5,
                    stage=OperationalStage.POST_IB_PRE_OB,
                    ib_observed=True,
                    ob_observed=True,
                ),
            ),
        )
    with pytest.raises(ValidationError):
        _scenario_set(
            _point(),
            (
                realized,
                StateScenario(
                    scenario_id=1,
                    scenario_weight=0.0,
                    stage=OperationalStage.POST_IB_PRE_OB,
                ),
            ),
        )


def test_comparison_support_threshold_is_typed():
    included = ComparisonSupport(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        rule_id="M2_COMPARISON_SUPPORT_MASS_V1",
        estimand="M2_COMPARISON_SUPPORT_CONDITIONAL",
        supported_mass=0.95,
        supported_scenario_ids=tuple(range(61)),
        scenario_count_total=64,
        threshold=NOMINAL_COMMON_SUPPORT_MASS,
        included=True,
        status=TypedStatus.SUPPORTED,
    )
    assert included.threshold == pytest.approx(0.90)

    excluded = ComparisonSupport(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        rule_id="M2_COMPARISON_SUPPORT_MASS_V1",
        estimand="M2_COMPARISON_SUPPORT_CONDITIONAL",
        supported_mass=0.50,
        supported_scenario_ids=tuple(range(32)),
        scenario_count_total=64,
        threshold=NOMINAL_COMMON_SUPPORT_MASS,
        included=False,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        reason_codes=("M2_COMPARISON_SUPPORT_BELOW_NOMINAL",),
    )
    assert excluded.supported_mass == pytest.approx(0.50)

    with pytest.raises(ValidationError):
        ComparisonSupport(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            rule_id="M2_COMPARISON_SUPPORT_MASS_V1",
            estimand="M2_COMPARISON_SUPPORT_CONDITIONAL",
            supported_mass=0.50,
            scenario_count_total=64,
            threshold=NOMINAL_COMMON_SUPPORT_MASS,
            included=True,
            status=TypedStatus.SUPPORTED,
        )

    with pytest.raises(ValidationError):
        ComparisonSupport(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            rule_id="M2_COMPARISON_SUPPORT_MASS_V1",
            estimand="M2_COMPARISON_SUPPORT_CONDITIONAL",
            supported_mass=0.50,
            scenario_count_total=64,
            threshold=NOMINAL_COMMON_SUPPORT_MASS,
            included=False,
            status=TypedStatus.SUPPORTED,
        )


def test_consequence_components_keep_missing_unsupported_and_zero_distinct():
    supported = ConsequenceComponentProfile(
        component_id="P_time",
        native_quantity=990.3555555555556,
        cu_quantity=1.0,
        support=SupportState.SUPPORTED,
        cu_status="CU_FROZEN",
        scale=990.3555555555556,
        scale_source="TRAIN_POSITIVE_MEDIAN",
        reference_source="M2_DATA2_FORMAL_CU_V5",
    )
    assert supported.cu_quantity == pytest.approx(1.0)

    zero = ConsequenceComponentProfile(
        component_id="P_itinerary",
        native_quantity=0.0,
        cu_quantity=0.0,
        support=SupportState.SUPPORTED,
        cu_status="CU_FROZEN",
        scale=1.0,
        scale_source="ASSUMPTION_EVENT_NORMALIZATION",
        reference_source="M2_DATA2_FORMAL_CU_V5",
    )
    assert zero.cu_quantity == 0.0

    with pytest.raises(ValidationError):
        ConsequenceComponentProfile(
            component_id="P_itinerary",
            native_quantity=12.0,
            cu_quantity=2.0,
            support=SupportState.SUPPORTED,
            cu_status="CU_FROZEN",
            scale=1.0,
            scale_source="ASSUMPTION_EVENT_NORMALIZATION",
            reference_source="M2_DATA2_FORMAL_CU_V5",
        )

    with pytest.raises(ValidationError):
        ConsequenceComponentProfile(
            component_id="P_itinerary",
            native_quantity=12.0,
            cu_quantity=12.0,
            support=SupportState.SUPPORTED,
            cu_status="CU_FROZEN",
            scale_source="ASSUMPTION_EVENT_NORMALIZATION",
            reference_source="M2_DATA2_FORMAL_CU_V5",
        )

    with pytest.raises(ValidationError):
        ConsequenceComponentProfile(
            component_id="P_service",
            native_quantity=None,
            cu_quantity=0.0,
            support=SupportState.ABSTAIN,
            cu_status="CU_ABSTAIN",
            scale=1.0,
            scale_source="ASSUMPTION_EVENT_NORMALIZATION",
            reference_source="M2_DATA2_FORMAL_CU_V5",
        )


def test_consequence_scenario_set_aligns_weights_and_priority():
    scenario = ConsequenceScenario(
        scenario_id=0,
        scenario_weight=1.0,
        native_components={"P_time": 0.0},
        cu_components={"P_time": 0.0},
        domain_scores={"passenger": 0.0},
        consequence_priority=0.0,
        support=SupportState.SUPPORTED,
    )
    scenario_set = ConsequenceScenarioSet(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        stage=OperationalStage.POST_IB_PRE_OB,
        representation=_history_joint(),
        registry_id="M2_DATA2_FORMAL_CU_V5",
        registry_hash="sha256:registry",
        scenarios=(scenario,),
    )
    assert scenario_set.scenarios[0].consequence_priority == 0.0

    with pytest.raises(ValidationError):
        ConsequenceScenario(
            scenario_id=0,
            scenario_weight=1.0,
            native_components={},
            cu_components={"P_time": 1.0},
        )

    with pytest.raises(ValidationError):
        ConsequenceScenario(
            scenario_id=0,
            scenario_weight=1.0,
            native_components={"P_time": None},
            cu_components={"P_time": None},
            consequence_priority=1.0,
            support=SupportState.ABSTAIN,
        )

    with pytest.raises(ValidationError):
        ConsequenceScenarioSet(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            stage=OperationalStage.POST_IB_PRE_OB,
            representation=_history_joint(),
            registry_id="M2_DATA2_FORMAL_CU_V5",
            registry_hash="sha256:registry",
            scenarios=(
                scenario,
                ConsequenceScenario(
                    scenario_id=1,
                    scenario_weight=0.5,
                    native_components={"P_time": 1.0},
                    support=SupportState.SUPPORTED,
                ),
            ),
        )


def test_priority_signal_types_abstention_and_common_support():
    signal = PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        representation_id="HISTORY_H16:JOINT",
        score=1.25,
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=0.95,
        comparison_support_threshold=NOMINAL_COMMON_SUPPORT_MASS,
    )
    assert signal.signal_type is SignalKind.CONSEQUENCE

    abstained = PrioritySignal(
        signal_type=SignalKind.DELAY,
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        representation_id="HISTORY_H16:JOINT",
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        reason_codes=("M2_COMPARISON_SUPPORT_BELOW_NOMINAL",),
    )
    assert abstained.score is None

    with pytest.raises(ValidationError):
        PrioritySignal(
            signal_type=SignalKind.DELAY,
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            score=3.0,
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
        )

    with pytest.raises(ValidationError):
        PrioritySignal(
            signal_type=SignalKind.DELAY,
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            score=3.0,
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.40,
            comparison_support_threshold=NOMINAL_COMMON_SUPPORT_MASS,
        )

    with pytest.raises(ValidationError):
        PrioritySignal(
            signal_type=SignalKind.DELAY,
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            score=3.0,
            support=SupportState.ABSTAIN,
            status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        )


def test_attention_decision_uses_one_shared_selector_contract():
    entry = AttentionEntry(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        score=3.14,
        rank=1,
        selected=True,
        selected_for=SignalKind.DELAY,
    )
    decision = AttentionDecision(
        signal_type=SignalKind.DELAY,
        q=0.10,
        k=1,
        cohort_size=1,
        entries=(entry,),
    )
    assert decision.entries[0].selected_for is SignalKind.DELAY
    assert decision.k == 1

    with pytest.raises(ValidationError):
        AttentionDecision(
            signal_type=SignalKind.CONSEQUENCE,
            q=0.10,
            k=1,
            cohort_size=1,
            entries=(entry,),
        )

    with pytest.raises(ValidationError):
        AttentionDecision(
            signal_type=SignalKind.DELAY,
            q=0.10,
            k=0,
            cohort_size=1,
            entries=(entry,),
        )


def test_headroom_summary_is_floor_to_grid():
    summary = HeadroomSummary(
        u_max=45.0,
        turnaround_lower_bound_q=32.0,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=1234,
        source_id="V2_TRAIN_SUPPORT_DEVELOPMENT",
    )
    assert summary.u_max == pytest.approx(45.0)

    with pytest.raises(ValidationError):
        HeadroomSummary(
            u_max=43.0,
            turnaround_lower_bound_q=32.0,
            turnaround_quantile=0.20,
            headroom_quantile=0.90,
            headroom_positive_n=1234,
            source_id="V2_TRAIN_SUPPORT_DEVELOPMENT",
        )


def test_recovery_decision_typed_paths_and_exact_enumeration():
    not_actionable = RecoveryDecision(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        representation_id="HISTORY_H16:JOINT",
        stage=OperationalStage.COMPLETED,
        actionable_status=TypedStatus.NOT_ACTIONABLE,
        action_grid=(0.0,),
        u_star=0.0,
        reason_codes=("M3_NOT_ACTIONABLE_AFTER_OFF_BLOCK",),
    )
    assert not_actionable.actionable_status is TypedStatus.NOT_ACTIONABLE

    actionable = RecoveryDecision(
        episode_id="sha256:episode",
        chain_id="sha256:chain",
        node_id="sha256:node",
        representation_id="HISTORY_H16:JOINT",
        stage=OperationalStage.POST_IB_PRE_OB,
        actionable_status=TypedStatus.SUPPORTED,
        action_grid=(0.0, 5.0, 10.0),
        u_max=10.0,
        u_star=5.0,
        j_zero=1.0,
        j_star=0.9,
        recoverable_value=0.1 + 1e-12,
        lambda_policy=0.25,
        solver_status=SolverStatus.EXACT_ENUMERATION,
    )
    assert actionable.recoverable_value == pytest.approx(0.1)

    with pytest.raises(ValidationError):
        RecoveryDecision(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            stage=OperationalStage.COMPLETED,
            actionable_status=TypedStatus.NOT_ACTIONABLE,
            action_grid=(0.0, 5.0),
            u_star=5.0,
        )

    with pytest.raises(ValidationError):
        RecoveryDecision(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            stage=OperationalStage.POST_IB_PRE_OB,
            actionable_status=TypedStatus.SUPPORTED,
            action_grid=(0.0, 5.0),
            u_max=5.0,
            u_star=7.5,
            j_zero=1.0,
            j_star=0.5,
            recoverable_value=0.5,
        )

    with pytest.raises(ValidationError):
        RecoveryDecision(
            episode_id="sha256:episode",
            chain_id="sha256:chain",
            node_id="sha256:node",
            representation_id="HISTORY_H16:JOINT",
            stage=OperationalStage.POST_IB_PRE_OB,
            actionable_status=TypedStatus.SUPPORTED,
            action_grid=(0.0, 5.0),
            u_max=5.0,
            u_star=5.0,
            j_zero=1.0,
            j_star=0.5,
            recoverable_value=0.9,
        )


def test_evaluation_keeps_attention_and_recovery_separate():
    evaluation = DecisionEvaluation(
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        cohort_id="DEVELOPMENT_H16",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=2.0,
        reference_attention_value=10.0,
        L_att=0.2,
    )
    assert evaluation.L_att == pytest.approx(0.2)

    undefined = DecisionEvaluation(
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        cohort_id="DEVELOPMENT_H16_ACTIONABLE",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=0.0,
        reference_recoverable_value=0.0,
        L_rec=None,
        value_status=TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE,
        activation_events={name: 0 for name in ATTENTION_ACTIVATION_EVENTS},
        A0=1.0,
        A5=1.0,
    )
    assert undefined.value_status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE

    with pytest.raises(ValidationError):
        DecisionEvaluation(
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            cohort_id="DEVELOPMENT_H16_ACTIONABLE",
            family=EvaluationFamily.RECOVERY,
            delta_recovery_objective=0.0,
            reference_recoverable_value=0.0,
            L_rec=0.0,
        )

    with pytest.raises(ValidationError):
        DecisionEvaluation(
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            cohort_id="DEVELOPMENT_H16",
            family=EvaluationFamily.ATTENTION,
            delta_attention_value=2.0,
            reference_attention_value=10.0,
            delta_recovery_objective=0.2,
            L_att=0.2,
        )

    with pytest.raises(ValidationError):
        DecisionEvaluation(
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            cohort_id="DEVELOPMENT_H16",
            family=EvaluationFamily.ATTENTION,
            delta_attention_value=1.0,
            reference_attention_value=10.0,
            L_att=0.5,
        )

    with pytest.raises(ValidationError):
        DecisionEvaluation(
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            cohort_id="DEVELOPMENT_H16",
            family=EvaluationFamily.ATTENTION,
            activation_events={"TOTAL_LOSS": 1},
        )

    assert "L_total" not in DecisionEvaluation.model_fields


def test_common_support_sensitivity_is_not_predefined_by_manuscript():
    assert NOMINAL_COMMON_SUPPORT_MASS == pytest.approx(0.90)
    assert PREDEFINED_COMMON_SUPPORT_SENSITIVITY == ()
