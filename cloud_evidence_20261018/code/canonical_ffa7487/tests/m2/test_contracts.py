import pytest
from pydantic import ValidationError

from model.M2.contracts import (
    COMPONENTS,
    ExposureConfidence,
    M2ScientificContext,
    NativeQuantity,
    SourceType,
)
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
            scenario_weight=1.0,
            native_quantity=0,
            native_unit="events",
            driver="x",
            evidence_class=EvidenceClass.UNSUPPORTED,
            support_state=SupportState.ABSTAIN,
            source_type=SourceType.DATA,
            reference_source="test",
            reference_lineage=("test-ref",),
            confidence=ExposureConfidence.NONE,
            reason_code="NO_ITINERARY",
        )
    valid = NativeQuantity(
        component_id="P_itinerary",
        scenario_id=0,
        scenario_weight=1.0,
        native_quantity=None,
        native_unit="events",
        driver="x",
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN,
        source_type=SourceType.DATA,
        reference_source="test",
        reference_lineage=("test-ref",),
        confidence=ExposureConfidence.NONE,
        reason_code="NO_ITINERARY",
    )
    assert valid.native_quantity is None


def test_v4_scientific_context_has_one_typed_passenger_path():
    assert tuple(M2ScientificContext.model_fields) == (
        "turnaround_reference",
        "turnaround_floor",
        "expected_downstream_exposure",
        "expected_passengers_per_flight",
        "connection_share_reference",
        "itinerary_buffer_reference",
        "service_policy_reference",
        "taxi_reference",
    )
