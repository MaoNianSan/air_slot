from datetime import date, datetime, timedelta, timezone
import pytest

from model.common.errors import ContractError
from model.PRE.canonical.normalization import (canonicalize_flightlist_row,
                                               canonicalize_metar_row, canonicalize_ontime_row)
from model.PRE.contracts.canonical import FlightRecord, OperationalEventRecord, WeatherObservation
from model.PRE.canonical.timezone import local_hhmm_to_utc


def test_metar_units_qnh_and_missing_mslp_are_explicit():
    row = {"station":"LSZH", "valid":"2019-01-01 00:20", "tmpf":"32", "dwpf":"23",
           "drct":"180", "sknt":"10", "gust":"M", "mslp":"M", "vsby":"10",
           "metar":"LSZH 010020Z 18010KT Q1013"}
    result = canonicalize_metar_row(row, replay_lag_minutes=5)
    assert isinstance(result, WeatherObservation)
    assert result.temperature_c == 0
    assert result.wind_speed_mps == pytest.approx(5.14444)
    assert result.qnh_hpa == 1013 and result.mslp_hpa is None
    assert result.wind_gust_mps is None and result.availability_time > result.event_time


def test_local_hhmm_handles_2400_rollover_and_rejects_unknown_timezone():
    value = local_hhmm_to_utc(date(2019, 1, 1), "2400", "America/New_York")
    assert value == datetime(2019, 1, 2, 5, tzinfo=timezone.utc)
    with pytest.raises(ContractError): local_hhmm_to_utc(date(2019, 1, 1), "1200", "Unknown/Zone")


def test_ontime_actuals_are_posthoc_not_formal_input():
    row = {"FlightDate":"2019-01-01", "Reporting_Airline":"AA", "Tail_Number":"N1",
           "Flight_Number_Reporting_Airline":"10", "Origin":"JFK", "Dest":"LAX",
           "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0810", "ArrTime":"1120",
           "WheelsOff":"0825", "WheelsOn":"1105", "TaxiOut":"15", "TaxiIn":"15",
           "DepDelay":"10", "ArrDelay":"20",
           "DepDelayMinutes":"10", "ArrDelayMinutes":"20",
           "Cancelled":"0", "Diverted":"0"}
    schedule, outcome = canonicalize_ontime_row(row, {"JFK":"America/New_York", "LAX":"America/Los_Angeles"})
    assert isinstance(schedule, FlightRecord) and isinstance(outcome, OperationalEventRecord)
    assert schedule.schedule_semantics == "CRS_DEPARTURE"
    assert schedule.event_start_time == schedule.scheduled_departure_utc
    assert schedule.event_end_time == schedule.scheduled_arrival_utc
    assert outcome.decision_time_role.value == "EVAL_OUTCOME"
    assert outcome.availability_basis.value == "POSTHOC_ONLY"


def test_ontime_direct_clock_is_primary_and_derived_values_are_retained():
    row = {"FlightDate":"2019-01-01", "Reporting_Airline":"AA", "Tail_Number":"N1",
           "Flight_Number_Reporting_Airline":"11", "Origin":"JFK", "Dest":"LAX",
           "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0810", "ArrTime":"1120",
           "WheelsOff":"0825", "WheelsOn":"1105", "TaxiOut":"15", "TaxiIn":"15",
           "DepDelay":"30", "ArrDelay":"40",
           "DepDelayMinutes":"30", "ArrDelayMinutes":"40",
           "Cancelled":"0", "Diverted":"0"}
    _, outcome = canonicalize_ontime_row(
        row, {"JFK":"America/New_York", "LAX":"America/Los_Angeles"}
    )
    assert outcome.actual_departure_utc == outcome.actual_departure_direct_utc
    assert outcome.actual_departure_derived_utc != outcome.actual_departure_direct_utc
    assert "BTS_SIGNED_DELAY_DIRECT_CLOCK_INCONSISTENCY" in outcome.quality_flags
    assert outcome.wheels_off_utc == outcome.wheels_off_direct_utc


def test_ontime_signed_delay_restores_early_operation_and_minutes_stay_reporting_only():
    row = {
        "FlightDate": "2019-01-01",
        "Reporting_Airline": "AA",
        "Tail_Number": "N1",
        "Flight_Number_Reporting_Airline": "12",
        "Origin": "JFK",
        "Dest": "LAX",
        "CRSDepTime": "0800",
        "CRSArrTime": "1100",
        "DepTime": "0753",
        "ArrTime": "1051",
        "WheelsOff": "0808",
        "WheelsOn": "1036",
        "TaxiOut": "15",
        "TaxiIn": "15",
        "DepDelay": "-7",
        "ArrDelay": "-9",
        "DepDelayMinutes": "0",
        "ArrDelayMinutes": "0",
        "Cancelled": "0",
        "Diverted": "0",
    }
    schedule, outcome = canonicalize_ontime_row(
        row, {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}
    )
    assert outcome.actual_departure_utc == schedule.scheduled_departure_utc - timedelta(minutes=7)
    assert outcome.actual_arrival_utc == schedule.scheduled_arrival_utc - timedelta(minutes=9)
    assert outcome.actual_departure_derived_utc == outcome.actual_departure_utc
    assert outcome.actual_arrival_derived_utc == outcome.actual_arrival_utc


def test_ontime_signed_delay_resolves_previous_local_date_near_midnight():
    row = {
        "FlightDate": "2019-01-02",
        "Reporting_Airline": "AA",
        "Tail_Number": "N1",
        "Flight_Number_Reporting_Airline": "13",
        "Origin": "JFK",
        "Dest": "LAX",
        "CRSDepTime": "0005",
        "CRSArrTime": "0300",
        "DepTime": "2355",
        "ArrTime": "0300",
        "WheelsOff": "0010",
        "WheelsOn": "0245",
        "TaxiOut": "15",
        "TaxiIn": "15",
        "DepDelay": "-10",
        "ArrDelay": "0",
        "DepDelayMinutes": "0",
        "ArrDelayMinutes": "0",
        "Cancelled": "0",
        "Diverted": "0",
    }
    schedule, outcome = canonicalize_ontime_row(
        row, {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}
    )
    assert outcome.actual_departure_utc == schedule.scheduled_departure_utc - timedelta(minutes=10)
    assert "BTS_SIGNED_DELAY_DATE_OFFSET_RESOLVED_DEPARTURE" in outcome.quality_flags


def test_flightlist_iso_timestamp_produces_dual_typed_objects_with_shared_lineage():
    row = {"callsign":"ABC1", "day":"2019-01-01", "origin":"LSZH", "destination":"EGLL",
           "icao24":"abc123", "firstseen":"2018-12-31 00:43:16+00:00",
           "lastseen":"2018-12-31 02:43:16+00:00"}
    first = canonicalize_flightlist_row(row)
    second = canonicalize_flightlist_row(row)
    flight, event = first
    assert isinstance(flight, FlightRecord) and isinstance(event, OperationalEventRecord)
    assert flight.canonical_record_id != event.canonical_record_id
    assert flight.provenance.source_record_id == event.provenance.source_record_id
    assert flight.decision_time_role.value == "EPISODE_CONSTRUCTION"
    assert event.decision_time_role.value == "EVAL_OUTCOME"
    assert [item.canonical_record_id for item in first] == [item.canonical_record_id for item in second]
