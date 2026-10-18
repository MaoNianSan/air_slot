import pytest
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.PRE.evidence.support import publish_value, validate_transformation


def test_support_is_monotone_and_zero_is_observed():
    validate_transformation(EvidenceClass.DERIVED, EvidenceClass.DIRECT)
    with pytest.raises(ContractError): validate_transformation(EvidenceClass.DIRECT, EvidenceClass.DERIVED)
    observed = publish_value(0, SupportState.SUPPORTED)
    assert observed.value == 0 and observed.reason_code is None


def test_abstain_and_unregistered_fallback_are_explicit():
    abstained = publish_value(None, SupportState.ABSTAIN, reason_code="NO_EVIDENCE")
    assert abstained.value is None
    with pytest.raises(ContractError): publish_value(1, SupportState.SUPPORTED, fallback_used=True, fallback_registered=False)
