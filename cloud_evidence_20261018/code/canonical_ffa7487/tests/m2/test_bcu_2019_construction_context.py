"""2019 construction-context identity regressions (2026-10-13 fix round).

The year-replicated builder (``data2/scripts/build_year_references.py``)
stamps every row with the shared six-year identity ``data2_2017_2022``, while
``fit_train_references`` used to key the turnaround/exposure/passenger
expectation on ``year == 2019`` -> ``data2_2019``; any 2019 rebuild therefore
crashed with ``REFERENCE_DATASET_MISMATCH``. The fix routes an explicit
construction context (``dataset_instance_id``). These tests pin:

1. the year-replicated 2019 identity contract,
2. legacy 2019 compatibility (no context argument -> ``data2_2019``),
3. 2017/2018/2020-2022 identity invariance,
4. the six-reference / seven-scale structural surface,
5. the 2019 taxi source (frozen v5 artifact) and its fit window,

plus an end-to-end 2019 fit on real-contract rows that used to crash.
"""

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.reference import data2_m2_train_fit as fit

V5_LABEL = "2019-01..2019-06"
LEGACY_ID = "data2_2019"
SHARED_ID = "data2_2017_2022"
ZONES = {"JFK": "America/New_York", "LAX": "America/Los_Angeles",
         "SFO": "America/Los_Angeles"}


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def _taxi_payload():
    return {
        "reference_id": "sha256:fixture-taxi-v5",
        "dataset_instance_id": LEGACY_ID,
        "rule_id": "DATA2_TAXI_REFERENCE",
        "rule_version": "1.0.0",
        "fit_period": V5_LABEL,
        "statistic_id": "MEDIAN",
        "global_value_minutes": 15.0,
        "global_sample_count": 3.0,
        "cells": [
            {"airport_id": "LAX", "value_minutes": 15.0, "sample_count": 3,
             "fallback_level": "AIRPORT_CELL",
             "provenance": ["airport=LAX", "n=3"]}
        ],
        "cells_count": 1,
        "manifest_freeze_id": "fixture-freeze",
        "support_state": "SUPPORTED",
    }


def _write_v5(root: Path) -> Path:
    path = (root / "artifacts" / "diagnostics" / "v5_development_freeze"
            / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_taxi_payload()), encoding="utf-8")
    return path


def _write_db1b(root: Path, year: int = 2019) -> None:
    path = (root / "data2" / "raw" / "bts" / "db1b" / str(year) / "coupon"
            / f"Origin_and_Destination_Survey_DB1BCoupon_{year}_1.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["ItinID", "MktID", "SeqNum", "Coupons", "Year",
                         "Quarter", "Origin", "Dest", "Break", "Passengers"])
        writer.writerow([1, 1, 1, 1, year, 1, "JFK", "LAX", 1, 100])
        writer.writerow([2, 2, 1, 1, year, 1, "LAX", "SFO", 1, 50])


def _leg(**overrides):
    base = {
        "FlightDate": "2019-01-02", "Reporting_Airline": "AA",
        "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "100",
        "Origin": "JFK", "Dest": "LAX", "CRSDepTime": "0800",
        "CRSArrTime": "1100", "DepTime": "0810", "ArrTime": "1120",
        "WheelsOff": "0825", "WheelsOn": "1105", "TaxiOut": "15",
        "TaxiIn": "15", "DepDelay": "10", "ArrDelay": "20",
        "DepDelayMinutes": "10", "ArrDelayMinutes": "20",
        "Cancelled": "0", "Diverted": "0",
    }
    base.update(overrides)
    return base


def _successor(**overrides):
    row = _leg(Flight_Number_Reporting_Airline="101", Origin="LAX", Dest="SFO",
               CRSDepTime="1140", CRSArrTime="1300", DepTime="1150",
               ArrTime="1310", WheelsOff="1205", WheelsOn="1255",
               DepDelay="10", ArrDelay="10", DepDelayMinutes="10",
               ArrDelayMinutes="10")
    row.update(overrides)
    return row


def _write_ontime(root: Path, days: int = 60) -> Path:
    """``days`` chained same-tail days -> >=50 genuine turnaround episodes at
    LAX, above the builder's global minimum support (50)."""
    path = root / "ontime_2019_1.csv"
    fields = list(fit.ONTIME_PROJECTED_FIELDS)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for offset in range(days):
            day = (datetime(2019, 1, 2) + timedelta(days=offset)).strftime("%Y-%m-%d")
            writer.writerow(_leg(FlightDate=day))
            writer.writerow(_successor(FlightDate=day))
    return path


def _routing_harness(monkeypatch):
    """Monkeypatch the four builders + the passenger stream to record the
    construction-context argument they receive."""
    from model.M2.context import smoke_reference_payloads
    from model.PRE.reference.exposure_data2 import (
        data2_downstream_exposure_from_payload,
    )
    from model.PRE.reference.passenger_data2 import (
        data2_passenger_reference_from_payload,
    )
    from model.PRE.reference.taxi_data2 import data2_taxi_reference_from_payload
    from model.PRE.reference.turnaround_data2 import (
        data2_turnaround_reference_from_payload,
    )

    payloads = smoke_reference_payloads()
    loaders = {
        "turnaround": data2_turnaround_reference_from_payload,
        "downstream_exposure": data2_downstream_exposure_from_payload,
        "passenger": data2_passenger_reference_from_payload,
        "taxi": data2_taxi_reference_from_payload,
    }
    seen: dict = {}

    def turn(rows, fit_period="2019-H1", dataset_instance_id=LEGACY_ID,
             **kwargs):
        seen["turnaround"] = dataset_instance_id
        return loaders["turnaround"](payloads["turnaround"])

    def exposure(rows, fit_period="2019-H1", dataset_instance_id=LEGACY_ID,
                 **kwargs):
        seen["exposure"] = dataset_instance_id
        return loaders["downstream_exposure"](payloads["downstream_exposure"])

    def stream(coupon_paths, year=2019, dataset_instance_id=None):
        seen["stream"] = {"year": year, "dataset_instance_id": dataset_instance_id}
        return []

    def passenger(rows, fit_period="2019-H1", dataset_instance_id=LEGACY_ID,
                  rule_id=""):
        seen["passenger"] = dataset_instance_id
        return loaders["passenger"](payloads["passenger"])

    def taxi_refit(rows, fit_period="2019-H1", dataset_instance_id=LEGACY_ID,
                   **kwargs):
        seen["taxi_refit"] = dataset_instance_id
        return loaders["taxi"](payloads["taxi"])

    monkeypatch.setattr(fit, "build_data2_turnaround_reference", turn)
    monkeypatch.setattr(fit, "build_data2_downstream_exposure", exposure)
    monkeypatch.setattr(fit, "stream_passenger_routes", stream)
    monkeypatch.setattr(fit, "build_data2_passenger_reference", passenger)
    monkeypatch.setattr(fit, "build_data2_taxi_reference", taxi_refit)
    return seen


# --------------------------------------------------------------------------
# 1. year-replicated 2019 identity contract (+ 5. taxi source / window)
# --------------------------------------------------------------------------
def test_year_replicated_2019_uses_shared_identity_context(monkeypatch, tmp_path):
    seen = _routing_harness(monkeypatch)
    _write_v5(tmp_path)
    result = fit.fit_train_references(
        [], root=tmp_path, fit_period="2019-H1", year=2019,
        dataset_instance_id=SHARED_ID,
    )
    assert seen["turnaround"] == SHARED_ID
    assert seen["exposure"] == SHARED_ID
    assert seen["passenger"] == SHARED_ID
    assert seen["stream"] == {"year": 2019, "dataset_instance_id": SHARED_ID}
    assert "taxi_refit" not in seen, "2019 must keep the frozen v5 taxi source"
    assert result["taxi"]["fit_period"] == V5_LABEL
    assert result["taxi"]["reference_id"] == "sha256:fixture-taxi-v5"


def test_year_replicated_2019_end_to_end_on_real_row_contract(tmp_path):
    """The exact construction that crashed with REFERENCE_DATASET_MISMATCH:
    real-contract rows stamped data2_2017_2022 + year 2019 contexts."""
    _write_v5(tmp_path)
    _write_db1b(tmp_path, 2019)
    ontime = _write_ontime(tmp_path)
    rows = list(fit.iter_train_rows((ontime,), ZONES,
                                    dataset_instance_id=SHARED_ID))
    assert len(rows) == 120
    result = fit.fit_train_references(
        rows, root=tmp_path, fit_period="2019-H1", year=2019,
        dataset_instance_id=SHARED_ID,
    )
    assert result["turnaround"]["dataset_instance_id"] == SHARED_ID
    assert result["downstream_exposure"]["dataset_instance_id"] == SHARED_ID
    assert result["passenger"]["dataset_instance_id"] == SHARED_ID
    assert result["taxi"]["fit_period"] == V5_LABEL


# --------------------------------------------------------------------------
# 2. legacy 2019 compatibility
# --------------------------------------------------------------------------
def test_legacy_2019_default_keeps_legacy_identity(monkeypatch, tmp_path):
    seen = _routing_harness(monkeypatch)
    _write_v5(tmp_path)
    fit.fit_train_references([], root=tmp_path, fit_period="2019-H1")
    assert seen["turnaround"] == LEGACY_ID
    assert seen["exposure"] == LEGACY_ID
    assert seen["passenger"] == LEGACY_ID
    assert seen["stream"] == {"year": 2019, "dataset_instance_id": None}
    assert "taxi_refit" not in seen


# --------------------------------------------------------------------------
# 3. other-year identity invariance
# --------------------------------------------------------------------------
@pytest.mark.parametrize("year", [2017, 2018, 2020, 2021, 2022])
def test_other_years_identity_invariance(monkeypatch, tmp_path, year):
    seen = _routing_harness(monkeypatch)
    fit.fit_train_references([], root=tmp_path, fit_period=f"{year}-H1",
                             year=year)
    assert seen["turnaround"] == SHARED_ID
    assert seen["exposure"] == SHARED_ID
    assert seen["passenger"] == SHARED_ID
    assert seen["stream"] == {"year": year, "dataset_instance_id": None}
    assert seen["taxi_refit"] == SHARED_ID


def test_explicit_context_wins_over_legacy_default(monkeypatch, tmp_path):
    seen = _routing_harness(monkeypatch)
    fit.fit_train_references([], root=tmp_path, fit_period="2018-H1", year=2018,
                             dataset_instance_id="data2_TEST")
    assert seen["turnaround"] == "data2_TEST"
    assert seen["exposure"] == "data2_TEST"
    assert seen["passenger"] == "data2_TEST"
    assert seen["stream"] == {"year": 2018, "dataset_instance_id": "data2_TEST"}


# --------------------------------------------------------------------------
# 4. six-reference / seven-scale structural surface
# --------------------------------------------------------------------------
def test_six_reference_and_seven_scale_surface(monkeypatch, tmp_path):
    from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS

    assert len(CONSEQUENCE_COMPONENTS) == 7
    assert "F_continuity" in CONSEQUENCE_COMPONENTS
    seen = _routing_harness(monkeypatch)
    _write_v5(tmp_path)
    result = fit.fit_train_references([], root=tmp_path, fit_period="2019-H1",
                                      year=2019, dataset_instance_id=SHARED_ID)
    # fit level provides the four row-derived references; the consequence pair
    # (expected_passengers / connection_share) is joined from
    # fit_passenger_consequence_references in the bundle builder.
    assert set(result) == {"turnaround", "downstream_exposure", "passenger",
                           "taxi"}


def test_scales_continuity_b_yields_seven_components(monkeypatch, tmp_path):
    six = {name: {"median": 1.0, "positive_n": 1} for name in
           ("F_execution", "F_propagation", "P_time", "P_itinerary",
            "P_service", "R_operating")}
    monkeypatch.setattr(fit, "compute_train_scales",
                        lambda *a, **k: dict(six))
    ontime = _write_ontime(tmp_path)
    rows = list(fit.iter_train_rows((ontime,), ZONES,
                                    dataset_instance_id=SHARED_ID))

    class _TurnRef:
        cells = ()
        global_value_minutes = 41.0

    output = fit.compute_train_scales_continuity_b(rows, {}, turnaround_ref=_TurnRef())
    assert len(output) == 7
    assert set(output) == set(six) | {"F_continuity"}


# --------------------------------------------------------------------------
# 5. taxi source & time-range pinning details
# --------------------------------------------------------------------------
def test_2019_taxi_source_is_the_v5_frozen_artifact(monkeypatch, tmp_path):
    seen = _routing_harness(monkeypatch)
    v5_path = _write_v5(tmp_path)
    result = fit.fit_train_references([], root=tmp_path, fit_period="2019-H1",
                                      year=2019, dataset_instance_id=SHARED_ID)
    # payload served verbatim from the designated frozen artifact file
    assert result["taxi"]["fit_period"] == json.loads(
        v5_path.read_text(encoding="utf-8"))["fit_period"] == V5_LABEL
    assert "taxi_refit" not in seen
    # and the non-2019 path refits from rows instead
    fit.fit_train_references([], root=tmp_path, fit_period="2018-H1", year=2018)
    assert seen["taxi_refit"] == SHARED_ID
