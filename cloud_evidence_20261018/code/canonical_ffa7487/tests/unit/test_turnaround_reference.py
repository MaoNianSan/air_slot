from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.turnaround import (
    RULE_ID,
    RULE_VERSION,
    TurnaroundReference,
    build_turnaround_reference,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError

UTC = timezone.utc


def leg(fid, first_hour, origin, destination, aircraft="a1", minutes=60, split="train"):
    first = datetime(2019, 1, 1, first_hour, tzinfo=UTC)
    last = first + timedelta(minutes=minutes)
    return {
        "dataset_instance_id": "data1_2019",
        "aircraft_id_namespace": "ICAO24",
        "aircraft_id": aircraft,
        "flight_id": fid,
        "origin_airport_id": origin,
        "destination_airport_id": destination,
        "event_start_time": first,
        "event_end_time": last,
        "first_seen_utc": first,
        "last_seen_utc": last,
        "split": split,
    }


def two_legs(fid, airport, gap, start_hour, aircraft=None):
    aircraft = aircraft or f"ac_{fid}"
    first_a = datetime(2019, 1, 1, start_hour, tzinfo=UTC)
    first_b = first_a + timedelta(minutes=60 + gap)
    last_b = first_b + timedelta(minutes=60)
    return [
        leg(f"{fid}_a", start_hour, "ORIG", airport, aircraft=aircraft),
        {
            **leg(f"{fid}_b", 0, airport, "DEST", aircraft=aircraft),
            "event_start_time": first_b,
            "event_end_time": last_b,
            "first_seen_utc": first_b,
            "last_seen_utc": last_b,
        },
    ]


def build_airport_cell(airport, gap, n, offset=0):
    rows = []
    for i in range(n):
        rows.extend(two_legs(f"{airport}_{i + offset}", airport, gap, (i + offset) % 20))
    return rows


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    rows = []
    for i in range(50):
        rows.extend(two_legs(f"r{i}", "B", 60, i % 20))
    first = build_turnaround_reference(rows, fit_period="2019-01..2019-06")
    second = build_turnaround_reference(list(reversed(rows)), fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data1_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION


def test_median_per_airport_grouping_and_units():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("D", 120, 50)
    ref = build_turnaround_reference(rows, fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_minutes == 60.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_minutes == 120.0 and cell_d.fallback_level == "AIRPORT_CELL"
    assert ref.global_value_minutes == 90.0
    value = ref.lookup("B")
    assert value.value == 60.0
    assert value.unit == "minutes"
    assert value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE
    assert value.support_ceiling is EvidenceClass.EMPIRICAL_REFERENCE


def test_min_cell_50_fallback_to_global_with_provenance():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("E", 30, 10)
    ref = build_turnaround_reference(rows, fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_minutes == ref.global_value_minutes
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert value.value == ref.global_value_minutes
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_unknown_airport_resolves_to_global_fallback():
    ref = build_turnaround_reference(build_airport_cell("B", 60, 50), fit_period="2019-01..2019-06")
    value = ref.lookup("NOT_IN_TRAIN")
    assert value.value == ref.global_value_minutes
    assert value.support_state is SupportState.DEGRADED
    assert "REFERENCE_LEVEL_GLOBAL" in value.quality_flags


def test_proxy_basis_keeps_support_degraded_with_reason():
    ref = build_turnaround_reference(build_airport_cell("B", 60, 50), fit_period="2019-01..2019-06")
    value = ref.lookup("B")
    assert value.support_state is SupportState.DEGRADED
    assert value.reason_code
    assert "FLIGHTLIST_PROXY_GAP_REFERENCE" in value.reason_code
    assert "REFERENCE_SOURCE_FLIGHTLIST_PROXY" in value.quality_flags


def test_nontrain_rows_are_excluded_from_fit():
    train = build_airport_cell("B", 60, 50)
    base = build_turnaround_reference(train, fit_period="2019-01..2019-06")
    dev = [
        leg("dev1", 8, "B", "C", aircraft="ac_x"),
        leg("dev2", 10, "C", "D", aircraft="ac_x", split="development"),
    ]
    with_dev = build_turnaround_reference(train + dev, fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 50


def test_zero_and_negative_proxy_gaps_are_not_fit_evidence():
    rows = [
        leg("f1", 1, "A", "B"),
        leg("f2", 2, "B", "C"),  # zero gap: f1 last == f2 first
        leg("f3", 3, "C", "D"),
    ]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_GAPS"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)


def test_max_gap_360_boundary_from_chain_rule():
    rows = [
        leg("a", 1, "A", "B"),
        leg("b", 8, "B", "C"),  # gap exactly 360 minutes
        {
            **leg("c", 15, "C", "D"),
            "event_start_time": datetime(2019, 1, 1, 15, 1, tzinfo=UTC),
            "first_seen_utc": datetime(2019, 1, 1, 15, 1, tzinfo=UTC),
        },  # gap 361 minutes -> link rejected
    ]
    ref = build_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_sample_count == 1
    assert ref.global_value_minutes == 360.0


def test_firstseen_lastseen_drive_proxy_gap_not_event_times():
    first = datetime(2019, 1, 1, 1, 0, tzinfo=UTC)
    rows = [
        {
            **leg("f1", 1, "A", "B"),
            "event_end_time": first + timedelta(hours=6),
            "last_seen_utc": first,
        },
        {
            **leg("f2", 8, "B", "C"),
            "first_seen_utc": datetime(2019, 1, 1, 8, 30, tzinfo=UTC),
            "event_start_time": datetime(2019, 1, 1, 8, 30, tzinfo=UTC),
        },
    ]
    with pytest.raises(ContractError, match="REFERENCE_PROXY_GAP_OUT_OF_DOMAIN"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    rows = build_airport_cell("B", 60, 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    rows = [leg("f1", 1, "A", "B", split="development"), leg("f2", 3, "B", "C", split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    rows = build_airport_cell("B", 60, 50)
    rows[0]["dataset_instance_id"] = "data2_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_missing_proxy_time_field_rejected():
    rows = build_airport_cell("B", 60, 50)
    del rows[0]["first_seen_utc"]
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:first_seen_utc"):
        build_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_gaps_only_and_is_reproducible():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("D", 120, 50)
    ref = build_turnaround_reference(rows, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 100
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert ref.support_state is SupportState.DEGRADED
    assert isinstance(ref, TurnaroundReference)


def test_registry_frozen_rule_and_legacy_candidate_coexist():
    registry = current_transformation_registry()
    frozen = registry.get("TURNAROUND_REFERENCE", "1.0.0")
    assert frozen.status is TransformationStatus.FROZEN
    assert frozen.construction_type.value == "TRAIN_FROZEN_REFERENCE"
    assert "MIN_CELL_SIZE_50" in frozen.formula_or_algorithm
    assert "MIN_CELL_50" in frozen.support_rule
    candidate = registry.get("TURNAROUND_REFERENCE", "0.1.0")
    assert candidate.status is TransformationStatus.DEVELOPMENT_CANDIDATE
    assert candidate.reason_code == "CONSTRUCTION_RULE_NOT_FROZEN"
