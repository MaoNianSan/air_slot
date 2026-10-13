"""Regression for the B-continuity scale on the real train-row contract.

``compute_train_scales_continuity_b`` consumes rows yielded by
``iter_train_rows``: the scheduled departure is carried as ``event_start_time``
(the canonical ``FlightRecord`` aliases ``scheduled_departure_utc`` /
``event_start_time`` onto the same ``schedule_dep`` value), and the flat key
``scheduled_departure_utc`` never exists on these row dicts.  A prior revision
read the flat key and crashed with KeyError on every real build; this test
exercises the F_continuity computation end-to-end on rows produced through the
real canonicalization path from a synthetic on-time CSV.
"""

import csv
from datetime import datetime

import pytest

from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.reference import data2_m2_train_fit as fit

FIELDS = list(fit.ONTIME_PROJECTED_FIELDS)
ZONES = {
    "JFK": "America/New_York",
    "LAX": "America/Los_Angeles",
    "SFO": "America/Los_Angeles",
}


def _leg(**overrides):
    base = {
        "FlightDate": "2017-01-02",
        "Reporting_Airline": "AA",
        "Tail_Number": "N1",
        "Flight_Number_Reporting_Airline": "100",
        "Origin": "JFK",
        "Dest": "LAX",
        "CRSDepTime": "0800",
        "CRSArrTime": "1100",
        "DepTime": "0810",
        "ArrTime": "1120",
        "WheelsOff": "0825",
        "WheelsOn": "1105",
        "TaxiOut": "15",
        "TaxiIn": "15",
        "DepDelay": "10",
        "ArrDelay": "20",
        "DepDelayMinutes": "10",
        "ArrDelayMinutes": "20",
        "Cancelled": "0",
        "Diverted": "0",
    }
    base.update(overrides)
    return base


def _successor():
    # Same tail; departs LAX with a planned turn of 1140 - 1120 = 20 min,
    # below the 41-minute turnaround reference -> F_continuity = 21.
    return _leg(
        Flight_Number_Reporting_Airline="101",
        Origin="LAX",
        Dest="SFO",
        CRSDepTime="1140",
        CRSArrTime="1300",
        DepTime="1150",
        ArrTime="1310",
        WheelsOff="1205",
        WheelsOn="1255",
        DepDelay="10",
        ArrDelay="10",
        DepDelayMinutes="10",
        ArrDelayMinutes="10",
    )


def _write_ontime(tmp_path, rows):
    path = tmp_path / "On_Time_2017_1.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def test_b_continuity_scales_read_scheduled_departure_from_real_row_contract(
    tmp_path, monkeypatch
):
    predecessor, successor = _leg(), _successor()
    path = _write_ontime(tmp_path, [predecessor, successor])
    rows = list(
        fit.iter_train_rows((path,), ZONES, dataset_instance_id="data2_test")
    )
    assert len(rows) == 2

    # The real row contract consumed by the scale computation.
    for row in rows:
        assert isinstance(row["event_start_time"], datetime)
        assert "scheduled_departure_utc" not in row
        assert isinstance(row["actual_arrival_utc"], datetime)
        assert isinstance(row["actual_departure_utc"], datetime)

    # Field equivalence with the canonical schedule record of the same row.
    schedule, _outcome = canonicalize_ontime_row(dict(successor), ZONES)
    assert rows[1]["event_start_time"] == schedule.scheduled_departure_utc

    # The B-specific F_continuity pass runs on the real row structure; the
    # five delegated legacy scales are stubbed out of this regression.
    monkeypatch.setattr(fit, "compute_train_scales", lambda *a, **k: {})

    class _Cell:
        airport_id = "LAX"
        value_minutes = 41.0
        fallback_level = "AIRPORT_CELL"

    class _TurnRef:
        cells = (_Cell(),)
        global_value_minutes = 41.0

    output = fit.compute_train_scales_continuity_b(
        rows, {}, turnaround_ref=_TurnRef()
    )
    entry = output["F_continuity"]
    assert entry["positive_n"] == 1
    assert entry["median"] == pytest.approx(21.0)
    assert entry["continuity_contract"] == "JATM_F_CONTINUITY_B_V1"
