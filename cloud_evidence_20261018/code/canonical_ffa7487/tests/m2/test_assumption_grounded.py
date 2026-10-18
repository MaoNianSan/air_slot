from pathlib import Path

import pytest

from model.M2.context import (
    AirportReferenceKeys,
    build_assumption_grounded_context,
    build_m2_context,
    build_m2_frozen_scope,
    build_m2_seven_component_scope,
    load_data2_reference_bundle,
    smoke_reference_payloads,
)
from model.M2.contracts import (
    ExposureConfidence,
    ExposureSupportLevel,
    ScientificContextValue,
    SourceType,
)
from model.M2.consequences.engine import native_quantities
from model.PRE.transformation import ConstructionType
from model.common.estimand import ScopeStatus
from model.common.enums import EvidenceClass, SupportState


def _node_exposure():
    return ScientificContextValue(
        object_id="TEST_NODE_EXPOSURE",
        value=1.0,
        unit="legs",
        support_state=SupportState.SUPPORTED,
        evidence_class=EvidenceClass.DERIVED,
        construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
        reference_period="2019-H1",
        freeze_id="sha256:" + "0" * 64,
        source_type=SourceType.DATA,
        support_level=ExposureSupportLevel.AIRPORT_REFERENCE,
        reference_source="sha256:" + "1" * 64,
        reference_id="sha256:" + "1" * 64,
        reference_version="TEST@1.0.0",
        confidence=ExposureConfidence.LOW,
    )


def _scenario(d_to_minutes):
    return {
        "decision_node_id": "n",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "d_ob_minutes": d_to_minutes,
        "d_tx_minutes": 0,
        "d_to_minutes": d_to_minutes,
        "ib_support": "SUPPORTED",
        "d_ob_support": "SUPPORTED",
        "d_tx_support": "SUPPORTED",
        "d_to_support": "SUPPORTED",
    }


def _assumption_context(**kwargs):
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    return build_assumption_grounded_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
        node_specific_exposure=_node_exposure(),
        **kwargs,
    )


def test_assumption_context_inputs_supported():
    context = _assumption_context(
        tau_service_minutes=180.0, itinerary_buffer_minutes=45.0
    )
    assert context.itinerary_buffer_reference.support_state is SupportState.SUPPORTED
    assert context.service_policy_reference.value == 180.0
    assert context.itinerary_buffer_reference.value == 45.0
    assert context.itinerary_buffer_reference.source_type is SourceType.SCENARIO_ASSUMPTION
    assert context.service_policy_reference.source_type is SourceType.SCENARIO_ASSUMPTION
    assert context.itinerary_buffer_reference.assumption_scope is not None


def test_p_itinerary_scenario_threshold_events():
    context = _assumption_context(
        tau_service_minutes=180.0, itinerary_buffer_minutes=45.0
    )
    by = {
        row.component_id: row
        for row in native_quantities(_scenario(20.0), context)
    }
    # The active refactor freezes a strict D_TO > 45 minute boundary.
    assert by["P_itinerary"].native_quantity == 0.0
    assert by["P_itinerary"].support_state is SupportState.SUPPORTED
    assert by["P_itinerary"].evidence_class is EvidenceClass.DOMAIN_PROXY
    # d_to=20 < tau=180 -> no service-policy event.
    assert by["P_service"].native_quantity == 0.0
    assert by["P_service"].support_state is SupportState.SUPPORTED


def test_p_itinerary_no_disruption_within_buffer():
    context = _assumption_context(
        tau_service_minutes=180.0, itinerary_buffer_minutes=45.0
    )
    by = {
        row.component_id: row
        for row in native_quantities(_scenario(10.0), context)
    }
    assert by["P_itinerary"].native_quantity == 0.0
    assert by["P_service"].native_quantity == 0.0

    by_above = {
        row.component_id: row
        for row in native_quantities(_scenario(60.0), context)
    }
    assert by_above["P_itinerary"].native_quantity == 25.0


def test_p_service_threshold_event_at_or_above_tau():
    context = _assumption_context(
        tau_service_minutes=180.0, itinerary_buffer_minutes=45.0
    )
    by = {
        row.component_id: row
        for row in native_quantities(_scenario(180.0), context)
    }
    assert by["P_service"].native_quantity == 100.0


def test_reference_context_supports_all_passenger_components():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    by = {
        row.component_id: row
        for row in native_quantities(_scenario(20.0), context)
    }
    assert by["P_itinerary"].support_state is SupportState.SUPPORTED
    assert by["P_service"].support_state is SupportState.SUPPORTED


def test_seven_component_scope_formal_ready():
    scope = build_m2_seven_component_scope()
    assert scope.scope_status is ScopeStatus.FORMAL_READY
    assert len(scope.included_components) == 7
    assert "P_itinerary" in scope.included_components
    assert "P_service" in scope.included_components


def test_frozen_scope_delegates_on_seven_config():
    seven = [
        "F_continuity", "F_execution", "F_propagation",
        "P_time", "P_itinerary", "P_service", "R_operating",
    ]
    scope = build_m2_frozen_scope({"formal_scope": seven})
    assert scope.scope_status is ScopeStatus.FORMAL_READY
    assert tuple(scope.included_components) == tuple(seven)
    active = build_m2_frozen_scope()
    assert len(active.included_components) == 7


def test_legacy_context_wrapper_rejects_non_v4_thresholds():
    with pytest.raises(Exception, match="M2_LEGACY_ITINERARY_THRESHOLD_MISMATCH"):
        _assumption_context(tau_service_minutes=180.0, itinerary_buffer_minutes=15.0)
    with pytest.raises(Exception, match="M2_LEGACY_SERVICE_THRESHOLD_MISMATCH"):
        _assumption_context(tau_service_minutes=240.0, itinerary_buffer_minutes=45.0)
