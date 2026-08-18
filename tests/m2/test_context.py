import pytest

from model.M2.context import (
    AirportReferenceKeys,
    build_exp2_fixed_scope_pending,
    build_m2_context,
    build_m2_frozen_scope,
    load_data2_reference_bundle,
    smoke_reference_payloads,
)
from model.M2.drivers import native_quantities
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import ScopeStatus
from model.common.errors import ContractError


def scenario():
    return {
        "decision_node_id": "n",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "r_ob_minutes": 20,
        "t_tx_minutes": 15,
        "ib_support": "SUPPORTED",
        "ob_support": "SUPPORTED",
        "tx_support": "SUPPORTED",
    }


def test_context_from_smoke_frozen_payloads():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    assert context.turnaround_reference.value == 38.0
    assert context.taxi_reference.value == 15.0
    assert context.expected_downstream_exposure.value == 1.0
    assert context.passenger_exposure.value == 100.0
    for value in (
        context.turnaround_reference,
        context.taxi_reference,
        context.expected_downstream_exposure,
        context.passenger_exposure,
    ):
        assert value.construction_type is ConstructionType.TRAIN_FROZEN_REFERENCE
        assert value.freeze_id.startswith("sha256:")
        assert value.reference_period == "2019-H1"


def test_missing_optional_normative_inputs_abstain():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    for value in (
        context.turnaround_floor,
        context.itinerary_disruption_events,
        context.service_policy_reference,
    ):
        assert value.value is None
        assert value.support_state is SupportState.ABSTAIN
        assert value.evidence_class is EvidenceClass.UNSUPPORTED


def test_expected_reference_id_mismatch_raises():
    payloads = smoke_reference_payloads()
    with pytest.raises(ContractError, match="M2_REFERENCE_ID_MISMATCH:taxi"):
        load_data2_reference_bundle(
            payloads,
            expected_reference_ids={"taxi": f"sha256:{'0' * 64}"},
        )


def test_missing_reference_payload_raises():
    payloads = smoke_reference_payloads()
    del payloads["taxi"]
    with pytest.raises(ContractError, match="M2_REFERENCE_PAYLOAD_MISSING:taxi"):
        load_data2_reference_bundle(payloads)


def test_mapping_uses_frozen_context():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    by_component = {row.component_id: row for row in native_quantities(scenario(), context)}
    assert by_component["F_continuity"].native_quantity == 0.0
    # Frozen Z_takeoff = max(0, DELTA_OB + T_TX - taxi_reference) = 20+15-15.
    assert by_component["F_propagation"].native_quantity == 20.0
    assert by_component["P_time"].native_quantity == 2000.0
    assert by_component["R_operating"].native_quantity == 0.0
    assert by_component["P_itinerary"].support_state is SupportState.ABSTAIN
    assert by_component["P_service"].support_state is SupportState.ABSTAIN


def test_z_takeoff_uses_signed_delta_ob_and_frozen_taxi_reference():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    context = build_m2_context(
        bundle,
        AirportReferenceKeys(
            connection_airport_id="ABE",
            successor_destination_airport_id="ATL",
        ),
    )
    # Early departure (negative DELTA_OB) must not inflate Z_takeoff.
    early = {
        **scenario(),
        "r_ob_minutes": 0,
        "delta_ob_minutes": -10,
        "delta_ob_support": "SUPPORTED",
        "t_tx_minutes": 25,
    }
    by_component = {row.component_id: row for row in native_quantities(early, context)}
    assert by_component["F_propagation"].native_quantity == 0.0
    assert by_component["P_time"].native_quantity == 0.0


def test_m2_frozen_scope_is_five_component_fixed_and_formal_ready():
    scope = build_m2_frozen_scope(
        {
            "formal_scope": [
                "F_continuity",
                "F_execution",
                "F_propagation",
                "P_time",
                "R_operating",
            ]
        }
    )
    assert scope.scope_status is ScopeStatus.FORMAL_READY
    assert scope.valuation_registry_id == "M2_DATA2_FORMAL_CU_V1"
    assert scope.aggregation_rule_id == "SUM_OVER_FIVE_ONLY_IF_ALL_SUPPORTED"
    assert scope.included_components == (
        "F_continuity",
        "F_execution",
        "F_propagation",
        "P_time",
        "R_operating",
    )


def test_m2_frozen_scope_rejects_scope_drift():
    from model.common.errors import ContractError

    with pytest.raises(ContractError, match="M2_FROZEN_SCOPE_NOT_FIVE_COMPONENT_FIXED"):
        build_m2_frozen_scope({"formal_scope": ["F_continuity"]})
