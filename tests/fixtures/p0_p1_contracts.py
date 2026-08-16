from model.M2.contracts import (
    AvailableComponentSumDiagnostic,
    ComponentVector,
    ConsequenceRow,
    FormalEstimandValue,
    ScenarioConsequence,
    ValuationStatus,
)
from model.M3.contracts import (
    ActionMaterialCoverageContract,
    ActionMaterialCoverageEntry,
    BenefitOrBurden,
    CandidateAction,
    CoverageRequirement,
    MaterialCriticality,
    MechanismRole,
    ResponseParameterStatus,
    ResponseProvenance,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import (
    ConsequenceScope,
    FormalEstimandStatus,
    ScopeStatus,
)


def scope_fixture(
    *,
    estimand_id="LOCAL-FLIGHT",
    components=("F_execution",),
    valuation_registry_id="TEST-VALUATION-V1",
):
    return ConsequenceScope.create(
        estimand_id=estimand_id,
        estimand_version="1.0.0",
        included_components=tuple(components),
        aggregation_rule_id="TEST-SUM-V1",
        valuation_registry_id=valuation_registry_id,
        material_coverage_contract_id="TEST-COVERAGE",
        scope_status=ScopeStatus.FORMAL_READY,
    )


def coverage_contract(*, resource_required=False, p_service_nonmaterial=False):
    entries = [
        ActionMaterialCoverageEntry(
            template_id="A00",
            component_id="F_execution",
            mechanism_role=MechanismRole.BASELINE_COMPARATOR,
            criticality=MaterialCriticality.MATERIAL_REQUIRED,
            coverage_requirement=CoverageRequirement.VALUED_COMPONENT,
            benefit_or_burden=BenefitOrBurden.BASELINE,
            required_evidence_class=EvidenceClass.DERIVED,
            required_support=SupportState.SUPPORTED,
            reason="critical A00 flight comparator",
        ),
        ActionMaterialCoverageEntry(
            template_id="A11",
            component_id="F_execution",
            mechanism_role=MechanismRole.PRINCIPAL_BENEFIT,
            criticality=MaterialCriticality.MATERIAL_REQUIRED,
            coverage_requirement=CoverageRequirement.VALUED_COMPONENT,
            benefit_or_burden=BenefitOrBurden.BENEFIT,
            required_evidence_class=EvidenceClass.DERIVED,
            required_support=SupportState.SUPPORTED,
            reason="principal execution benefit",
        ),
    ]
    if resource_required:
        entries.append(
            ActionMaterialCoverageEntry(
                template_id="A11",
                component_id="R_operating",
                mechanism_role=MechanismRole.PRINCIPAL_BURDEN,
                criticality=MaterialCriticality.MATERIAL_REQUIRED,
                coverage_requirement=CoverageRequirement.VALUED_COMPONENT,
                benefit_or_burden=BenefitOrBurden.BURDEN,
                required_evidence_class=EvidenceClass.DERIVED,
                required_support=SupportState.SUPPORTED,
                reason="material resource burden",
            )
        )
    if p_service_nonmaterial:
        entries.append(
            ActionMaterialCoverageEntry(
                template_id="A11",
                component_id="P_service",
                mechanism_role=MechanismRole.NONMATERIAL_CONTEXT,
                criticality=MaterialCriticality.NONMATERIAL,
                coverage_requirement=CoverageRequirement.SUPPORT_ONLY,
                benefit_or_burden=BenefitOrBurden.CONTEXT,
                required_evidence_class=EvidenceClass.DERIVED,
                required_support=SupportState.SUPPORTED,
                reason="nonmaterial service context",
            )
        )
    return ActionMaterialCoverageContract.create(
        contract_id="TEST-COVERAGE",
        contract_version="1.0.0",
        entries=tuple(entries),
    )


def consequence(
    *,
    scenario_id=0,
    scope=None,
    missing=(),
    values=None,
):
    scope = scope or scope_fixture()
    values = values or {"F_execution": 10.0}
    rows = []
    for component in CONSEQUENCE_COMPONENTS:
        absent = component in missing
        value = float(values.get(component, 0.0))
        rows.append(
            ConsequenceRow(
                component_id=component,
                scenario_id=scenario_id,
                aspect=(
                    "Flight"
                    if component.startswith("F_")
                    else "Passenger"
                    if component.startswith("P_")
                    else "Resource"
                ),
                native_quantity=None if absent else value,
                native_unit="unit",
                driver="test",
                constructed_value_cu=None if absent else value,
                support_state=(
                    SupportState.ABSTAIN if absent else SupportState.SUPPORTED
                ),
                evidence_class=(
                    EvidenceClass.UNSUPPORTED if absent else EvidenceClass.DERIVED
                ),
                valuation_status=(
                    ValuationStatus.VALUATION_UNSUPPORTED
                    if absent
                    else ValuationStatus.VALUATION_FROZEN
                ),
                valuation_registry_id=None if absent else "TEST-VALUATION-V1",
                valuation_rule_id=None if absent else f"TEST-{component}",
                valuation_parameter_version=None if absent else "1.0.0",
                reason_code="NO_EVIDENCE" if absent else None,
            )
        )
    valued = tuple(row for row in rows if row.constructed_value_cu is not None)
    included = tuple(
        row for row in rows if row.component_id in scope.included_components
    )
    formal_ok = all(row.constructed_value_cu is not None for row in included)
    formal = FormalEstimandValue(
        value_cu=(sum(row.constructed_value_cu for row in included) if formal_ok else None),
        status=(
            FormalEstimandStatus.FORMAL_AVAILABLE
            if formal_ok
            else FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
        ),
        estimand_id=scope.estimand_id,
        estimand_version=scope.estimand_version,
        scope_hash=scope.scope_hash,
        valuation_registry_id=scope.valuation_registry_id,
        aggregation_rule_id=scope.aggregation_rule_id,
        included_components=scope.included_components,
        reason_code=None if formal_ok else "INCLUDED_COMPONENT_ABSTAIN",
    )
    return ScenarioConsequence(
        decision_node_id="node",
        scenario_id=scenario_id,
        scenario_weight=1.0,
        consequence_scope=scope,
        component_vector=ComponentVector(rows=tuple(rows)),
        available_component_sum_diagnostic=AvailableComponentSumDiagnostic(
            value_cu=sum(row.constructed_value_cu for row in valued) if valued else None,
            included_components=tuple(row.component_id for row in valued),
            status="DIAGNOSTIC_AVAILABLE" if valued else "NO_VALUED_COMPONENTS",
        ),
        formal_estimand_value=formal,
    )


def candidate(
    template="A11",
    *,
    action_index=1,
    candidate_index=0,
    precondition="TRUE",
    provenance=ResponseProvenance.OPERATOR_INDUSTRY,
    parameter_status=ResponseParameterStatus.FROZEN,
    coverage="FULL",
    mitigation=None,
    induced=None,
):
    is_a00 = template == "A00"
    return CandidateAction(
        candidate_action_id=f"{template}:instance-{candidate_index}",
        template_id=template,
        action_family="null" if is_a00 else "timing",
        action_index=0 if is_a00 else action_index,
        candidate_index=candidate_index,
        parameters={} if is_a00 else {"deadline_minutes": 30},
        precondition_state=precondition,
        authority_capabilities=(),
        mitigation={} if is_a00 else (mitigation or {"F_execution": 0.5}),
        induced={} if is_a00 else (induced or {}),
        response_model="DETERMINISTIC",
        response_parameters={"value": 0.0 if is_a00 else 1.0},
        response_provenance=provenance,
        response_parameter_status=(
            ResponseParameterStatus.NOT_REQUIRED if is_a00 else parameter_status
        ),
        coverage=coverage,
        preparation_time_minutes=0,
        deadline_semantics="scenario_deadline",
    )
