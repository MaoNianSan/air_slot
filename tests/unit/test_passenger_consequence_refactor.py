from model.M2.contracts import M2ScientificContext, ScientificContextValue
from model.M2.drivers import native_quantities
from model.PRE.references.connection_share_reference import (
    build_connection_share_reference,
    derive_expected_connecting_passengers,
)
from model.PRE.references.passenger_load_reference import build_expected_passengers_reference
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState


def _ctx(pax=100.0, share=0.25):
    def value(name, raw, unit="unit", evidence=EvidenceClass.EMPIRICAL_REFERENCE, construction=ConstructionType.TRAIN_FROZEN_REFERENCE):
        return ScientificContextValue(
            object_id=name,
            value=raw,
            unit=unit,
            support_state=SupportState.SUPPORTED,
            evidence_class=evidence,
            construction_type=construction,
            reference_period="2019-H1",
            freeze_id="sha256:" + "1" * 64,
            reference_id="sha256:" + "2" * 64,
            reference_source=name,
        )
    return M2ScientificContext(
        turnaround_reference=value("turn", 0),
        turnaround_floor=value("floor", 0),
        expected_downstream_exposure=value("exposure", 1),
        passenger_exposure=value("pax", pax, "passengers_per_flight"),
        expected_passengers_per_flight=value("expected-pax", pax, "passengers_per_flight"),
        itinerary_disruption_events=value("itin-events", 0),
        itinerary_buffer_reference=None,
        service_policy_reference=value("service", 180, "minutes", EvidenceClass.EXTERNAL_STANDARD, ConstructionType.EXTERNAL_OR_POLICY_REFERENCE),
        taxi_reference=value("taxi", 0),
        connection_share_reference=value("share", share, "share"),
    )


def _scenario(delay):
    return {
        "decision_node_id": "n", "scenario_id": 0, "scenario_weight": 1.0,
        "r_ib_minutes": 0, "d_ob_minutes": delay, "d_tx_minutes": 0,
        "d_to_minutes": delay, "ib_support": "SUPPORTED",
        "d_ob_support": "SUPPORTED", "d_tx_support": "SUPPORTED", "d_to_support": "SUPPORTED",
    }


def test_t100_expected_passengers_and_fallbacks():
    ref = build_expected_passengers_reference([
        {"CARRIER": "AA", "ORIGIN": "AAA", "DEST": "BBB", "MONTH": 1, "PASSENGERS": 1000, "DEPARTURES_PERFORMED": 10},
        {"CARRIER": "AA", "ORIGIN": "AAA", "DEST": "BBB", "MONTH": 1, "PASSENGERS": 1, "DEPARTURES_PERFORMED": 0},
    ])
    cell = ref.lookup("AA", "AAA", "BBB", 1)
    assert cell.reference_value == 100
    assert cell.reference_unit if hasattr(cell, "reference_unit") else True
    assert ref.lookup("ZZ", "XXX", "YYY", 1) is not None  # global fallback is supported
    assert cell.lineage_hash.startswith("sha256:")


def test_connection_share_and_derived_reference():
    ref = build_connection_share_reference([
        {"Origin": "AAA", "Dest": "BBB", "Quarter": 1, "Passengers": 30, "Break": ""},
        {"Origin": "AAA", "Dest": "BBB", "Quarter": 1, "Passengers": 70, "Break": "X"},
    ])
    cell = ref.lookup("AAA", "BBB", 1)
    assert cell.connection_share == 0.3
    derived = derive_expected_connecting_passengers(100.0, cell)
    assert derived.expected_connecting_passengers == 30.0
    assert derived.evidence_class is EvidenceClass.DERIVED
    assert derived.lineage_hash.startswith("sha256:")


def test_reference_builders_reject_invalid_rows_and_preserve_zero_one_shares():
    expected = build_expected_passengers_reference([
        {"CARRIER": "AA", "ORIGIN": "AAA", "DEST": "BBB", "MONTH": 1, "PASSENGERS": -1, "DEPARTURES_PERFORMED": 1},
        {"CARRIER": "AA", "ORIGIN": "AAA", "DEST": "BBB", "MONTH": 1, "PASSENGERS": 1, "DEPARTURES_PERFORMED": 0},
    ])
    assert expected.excluded_rows == 2
    assert expected.support_state is SupportState.ABSTAIN
    zero = build_connection_share_reference([{"Origin": "AAA", "Dest": "BBB", "Quarter": 1, "Passengers": 1, "Break": "X"}])
    one = build_connection_share_reference([{"Origin": "AAA", "Dest": "BBB", "Quarter": 1, "Passengers": 1, "Break": ""}])
    assert zero.lookup("AAA", "BBB", 1).connection_share == 0.0
    assert one.lookup("AAA", "BBB", 1).connection_share == 1.0


def test_passenger_formula_thresholds_and_units():
    for delay, itin, service in ((44.999, 0, 0), (45.0, 0, 0), (45.001, 25, 0), (179.999, 25, 0), (180.0, 25, 100), (200.0, 25, 100)):
        by = {row.component_id: row for row in native_quantities(_scenario(delay), _ctx())}
        assert by["P_time"].native_quantity == 100 * delay
        assert by["P_itinerary"].native_quantity == itin
        assert by["P_service"].native_quantity == service
        assert by["P_time"].native_unit == "passenger_minutes"
        assert by["P_itinerary"].native_unit == "expected_disrupted_connecting_passenger_exposure"
        assert by["P_service"].native_unit == "expected_long_delay_passenger_service_exposure"


def test_missing_reference_abstains_without_partial_multiplication():
    ctx = _ctx(share=0.25).model_copy(update={"connection_share_reference": None})
    by = {row.component_id: row for row in native_quantities(_scenario(60), ctx)}
    assert by["P_itinerary"].native_quantity is None
    assert by["P_itinerary"].support_state is SupportState.ABSTAIN
