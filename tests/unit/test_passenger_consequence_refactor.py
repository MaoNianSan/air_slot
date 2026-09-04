import csv

import pytest

from model.M2.contracts import M2ScientificContext, ScientificContextValue
from model.M2.consequences.engine import native_quantities
from model.PRE.references.connection_share_reference import (
    build_connection_share_reference,
    derive_expected_connecting_passengers,
)
from model.PRE.references.passenger_load_reference import build_expected_passengers_reference
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.PRE.reference.data2_m2_train_fit import stream_db1b_coupon_rows, stream_t100_rows


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
            reference_id=("sha256:" + "2" * 64) if construction is ConstructionType.TRAIN_FROZEN_REFERENCE else None,
            reference_source=name,
        )
    return M2ScientificContext(
        turnaround_reference=value("turn", 0),
        turnaround_floor=value("floor", 0),
        expected_downstream_exposure=value("exposure", 1),
        expected_passengers_per_flight=value("expected-pax", pax, "passengers_per_flight"),
        itinerary_buffer_reference=value("itin-threshold", 45, "minutes", EvidenceClass.SCENARIO_PARAMETER, ConstructionType.SCENARIO_ASSUMPTION),
        service_policy_reference=value("service-threshold", 180, "minutes", EvidenceClass.SCENARIO_PARAMETER, ConstructionType.SCENARIO_ASSUMPTION),
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
    missing = ScientificContextValue(
        object_id="share", value=None, unit="share", support_state=SupportState.ABSTAIN,
        evidence_class=EvidenceClass.UNSUPPORTED, construction_type=ConstructionType.UNSUPPORTED,
        reason_code="NO_CONNECTION_SHARE",
    )
    ctx = _ctx(share=0.25).model_copy(update={"connection_share_reference": missing})
    by = {row.component_id: row for row in native_quantities(_scenario(60), ctx)}
    assert by["P_itinerary"].native_quantity is None
    assert by["P_itinerary"].support_state is SupportState.ABSTAIN
    assert by["P_time"].support_state is SupportState.SUPPORTED
    assert by["P_service"].support_state is SupportState.SUPPORTED


def test_t100_train_month_boundary_and_invalid_months(tmp_path):
    path = tmp_path / "t100.csv"
    fields = ["CARRIER", "ORIGIN", "DEST", "MONTH", "PASSENGERS", "DEPARTURES_PERFORMED"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for month, passengers in ((1, 100), (6, 100), (7, 10000), (10, 20000), ("", 1), ("abc", 1), (0, 1), (13, 1)):
            writer.writerow({"CARRIER": "AA", "ORIGIN": "AAA", "DEST": "BBB", "MONTH": month, "PASSENGERS": passengers, "DEPARTURES_PERFORMED": 1})
    rows = stream_t100_rows(path, allowed_months=(1, 2, 3, 4, 5, 6))
    reference = build_expected_passengers_reference(rows)
    assert reference.lookup("AA", "AAA", "BBB", 1).reference_value == 100.0
    assert set(rows.audit["used_months"]) == {1, 6}
    assert rows.audit["rows_excluded_outside_fit_period"] == 2
    assert rows.audit["rows_excluded_invalid_month"] == 4


def test_db1b_missing_trip_break_fails_closed(tmp_path):
    path = tmp_path / "Origin_and_Destination_Survey_DB1BCoupon_2019_1.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["Origin", "Dest", "Quarter", "Passengers"])
        writer.writeheader()
        writer.writerow({"Origin": "AAA", "Dest": "BBB", "Quarter": 1, "Passengers": 100})
    with pytest.raises(ContractError, match="DB1B_COUPON_TRIP_BREAK_FIELD_MISSING"):
        build_connection_share_reference(stream_db1b_coupon_rows((path,)))


def test_runtime_thresholds_come_from_typed_context():
    context = _ctx().model_copy(update={
        "itinerary_buffer_reference": _ctx().itinerary_buffer_reference.model_copy(update={"value": 60.0}),
        "service_policy_reference": _ctx().service_policy_reference.model_copy(update={"value": 240.0}),
    })
    by = {row.component_id: row for row in native_quantities(_scenario(50.0), context)}
    assert by["P_itinerary"].native_quantity == 0.0
    by = {row.component_id: row for row in native_quantities(_scenario(200.0), context)}
    assert by["P_service"].native_quantity == 0.0


@pytest.mark.parametrize("field, affected", [
    ("expected_passengers_per_flight", {"P_time", "P_itinerary", "P_service"}),
    ("connection_share_reference", {"P_itinerary"}),
    ("itinerary_buffer_reference", {"P_itinerary"}),
    ("service_policy_reference", {"P_service"}),
])
def test_component_specific_abstention(field, affected):
    base = _ctx()
    current = getattr(base, field)
    missing = current.model_copy(update={"value": None, "support_state": SupportState.ABSTAIN, "evidence_class": EvidenceClass.UNSUPPORTED, "construction_type": ConstructionType.UNSUPPORTED, "reason_code": "TEST_ABSTAIN"})
    by = {row.component_id: row for row in native_quantities(_scenario(200.0), base.model_copy(update={field: missing}))}
    for component in ("P_time", "P_itinerary", "P_service"):
        assert (by[component].support_state is SupportState.ABSTAIN) == (component in affected)


def test_passenger_lineage_contains_all_typed_references():
    by = {row.component_id: row for row in native_quantities(_scenario(200.0), _ctx())}
    assert "LEGACY_M2_V1_REFERENCE_LINEAGE_UNAVAILABLE" in by["P_time"].reference_lineage
    assert _ctx().expected_passengers_per_flight.reference_id in by["P_time"].reference_lineage
    assert _ctx().connection_share_reference.reference_id in by["P_itinerary"].reference_lineage
    assert _ctx().itinerary_buffer_reference.object_id in by["P_itinerary"].reference_lineage
    assert _ctx().service_policy_reference.object_id in by["P_service"].reference_lineage
