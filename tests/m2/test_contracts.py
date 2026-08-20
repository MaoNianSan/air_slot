import pytest
from pydantic import ValidationError

from model.M2.contracts import COMPONENTS, NativeQuantity, SourceType
from model.common.enums import EvidenceClass, SupportState


def test_fixed_ontology_and_abstain_is_null():
    assert COMPONENTS == (
        "F_continuity",
        "F_execution",
        "F_propagation",
        "P_time",
        "P_itinerary",
        "P_service",
        "R_operating",
    )
    with pytest.raises(ValidationError):
        NativeQuantity(
            component_id="P_itinerary",
            scenario_id=0,
            native_quantity=0,
            native_unit="events",
            driver="x",
            evidence_class=EvidenceClass.UNSUPPORTED,
            support_state=SupportState.ABSTAIN,
            source_type=SourceType.DATA,
            reason_code="NO_ITINERARY",
        )
    valid = NativeQuantity(
        component_id="P_itinerary",
        scenario_id=0,
        native_quantity=None,
        native_unit="events",
        driver="x",
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN,
        source_type=SourceType.DATA,
        reason_code="NO_ITINERARY",
    )
    assert valid.native_quantity is None
