import pytest
from pydantic import ValidationError

from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import SupportedValue


def test_abstain_requires_null_and_reason():
    with pytest.raises(ValidationError):
        SupportedValue(value=0, unit="min", evidence_class="UNSUPPORTED",
                       support_ceiling="UNSUPPORTED", support_state="ABSTAIN")


def test_observed_zero_is_not_missing():
    value = SupportedValue(value=0, unit="min", evidence_class=EvidenceClass.DIRECT,
                           support_ceiling=EvidenceClass.DIRECT,
                           support_state=SupportState.SUPPORTED)
    assert value.value == 0
