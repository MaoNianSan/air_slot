from datetime import date, datetime, timezone
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
           "DepDelayMinutes":"10", "ArrDelayMinutes":"20",
           "Cancelled":"0", "Diverted":"0"}
    schedule, outcome = canonicalize_ontime_row(row, {"JFK":"America/New_York", "LAX":"America/Los_Angeles"})
    assert isinstance(schedule, FlightRecord) and isinstance(outcome, OperationalEventRecord)
    assert schedule.schedule_semantics == "CRS_DEPARTURE"
    assert schedule.event_start_time == schedule.scheduled_departure_utc
    assert schedule.event_end_time == schedule.scheduled_arrival_utc
    assert outcome.decision_time_role.value == "EVAL_OUTCOME"
    assert outcome.availability_basis.value == "POSTHOC_ONLY"


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
