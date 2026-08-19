from __future__ import annotations

from model.M2.contracts import ConsequenceRow
from model.common.cu_normalization import CUNormalizationStatus
from model.M3.contracts import (
    ActionMaterialCoverageContract,
    CoverageRequirement,
    MaterialCriticality,
    MechanismRole,
)
from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import FrozenModel


class MaterialCoverageEvaluation(FrozenModel):
    candidate_action_id: str
    material_benefit_coverage: bool
    material_burden_coverage: bool
    baseline_coverage: bool
    nonmaterial_missingness: tuple[str, ...]
    coverage_explanation: tuple[str, ...]
    quality_flags: tuple[str, ...]

    @property
    def formal_coverage_valid(self) -> bool:
        return (
            self.material_benefit_coverage
            and self.material_burden_coverage
            and self.baseline_coverage
        )


_EVIDENCE_RANK = {
    EvidenceClass.DIRECT: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.DOMAIN_PROXY: 2,
    EvidenceClass.EMPIRICAL_REFERENCE: 2,
    EvidenceClass.EXTERNAL_STANDARD: 2,
    EvidenceClass.SCENARIO_PARAMETER: 3,
    EvidenceClass.UNSUPPORTED: 4,
}
_SUPPORT_RANK = {
    SupportState.SUPPORTED: 0,
    SupportState.DEGRADED: 1,
    SupportState.ABSTAIN: 2,
}


def _entry_satisfied(entry, row: ConsequenceRow) -> bool:
    if row.support_state is SupportState.ABSTAIN:
        return False
    if _SUPPORT_RANK[row.support_state] > _SUPPORT_RANK[entry.required_support]:
        return False
    if _EVIDENCE_RANK[row.evidence_class] > _EVIDENCE_RANK[
        entry.required_evidence_class
    ]:
        return False
    if (
        entry.coverage_requirement is CoverageRequirement.VALUED_COMPONENT
        and (
            row.constructed_value_cu is None
            or row.cu_status is not CUNormalizationStatus.CU_FROZEN
        )
    ):
        return False
    if (
        entry.coverage_requirement is CoverageRequirement.NATIVE_QUANTITY
        and row.native_quantity is None
    ):
        return False
    return True


def evaluate_material_coverage(
    candidate,
    rows: tuple[ConsequenceRow, ...],
    contract: ActionMaterialCoverageContract,
) -> MaterialCoverageEvaluation:
    by_component = {row.component_id: row for row in rows}
    entries = contract.for_template(candidate.template_id)
    benefit = True
    burden = True
    baseline = True
    nonmaterial = []
    explanations = []
    quality = []
    for entry in entries:
        satisfied = _entry_satisfied(entry, by_component[entry.component_id])
        if satisfied:
            continue
        explanations.append(
            f"{entry.component_id}:{entry.mechanism_role.value}:{entry.reason}"
        )
        if entry.criticality is MaterialCriticality.NONMATERIAL:
            nonmaterial.append(entry.component_id)
            quality.append("NONMATERIAL_COMPONENT_MISSING")
            continue
        if entry.criticality is MaterialCriticality.MATERIAL_DEGRADABLE:
            quality.append("DEGRADED_REFERENCE")
            continue
        if entry.mechanism_role is MechanismRole.PRINCIPAL_BENEFIT:
            benefit = False
        elif entry.mechanism_role is MechanismRole.PRINCIPAL_BURDEN:
            burden = False
        elif entry.mechanism_role is MechanismRole.BASELINE_COMPARATOR:
            baseline = False
    if candidate.coverage == "PARTIAL":
        quality.append("PARTIAL_LOCAL_COVERAGE")
    return MaterialCoverageEvaluation(
        candidate_action_id=candidate.candidate_action_id,
        material_benefit_coverage=benefit,
        material_burden_coverage=burden,
        baseline_coverage=baseline,
        nonmaterial_missingness=tuple(sorted(set(nonmaterial))),
        coverage_explanation=tuple(sorted(explanations)),
        quality_flags=tuple(sorted(set(quality))),
    )


class A00BaselineComparatorGate(FrozenModel):
    valid: bool
    missing_components: tuple[str, ...]
    explanation: tuple[str, ...]


def evaluate_a00_baseline_gate(
    rows: tuple[ConsequenceRow, ...],
    contract: ActionMaterialCoverageContract,
) -> A00BaselineComparatorGate:
    by_component = {row.component_id: row for row in rows}
    entries = tuple(
        entry
        for entry in contract.for_template("A00")
        if entry.mechanism_role is MechanismRole.BASELINE_COMPARATOR
    )
    missing = tuple(
        sorted(
            entry.component_id
            for entry in entries
            if entry.criticality is MaterialCriticality.MATERIAL_REQUIRED
            and not _entry_satisfied(entry, by_component[entry.component_id])
        )
    )
    return A00BaselineComparatorGate(
        valid=not missing,
        missing_components=missing,
        explanation=tuple(
            f"A00_BASELINE_COMPONENT_INVALID:{component}" for component in missing
        ),
    )

