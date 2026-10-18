import pytest
from pydantic import ValidationError
from model.M2.contracts import COMPONENTS, NativeQuantity

def test_fixed_ontology_and_abstain_is_null():
    assert COMPONENTS == ("F_continuity","F_execution","F_propagation","P_time","P_itinerary","P_service","R_operating")
    with pytest.raises(ValidationError): NativeQuantity(component="P_itinerary", native_value=0, native_unit="events", driver="x", evidence_class="UNSUPPORTED", support="ABSTAIN", reason_code="NO_ITINERARY")
    valid=NativeQuantity(component="P_itinerary",native_value=None,native_unit="events",driver="x",evidence_class="UNSUPPORTED",support="ABSTAIN",reason_code="NO_ITINERARY")
    assert valid.native_value is None
