from model.common.enums import (
    ArtifactLayer, AvailabilityBasis, DecisionTimeRole, EvidenceClass,
    FreezeState, OperationalStage, SupportState, weaker_or_equal,
)


def test_required_enums_are_stable():
    assert AvailabilityBasis.POSTHOC_ONLY.value == "POSTHOC_ONLY"
    assert DecisionTimeRole.INFERENCE_EVIDENCE.value == "INFERENCE_EVIDENCE"
    assert SupportState.ABSTAIN.value == "ABSTAIN"
    assert FreezeState.DEVELOPMENT_FROZEN.value == "DEVELOPMENT_FROZEN"
    assert OperationalStage.PRE_IB.value == "PRE_IB"
    assert ArtifactLayer.FORMAL.value == "FORMAL"
    assert tuple(item.value for item in SupportState) == ("SUPPORTED", "DEGRADED", "ABSTAIN")


def test_evidence_ceiling_order():
    assert weaker_or_equal(EvidenceClass.DERIVED, EvidenceClass.DIRECT)
    assert not weaker_or_equal(EvidenceClass.DIRECT, EvidenceClass.DOMAIN_PROXY)
