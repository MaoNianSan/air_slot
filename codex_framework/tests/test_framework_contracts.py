from datetime import datetime, timezone

import pytest

from codex_framework.air_slot_framework.action_response import (
    ActionEligibility,
    ActionResponseRule,
    ActionTemplate,
    EligibilityState,
    ResponseParameter,
    ResponseSupport,
    materialize_action,
)
from codex_framework.air_slot_framework.contracts import (
    CONSEQUENCE_COMPONENTS,
    ConsequenceScenario,
    HistoryConditionedState,
    NativeConsequenceComponent,
    OperationalInformation,
    SupportState,
)
from codex_framework.air_slot_framework.experiments import (
    ExperimentStage,
    SafetyState,
    build_experiment_manifest,
    validate_representation_isolation,
)
from codex_framework.air_slot_framework.workflow import build_development_workflow_manifest
from codex_framework.air_slot_framework.pipeline import DecisionChainInput, run_decision_chain
from codex_framework.air_slot_framework.risk import (
    MappingStatus,
    RMBMappingRule,
    ResidualRiskPolicy,
    RiskEvaluationStatus,
    RiskPolicyStatus,
    TailSupport,
    evaluate_residual_risk,
)


def _scenario(*, unsupported: set[str] = set()):
    components = []
    for component_id in CONSEQUENCE_COMPONENTS:
        if component_id in unsupported:
            components.append(
                NativeConsequenceComponent(
                    component_id=component_id,
                    q_value=None,
                    native_unit="unit",
                    support_state=SupportState.ABSTAIN,
                    reference_lineage=("synthetic",),
                    reason_code="UNSUPPORTED_SYNTHETIC",
                )
            )
        else:
            components.append(
                NativeConsequenceComponent(
                    component_id=component_id,
                    q_value=1.0,
                    native_unit="unit",
                    support_state=SupportState.SUPPORTED,
                    train_positive_median=1.0,
                    reference_lineage=("synthetic",),
                )
            )
    return ConsequenceScenario.from_native(
        episode_id="e1",
        decision_node_id="n1",
        scenario_id=0,
        scenario_weight=1.0,
        components=tuple(components),
    )


def _eligibility(action_id: str):
    return ActionEligibility.create(
        action_id=action_id,
        action_family="baseline" if action_id == "A00" else "reroute",
        decision_node_id="n1",
        state=EligibilityState.ELIGIBLE,
        conditions=("synthetic",),
        fact_references=("synthetic_fact",),
        provenance=("synthetic",),
    )


def _a00_rule():
    return ActionResponseRule.create(
        response_rule_id="rule-a00",
        action_id="A00",
        action_family="baseline",
        support=ResponseSupport.SUPPORTED,
        response_model="IDENTITY",
        affected_components=(),
        source_references=("synthetic_identity",),
        parameter_version="v1",
        freeze_id="freeze1",
        provenance=("synthetic",),
    )


def _conditional_rule():
    params = tuple(
        ResponseParameter(
            parameter_name=name,
            value=value,
            unit="ratio",
            source_reference="synthetic_assumption",
            parameter_version="v1",
            freeze_id="freeze1",
        )
        for name, value in (("mean_intensity", 0.8), ("induced_score_to_cu", 1.0))
    )
    return ActionResponseRule.create(
        response_rule_id="rule-a11",
        action_id="A11",
        action_family="reroute",
        support=ResponseSupport.SCENARIO_ASSUMPTION,
        response_model="DETERMINISTIC",
        affected_components=("F_execution",),
        source_references=("synthetic_assumption",),
        parameter_version="v1",
        freeze_id="freeze1",
        parameters=params,
        provenance=("synthetic",),
    )


def test_information_cutoff_and_cu_median_and_abstain():
    with pytest.raises(ValueError, match="E_INFORMATION_CUTOFF_AFTER_DECISION_TIME"):
        OperationalInformation(
            episode_id="e1",
            decision_node_id="n1",
            decision_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            information_cutoff=datetime(2026, 1, 2, tzinfo=timezone.utc),
            current_information={},
            admissible_history=(),
            provenance=("synthetic",),
        )
    scenario = _scenario(unsupported={"P_service"})
    assert scenario.cu_components[0].value_cu == 1.0
    assert scenario.cu_components[-2].support_state is SupportState.ABSTAIN
    assert scenario.cu_components[-2].value_cu is None


def test_a00_identity_and_non_a00_reproducible_conditional_response():
    baseline = _scenario()
    a00 = ActionTemplate(
        action_id="A00", action_family="baseline", affected_components=(), mitigation={}, induced={},
        literature_references=("synthetic",), operational_constraints=("none",),
    )
    identity = materialize_action(
        baseline=baseline, eligibility=_eligibility("A00"), action=a00, response_rule=_a00_rule(), seed=7
    )
    assert identity.status == "IDENTITY"
    assert [x.value_cu for x in identity.scenarios[0].components] == [x.value_cu for x in baseline.cu_components]

    action = ActionTemplate(
        action_id="A11", action_family="reroute", affected_components=("F_execution",),
        mitigation={"F_execution": 0.5}, induced={}, literature_references=("synthetic",),
        operational_constraints=("synthetic",),
    )
    first = materialize_action(
        baseline=baseline, eligibility=_eligibility("A11"), action=action, response_rule=_conditional_rule(), seed=11
    )
    second = materialize_action(
        baseline=baseline, eligibility=_eligibility("A11"), action=action, response_rule=_conditional_rule(), seed=11
    )
    assert first.scenarios[0].response_draw_id == second.scenarios[0].response_draw_id
    assert first.response_support is ResponseSupport.SCENARIO_ASSUMPTION
    assert first.produces_rmb is False and first.produces_ranking is False

    with pytest.raises(ValueError, match="NON_A00_REQUIRES_EXPLICIT_ELIGIBILITY"):
        materialize_action(
            baseline=baseline,
            eligibility=_eligibility("A11").model_copy(update={"state": EligibilityState.UNKNOWN}),
            action=action,
            response_rule=_conditional_rule(),
            seed=11,
        )


def test_risk_gates_and_tail_support():
    baseline = _scenario()
    action = ActionTemplate(
        action_id="A00", action_family="baseline", affected_components=(), mitigation={}, induced={},
        literature_references=("synthetic",), operational_constraints=("none",),
    )
    materialized = materialize_action(
        baseline=baseline, eligibility=_eligibility("A00"), action=action, response_rule=_a00_rule(), seed=0
    )
    conditional = evaluate_residual_risk(
        materialization=materialized,
        mapping=RMBMappingRule(mapping_id="m", mapping_status=MappingStatus.TEST_ONLY),
        policy=ResidualRiskPolicy(policy_id="p", policy_status=RiskPolicyStatus.TEST_ONLY, tail_support=TailSupport.SUPPORTED),
    )
    assert conditional.status is RiskEvaluationStatus.CONDITIONAL
    assert conditional.ranking_allowed is False
    unresolved_tail = evaluate_residual_risk(
        materialization=materialized,
        mapping=RMBMappingRule(mapping_id="m", mapping_status=MappingStatus.FROZEN),
        policy=ResidualRiskPolicy(policy_id="p", policy_status=RiskPolicyStatus.FROZEN, tail_support=TailSupport.UNRESOLVED),
    )
    assert unresolved_tail.status is RiskEvaluationStatus.CONDITIONAL
    assert unresolved_tail.expected_loss is None
    assert unresolved_tail.conditional_value_at_risk is None
    assert unresolved_tail.ranking_allowed is False
    supported = evaluate_residual_risk(
        materialization=materialized,
        mapping=RMBMappingRule(mapping_id="m", mapping_status=MappingStatus.FROZEN),
        policy=ResidualRiskPolicy(policy_id="p", policy_status=RiskPolicyStatus.FROZEN, tail_support=TailSupport.SUPPORTED),
    )
    assert supported.status is RiskEvaluationStatus.EVALUATED
    abstain_materialized = materialize_action(
        baseline=_scenario(unsupported={"P_service"}),
        eligibility=_eligibility("A00"), action=action, response_rule=_a00_rule(), seed=0,
    )
    abstained = evaluate_residual_risk(
        materialization=abstain_materialized,
        mapping=RMBMappingRule(mapping_id="m", mapping_status=MappingStatus.FROZEN),
        policy=ResidualRiskPolicy(policy_id="p", policy_status=RiskPolicyStatus.FROZEN, tail_support=TailSupport.SUPPORTED),
    )
    assert abstained.status is RiskEvaluationStatus.ABSTAINED


def test_experiment_safety_and_coarse_isolation():
    manifest = build_experiment_manifest(
        stage=ExperimentStage.EXP2,
        variant="EXP2B_SCALAR",
        source_artifact={"source": "synthetic"},
        split="DEVELOPMENT",
        seed=1,
    )
    assert manifest.safety.final_test_access_count == 0
    with pytest.raises(ValueError, match="HIDDEN_7COMPONENT"):
        validate_representation_isolation(variant="EXP2B_SCALAR", source_payload={"hidden_7_component_values": [1]})
    with pytest.raises(ValueError):
        SafetyState(formal_execution_authorized=True)


def test_workflow_stops_formal_experiments():
    manifest = build_development_workflow_manifest()
    assert manifest.formal_experiments_run is False
    assert manifest.paper_full_run is False
    assert manifest.safety.final_test_access_count == 0
    assert {item.stage_id for item in manifest.stages if item.status.value == "BLOCKED"} == {"W3", "W4", "W5", "W6"}


def test_end_to_end_chain_stops_at_conditional_decision():
    baseline = _scenario()
    info = OperationalInformation(
        episode_id="e1",
        decision_node_id="n1",
        decision_time=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        information_cutoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        current_information={"delay": 10},
        admissible_history=({"delay": 5},),
        provenance=("synthetic",),
    )
    state = HistoryConditionedState(
        episode_id="e1",
        decision_node_id="n1",
        information_hash=info.information_hash,
        history_mode="ADAPTIVE_HISTORY",
        state_provenance=("synthetic",),
        consequence_scenarios=(baseline,),
    )
    action = ActionTemplate(
        action_id="A00", action_family="baseline", affected_components=(), mitigation={}, induced={},
        literature_references=("synthetic",), operational_constraints=("none",),
    )
    output = run_decision_chain(
        DecisionChainInput(
            information=info,
            state=state,
            actions=(action,),
            eligibilities=(_eligibility("A00"),),
            response_rules=(_a00_rule(),),
            mapping=RMBMappingRule(mapping_id="m", mapping_status=MappingStatus.TEST_ONLY),
            risk_policy=ResidualRiskPolicy(policy_id="p", policy_status=RiskPolicyStatus.TEST_ONLY, tail_support=TailSupport.SUPPORTED),
        )
    )
    assert output.decision_action_id is None
    assert output.decision_status == "CONDITIONAL_NO_AUTHORITATIVE_RANKING"
    assert output.final_test_access_count == 0
