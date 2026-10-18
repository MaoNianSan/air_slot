"""M2 freeze scale lookup indexes must match the frozen reference lookups."""

import pytest

from model.M2.context import smoke_reference_payloads
from model.PRE.reference.data2_m2_train_fit import (
    _exposure_value,
    _passenger_value,
    _turnaround_taxi_value,
)
from model.PRE.reference.exposure_data2 import data2_downstream_exposure_from_payload
from model.PRE.reference.passenger_data2 import data2_passenger_reference_from_payload
from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
from model.PRE.reference.turnaround_data2 import data2_turnaround_reference_from_payload


def _payloads():
    return smoke_reference_payloads()


def test_turnaround_index_matches_lookup():
    payloads = _payloads()
    reference = data2_turnaround_reference_from_payload(payloads["turnaround"])
    index = {cell.airport_id: cell for cell in reference.cells}
    for airport in ("ABE", "UNKNOWN_AIRPORT"):
        expected = reference.lookup(airport)
        actual = _turnaround_taxi_value(index, airport, reference)
        if expected.value is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected.value)


def test_taxi_index_matches_lookup():
    payloads = _payloads()
    reference = data2_taxi_reference_from_payload(payloads["taxi"])
    index = {cell.airport_id: cell for cell in reference.cells}
    for airport in ("ABE", "UNKNOWN_AIRPORT"):
        expected = reference.lookup(airport)
        actual = _turnaround_taxi_value(
            index, airport, reference, abstain_if_missing=True
        )
        if expected.value is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected.value)


def test_exposure_index_matches_lookup():
    payloads = _payloads()
    reference = data2_downstream_exposure_from_payload(payloads["downstream_exposure"])
    index = {cell.airport_id: cell for cell in reference.cells}
    for airport in ("ABE", "UNKNOWN_AIRPORT"):
        expected = reference.lookup(airport)
        actual = _exposure_value(index, airport, reference)
        if expected.value is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected.value)


def test_passenger_index_matches_lookup():
    payloads = _payloads()
    reference = data2_passenger_reference_from_payload(payloads["passenger"])
    index = {
        (cell.origin_airport_id, cell.destination_airport_id): cell
        for cell in reference.cells
    }
    for origin, destination in (("ABE", "ATL"), ("ABE", "ZZZ")):
        expected = reference.lookup(origin, destination)
        actual = _passenger_value(index, origin, destination)
        if expected.value is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected.value)
