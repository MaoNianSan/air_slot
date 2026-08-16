from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.exposure_data2 import (
    RULE_ID,
    RULE_VERSION,
    Data2ExposureReference,
    build_data2_downstream_exposure,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from pathlib import Path

UTC = timezone.utc


def flight(fid, aircraft, origin, dest, dep, arr, *, split="train", dataset="data2_2019"):
    return {
        "dataset_instance_id": dataset,
        "aircraft_id_namespace": "REGISTRATION",
        "aircraft_id": aircraft,
        "flight_id": fid,
        "origin_airport_id": origin,
        "destination_airport_id": dest,
        "event_start_time": dep,
        "event_end_time": arr,
        "split": split,
    }


def t(hour=6, minute=0):
    return datetime(2019, 1, 1, hour, tzinfo=UTC) + timedelta(minutes=minute)


def build_cell(airport, n, offset=0, gap=60):
    """n single-leg arrivals at `airport` (each with no same-aircraft follow-on)."""
    rows = []
    for i in range(n):
        h = (i + offset) % 20
        rows.append(flight(f"f_{airport}_{i + offset}", f"ac_{airport}_{i + offset}",
                           "ORIG", airport, t(h), t(h, 40)))
    return rows


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    rows = build_cell("B", 50)
    first = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")
    second = build_data2_downstream_exposure(list(reversed(rows)), fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data2_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION
    assert first.horizon_minutes == 360


def test_median_per_connection_airport_and_units():
    # B: every arrival has exactly 1 same-aircraft follow-on within 360
    rows_b = []
    for i in range(50):
        h = i % 20
        ac = f"acB_{i}"
        rows_b.append(flight(f"b{i}_a", ac, "ORIG", "B", t(h), t(h, 40)))
        rows_b.append(flight(f"b{i}_b", ac, "B", "DEST", t(h, 100), t(h, 140)))
    # D: arrivals with 2 follow-ons each
    rows_d = []
    for i in range(50):
        h = i % 20
        ac = f"acD_{i}"
        rows_d.append(flight(f"d{i}_a", ac, "ORIG", "D", t(h), t(h, 40)))
        rows_d.append(flight(f"d{i}_b", ac, "D", "X", t(h, 100), t(h, 140)))
        rows_d.append(flight(f"d{i}_c", ac, "D", "Y", t(h, 200), t(h, 240)))
    ref = build_data2_downstream_exposure(rows_b + rows_d, fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_legs == 1.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_legs == 2.0 and cell_d.fallback_level == "AIRPORT_CELL"
    value = ref.lookup("B")
    assert value.value == 1.0
    assert value.unit == "legs"
    assert value.evidence_class is EvidenceClass.DERIVED
    assert value.support_ceiling is EvidenceClass.DERIVED
    assert value.support_state is SupportState.SUPPORTED


def test_min_cell_50_fallback_to_global_with_provenance():
    rows = build_cell("B", 50) + build_cell("E", 10, offset=1000)
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_legs == ref.global_value_legs
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert value.value == ref.global_value_legs
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_zero_coverage_airport_abstains():
    ref = build_data2_downstream_exposure(build_cell("B", 50), fit_period="2019-01..2019-06")
    value = ref.lookup("ZZZ_NO_COVERAGE")
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN
    assert value.reason_code == "NO_DOWNSTREAM_SCHEDULE_EVIDENCE"
    assert "REFERENCE_SOURCE_CRS_SCHEDULE" in value.quality_flags


def test_counting_uses_crs_schedule_not_actual_events():
    # Follow-on CRS departure inside the window even if the actual departure
    # (ignored field) lies outside the horizon: CRS schedule is the basis.
    rows = [
        flight("a1", "ac1", "ORIG", "B", t(6), t(6, 40)),
        {**flight("a2", "ac1", "B", "DEST", t(7), t(7, 40)),
         "actual_departure_utc": t(20), "actual_arrival_utc": t(20, 40)},
    ]
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_sample_count == 2
    # median of {1, 0} = 0.5
    assert ref.global_value_legs == 0.5


def test_horizon_boundary_inclusive_and_anchor_exclusive():
    rows = [
        flight("a1", "ac1", "ORIG", "B", t(6), t(6, 40)),
        flight("a2", "ac1", "B", "X", t(7, 0), t(7, 40)),    # dep exactly t0+20 -> counted
        flight("a3", "ac1", "B", "Y", t(7, 0), t(7, 40)),    # dep at t0+20 -> counted
    ]
    # t0 = 6:40; dep at 7:00 -> +20 min <= 360 -> both counted; N_down(a1) = 2
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_value_legs == 0.0  # median of {2, 0, 0}

    # boundary: dep exactly t0+360 counted; dep at t0+361 excluded
    rows2 = [
        flight("b1", "ac2", "ORIG", "C", t(6), t(6, 0)),
        flight("b2", "ac2", "C", "X", t(12, 0), t(12, 40)),   # dep t0+360 -> counted
        flight("b3", "ac2", "C", "Y", t(12, 1), t(12, 41)),   # dep t0+361 -> excluded
    ]
    ref2 = build_data2_downstream_exposure(rows2, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref2.global_value_legs == 0.0  # median of {1, 0, 0}

    # departure at or before t0 is excluded (zero/negative window)
    rows3 = [
        flight("c1", "ac3", "ORIG", "D", t(6), t(7)),
        flight("c2", "ac3", "D", "X", t(7), t(7, 40)),        # dep == t0 -> excluded
        flight("c3", "ac3", "D", "Y", t(6, 30), t(7, 10)),    # dep < t0 -> excluded
    ]
    ref3 = build_data2_downstream_exposure(rows3, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref3.global_value_legs == 0.0


def test_transitive_followons_are_counted_per_flight():
    rows = [
        flight("f1", "ac1", "A", "B", t(6), t(6, 40)),
        flight("f2", "ac1", "B", "C", t(7, 40), t(8, 20)),
        flight("f3", "ac1", "C", "D", t(9, 20), t(10, 0)),
    ]
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    # f1: future B-departures of ac1 within 360 = {f2} -> 1
    # f2: future C-departures = {f3} -> 1
    # f3: none -> 0
    assert ref.global_value_legs == 1.0


def test_other_airport_departures_are_not_counted():
    rows = [
        flight("f1", "ac1", "ORIG", "B", t(6), t(6, 40)),
        flight("f2", "ac1", "X", "C", t(7), t(7, 40)),  # different origin than B
    ]
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_value_legs == 0.0


def test_nontrain_rows_are_excluded_from_fit():
    train = build_cell("B", 50)
    base = build_data2_downstream_exposure(train, fit_period="2019-01..2019-06")
    dev = [flight("dev1", "ac_x", "B", "C", t(8), t(8, 40), split="development"),
           flight("dev2", "ac_x", "C", "D", t(9, 40), t(10, 20), split="development")]
    with_dev = build_data2_downstream_exposure(train + dev, fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 50


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    rows = build_cell("B", 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    rows = [flight("f1", "ac1", "A", "B", t(6), t(6, 40), split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    rows = build_cell("B", 50)
    rows[0]["dataset_instance_id"] = "data1_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_missing_schedule_field_rejected():
    rows = build_cell("B", 50)
    del rows[0]["event_start_time"]
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:event_start_time"):
        build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_rows_and_registry_state():
    rows = build_cell("B", 50) + build_cell("D", 50, offset=1000)
    ref = build_data2_downstream_exposure(rows, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 100
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert ref.support_state is SupportState.SUPPORTED
    assert ref.reason_code == "CRS_SCHEDULE_EXPECTED_EXPOSURE"
    assert isinstance(ref, Data2ExposureReference)

    registry = current_transformation_registry()
    rule = registry.get("DATA2_DOWNSTREAM_EXPOSURE", "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    assert "MIN_CELL_SIZE_50" in rule.formula_or_algorithm
    assert "360" in rule.formula_or_algorithm
    assert rule.evidence_class is EvidenceClass.DERIVED
    data1_rule = registry.get("EXPECTED_DOWNSTREAM_EXPOSURE", "1.0.0")
    assert data1_rule.status is TransformationStatus.FROZEN
    assert "N_down(H=360)" in data1_rule.formula_or_algorithm
    assert data1_rule.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE

    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-DOWNSTREAM-EXPOSURE" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-DOWNSTREAM-EXPOSURE")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert d2.evidence_class is EvidenceClass.DERIVED
    assert "D2-BTS-SCHEDULE" in d2.external_evidence_rule_ids


def test_data1_chain_exposure_remains_degraded_empirical():
    from model.PRE.reference.exposure import build_downstream_exposure

    rows1 = []
    for i in range(50):
        first = datetime(2019, 1, 1, i % 20, tzinfo=UTC)
        rows1.append({"dataset_instance_id": "data1_2019", "aircraft_id_namespace": "ICAO24",
                      "aircraft_id": f"ac_{i}", "flight_id": f"f{i}_a",
                      "origin_airport_id": "ORIG", "destination_airport_id": "B",
                      "event_start_time": first, "event_end_time": first + timedelta(minutes=60),
                      "first_seen_utc": first, "split": "train"})
        rows1.append({"dataset_instance_id": "data1_2019", "aircraft_id_namespace": "ICAO24",
                      "aircraft_id": f"ac_{i}", "flight_id": f"f{i}_b",
                      "origin_airport_id": "B", "destination_airport_id": "DEST",
                      "event_start_time": first + timedelta(minutes=120),
                      "event_end_time": first + timedelta(minutes=180),
                      "first_seen_utc": first + timedelta(minutes=120), "split": "train"})
    data1_ref = build_downstream_exposure(rows1, fit_period="2019-01..2019-06")
    data1_value = data1_ref.lookup("B")
    assert data1_value.support_state is SupportState.DEGRADED
    assert data1_value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE
    assert "TRAIN_CHAIN_EXPECTED_EXPOSURE" in data1_value.reason_code

    data2_ref = build_data2_downstream_exposure(build_cell("B", 50), fit_period="2019-01..2019-06")
    data2_value = data2_ref.lookup("B")
    assert data2_value.support_state is SupportState.SUPPORTED
    assert data2_value.evidence_class is EvidenceClass.DERIVED