from datetime import date, datetime, timezone
import pytest

from model.common.errors import ContractError
from model.PRE.canonical.normalization import canonicalize_metar_row, canonicalize_ontime_row
from model.PRE.canonical.timezone import local_hhmm_to_utc


def test_metar_units_qnh_and_missing_mslp_are_explicit():
    row = {"station":"LSZH", "valid":"2019-01-01 00:20", "tmpf":"32", "dwpf":"23",
           "drct":"180", "sknt":"10", "gust":"M", "mslp":"M", "vsby":"10",
           "metar":"LSZH 010020Z 18010KT Q1013"}
    result = canonicalize_metar_row(row, replay_lag_minutes=5)
    assert result["temperature_c"] == 0
    assert result["wind_speed_mps"] == pytest.approx(5.14444)
    assert result["qnh_hpa"] == 1013 and result["mslp_hpa"] is None
    assert result["availability_time"] > result["event_time"]


def test_local_hhmm_handles_2400_rollover_and_rejects_unknown_timezone():
    value = local_hhmm_to_utc(date(2019, 1, 1), "2400", "America/New_York")
    assert value == datetime(2019, 1, 2, 5, tzinfo=timezone.utc)
    with pytest.raises(ContractError): local_hhmm_to_utc(date(2019, 1, 1), "1200", "Unknown/Zone")


def test_ontime_actuals_are_posthoc_not_formal_input():
    row = {"FlightDate":"2019-01-01", "Reporting_Airline":"AA", "Tail_Number":"N1",
           "Flight_Number_Reporting_Airline":"10", "Origin":"JFK", "Dest":"LAX",
           "CRSDepTime":"0800", "CRSArrTime":"1100", "DepTime":"0810", "ArrTime":"1120",
           "WheelsOff":"0825", "WheelsOn":"1105", "TaxiOut":"15", "TaxiIn":"15",
           "Cancelled":"0", "Diverted":"0"}
    result = canonicalize_ontime_row(row, {"JFK":"America/New_York", "LAX":"America/Los_Angeles"})
    assert result["schedule_semantics"] == "CRS_DEPARTURE"
    assert result["realized_outcome"]["decision_time_role"] == "EVAL_OUTCOME"
    assert result["realized_outcome"]["availability_basis"] == "POSTHOC_ONLY"
