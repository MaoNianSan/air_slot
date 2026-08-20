import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from model.M3.action_response import ResponseSourceType, ResponseSupportClass
from model.M4.m3_action_interface import M4ActionEnvelopeInput
from model.M4.residual_risk import (
    M1_POSITIVE_TAIL_DECISION_REQUIRED,
    RankingAuthority,
    ResidualRiskPolicy,
    RiskEvaluationSupport,
    RiskPolicyStatus,
    TailSupportState,
    evaluate_residual_risk,
    rank_risk_evaluations,
    weighted_expectation,
    weighted_var_cvar,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import ContractError
from model.common.monetary_system import (
    MonetaryMappingFunction,
    MonetaryMappingParameter,
    MonetaryMappingRegistry,
    MonetaryMappingRule,
    MonetaryMappingStatus,
    MonetarySourceType,
)


def _hash(character):
    return f"sha256:{character * 64}"


def _action_input(
    *,
    action_id="A00",
    response_support=ResponseSupportClass.SUPPORTED,
    scenario_values=(1.0, 3.0),
    scenario_weights=(0.25, 0.75),
):
    scenario_ids = tuple(range(len(scenario_values)))
    scenarios = tuple(
        {
            "scenario_id": scenario_id,
            "scenario_weight": weight,
            "components": tuple(
                {
                    "component_id": component,
                    "C_a_CU": value,
                    "support_state": "SUPPORTED",
                    "baseline_cu_artifact_id": _hash("a"),
                    "baseline_reference_lineage_hash": _hash(
                        str((index + scenario_id) % 10)
                    ),
                }
                for index, component in enumerate(CONSEQUENCE_COMPONENTS)
            ),
        }
        for scenario_id, (value, weight) in enumerate(
            zip(scenario_values, scenario_weights, strict=True)
        )
    )
    return M4ActionEnvelopeInput(
        episode_id="episode-v2",
        decision_node_id="node-v2",
        action_id=action_id,
        action_family="null" if action_id == "A00" else "test-action",
        eligibility_state="ELIGIBLE",
        eligibility_id=_hash("b"),
        response_support=response_support,
        response_rule_id=f"M3_V2_{action_id}",
        response_rule_hash=_hash("c"),
        response_source_type=(
            ResponseSourceType.OPERATIONAL_RULE
            if response_support is ResponseSupportClass.SUPPORTED
            else ResponseSourceType.SCENARIO_ASSUMPTION
        ),
        response_source_references=(f"TEST:{action_id}",),
        response_parameter_version="TEST-M3-1",
        response_freeze_id="TEST-M3-FREEZE",
        response_provenance=("TEST_M3_PROVENANCE",),
        scenario_ids=scenario_ids,
        scenario_weights=scenario_weights,
        scenario_consequences=scenarios,
        m3_envelope_hash=_hash("d"),
    )


def _mapping(
    *,
    system="TEST-M1",
    scale=1.0,
    version="1.0.0",
    status=MonetaryMappingStatus.TEST_ONLY,
):
    source = (
        MonetarySourceType.TEST_ONLY
        if status is MonetaryMappingStatus.TEST_ONLY
        else MonetarySourceType.OPERATIONAL_RULE
    )
    freeze_id = f"TEST-FREEZE-{system}-{version}"
    rules = {
        component: MonetaryMappingRule.create(
            monetary_system_id=system,
            component_id=component,
            mapping_function=MonetaryMappingFunction.LINEAR_SCALE,
            parameter_version=version,
            source_type=source,
            reference=("TEST_SYNTHETIC_MAPPING_NOT_SCIENTIFIC",),
            freeze_id=freeze_id,
            parameters=(
                MonetaryMappingParameter(
                    parameter_name="money_per_cu",
                    value=scale,
                    unit=f"{system}/CU",
                    provenance=("TEST_ONLY",),
                ),
            ),
            provenance=("TEST_ONLY",),
            rule_id=f"{system}:{component}:{version}",
        )
        for component in CONSEQUENCE_COMPONENTS
    }
    return MonetaryMappingRegistry(
        monetary_system_id=system,
        registry_id=f"TEST-{system}-{version}",
        registry_version=version,
        freeze_status=status,
        freeze_id=freeze_id,
        reference_period="TEST",
        component_mappings=rules,
        provenance=("TEST_ONLY",),
    )


def _policy(
    *,
    status=RiskPolicyStatus.TEST_ONLY,
    tail=TailSupportState.SUPPORTED,
):
    return ResidualRiskPolicy.create(
        alpha=0.75,
        expected_loss_coefficient=0.5,
        cvar_coefficient=0.5,
        risk_metric_version="TEST-MEAN-CVAR-1",
        policy_status=status,
        freeze_id=(None if status is RiskPolicyStatus.NOT_FROZEN else "TEST-RISK-FREEZE"),
        tail_support_state=tail,
        tail_reference=(
            M1_POSITIVE_TAIL_DECISION_REQUIRED
            if tail is TailSupportState.UNRESOLVED
            else "TEST_TAIL_SUPPORT"
        ,),
        provenance=("TEST_ONLY",),
    )


def test_1_m4_v2_rejects_raw_operational_variables():
    payload = _action_input().model_dump()
    with pytest.raises(ValidationError):
        M4ActionEnvelopeInput.model_validate(
            {**payload, "D_OB": 20.0, "weather": "future"}
        )
    with pytest.raises(TypeError, match="ACTION_EVALUATION_ENVELOPE"):
        evaluate_residual_risk(
            payload, monetary_mapping=_mapping(), risk_policy=_policy()
        )


def test_2_m4_v2_consumes_only_action_conditioned_cu():
    result = evaluate_residual_risk(
        _action_input(), monetary_mapping=_mapping(), risk_policy=_policy()
    )
    assert result.scenario_ids == (0, 1)
    assert all(
        component.C_a_CU is not None
        for scenario in result.scenario_losses
        for component in scenario.component_losses
    )


def test_3_same_cu_different_monetary_system_changes_only_loss():
    envelope = _action_input()
    before = envelope.model_dump()
    first = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(system="TEST-M1", scale=1), risk_policy=_policy()
    )
    second = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(system="TEST-M2", scale=2), risk_policy=_policy()
    )
    assert first.scenario_ids == second.scenario_ids == envelope.scenario_ids
    assert first.action_id == second.action_id == envelope.action_id
    assert first.expected_monetary_loss * 2 == second.expected_monetary_loss
    assert envelope.model_dump() == before


def test_4_mapping_version_changes_loss_artifact_identity():
    envelope = _action_input()
    first = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(version="1.0.0"), risk_policy=_policy()
    )
    second = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(version="2.0.0"), risk_policy=_policy()
    )
    assert first.monetary_mapping_registry_hash != second.monetary_mapping_registry_hash
    assert first.scenario_losses[0].loss_artifact_id != second.scenario_losses[0].loss_artifact_id


def test_5_every_mapping_has_named_parameter_and_provenance():
    mapping = _mapping()
    assert all(
        rule.monetary_system_id
        and rule.mapping_function
        and rule.parameter_version
        and rule.source_type
        and rule.reference
        and rule.freeze_id
        and rule.provenance
        and tuple(parameter.parameter_name for parameter in rule.parameters)
        == ("money_per_cu",)
        for rule in mapping.component_mappings.values()
    )
    with pytest.raises(ValidationError):
        MonetaryMappingRule.model_validate(
            {**next(iter(mapping.component_mappings.values())).model_dump(), "weight": 3}
        )
    root = Path(__file__).resolve().parents[2]
    design = json.loads(
        (root / "registries" / "m4_v2_monetary_mapping_design.json").read_text(
            encoding="utf-8"
        )
    )
    assert design["production_mapping_enabled"] is False
    assert tuple(item["component_id"] for item in design["component_status"]) == CONSEQUENCE_COMPONENTS
    assert all(item["support_state"] == "ABSTAIN" for item in design["component_status"])


def test_6_scenario_weights_are_preserved_in_risk_envelope():
    result = evaluate_residual_risk(
        _action_input(), monetary_mapping=_mapping(), risk_policy=_policy()
    )
    assert result.scenario_weights == (0.25, 0.75)
    assert tuple(item.scenario_weight for item in result.scenario_losses) == (
        0.25,
        0.75,
    )


def test_7_weighted_expectation_is_correct():
    assert weighted_expectation((7.0, 21.0), (0.25, 0.75)) == 17.5
    result = evaluate_residual_risk(
        _action_input(), monetary_mapping=_mapping(), risk_policy=_policy()
    )
    assert result.expected_monetary_loss == 17.5


def test_8_weighted_cvar_uses_fractional_tail_mass():
    var, cvar = weighted_var_cvar((0.0, 100.0), (0.8, 0.2), 0.9)
    assert var == 100.0
    assert cvar == pytest.approx(100.0)
    result = evaluate_residual_risk(
        _action_input(), monetary_mapping=_mapping(), risk_policy=_policy()
    )
    assert result.monetary_loss_var_alpha == 21.0
    assert result.monetary_loss_cvar_alpha == 21.0


def test_9_unresolved_positive_tail_gate_blocks_cvar():
    with pytest.raises(ContractError, match=M1_POSITIVE_TAIL_DECISION_REQUIRED):
        evaluate_residual_risk(
            _action_input(),
            monetary_mapping=_mapping(),
            risk_policy=_policy(tail=TailSupportState.UNRESOLVED),
        )


def test_10_a00_is_mapped_from_its_identity_consequence_without_mutation():
    envelope = _action_input(action_id="A00")
    before = tuple(
        component.C_a_CU
        for scenario in envelope.scenario_consequences
        for component in scenario.components
    )
    result = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(scale=2), risk_policy=_policy()
    )
    after = tuple(
        component.C_a_CU
        for scenario in result.scenario_losses
        for component in scenario.component_losses
    )
    assert after == before
    assert result.action_id == "A00"


def test_11_unsupported_action_is_not_ranked():
    evaluation = evaluate_residual_risk(
        _action_input(action_id="A11", response_support=ResponseSupportClass.ABSTAIN),
        monetary_mapping=_mapping(),
        risk_policy=_policy(),
    )
    ranking = rank_risk_evaluations((evaluation,))
    assert evaluation.support_state is RiskEvaluationSupport.ABSTAINED
    assert evaluation.ranking_authority is RankingAuthority.NOT_RANKED
    assert ranking.abstained_action_ids == ("A11",)
    assert not ranking.authoritative_ranking
    assert not ranking.conditional_ranking


def test_12_assumption_based_action_has_conditional_ranking_label():
    evaluation = evaluate_residual_risk(
        _action_input(
            action_id="A11",
            response_support=ResponseSupportClass.SCENARIO_ASSUMPTION,
        ),
        monetary_mapping=_mapping(),
        risk_policy=_policy(),
    )
    ranking = rank_risk_evaluations((evaluation,))
    assert evaluation.support_state is RiskEvaluationSupport.ASSUMPTION_BASED
    assert ranking.conditional_ranking[0].ranking_authority is RankingAuthority.CONDITIONAL
    assert not ranking.authoritative_ranking
    supported = evaluate_residual_risk(
        _action_input(action_id="A00"),
        monetary_mapping=_mapping(status=MonetaryMappingStatus.FROZEN),
        risk_policy=_policy(status=RiskPolicyStatus.FROZEN),
    )
    supported_ranking = rank_risk_evaluations((supported,))
    assert supported.support_state is RiskEvaluationSupport.SUPPORTED
    assert supported_ranking.authoritative_ranking[0].ranking_authority is RankingAuthority.AUTHORITATIVE


def test_13_m2_reference_lineage_is_preserved():
    envelope = _action_input()
    result = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(), risk_policy=_policy()
    )
    expected = tuple(
        component.baseline_reference_lineage_hash
        for scenario in envelope.scenario_consequences
        for component in scenario.components
    )
    assert result.reference_lineage_hashes == expected


def test_14_m3_response_provenance_is_preserved():
    envelope = _action_input()
    result = evaluate_residual_risk(
        envelope, monetary_mapping=_mapping(), risk_policy=_policy()
    )
    assert result.response_provenance == envelope.response_provenance
    assert result.response_support is envelope.response_support


def test_15_risk_envelope_is_reproducible():
    envelope = _action_input()
    mapping = _mapping()
    policy = _policy()
    first = evaluate_residual_risk(
        envelope, monetary_mapping=mapping, risk_policy=policy
    )
    second = evaluate_residual_risk(
        envelope, monetary_mapping=mapping, risk_policy=policy
    )
    assert first == second
    assert first.risk_envelope_hash == second.risk_envelope_hash
