from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.taxi import (
    RULE_ID,
    RULE_VERSION,
    TaxiReference,
    build_taxi_reference,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.PRE.canonical.normalization import canonicalize_trajectory_event
from model.PRE.episode.event_detection import (
    MotionState,
    TrajectoryDetectorConfig,
    TrajectoryEventRecord,
)
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError

UTC = timezone.utc


def traj(event_type, t, *, aircraft="a1", flags=()):
    return canonicalize_trajectory_event(TrajectoryEventRecord(
        event_type=event_type, event_time=t, aircraft_id=aircraft,
        prev_time=t - timedelta(minutes=1), cur_time=t,
        prev_state=MotionState.TAXI, cur_state=MotionState.AIR,
        support_state=SupportState.SUPPORTED, quality_flags=flags,
        detector_parameters=TrajectoryDetectorConfig().parameters()), flight_id="F1")


def flight(fid, airport, first_hour, last_hour, aircraft="a1", split="train"):
    return {
        "dataset_instance_id": "data1_2019",
        "aircraft_id": aircraft,
        "flight_id": fid,
        "origin_airport_id": airport,
        "first_seen_utc": datetime(2019, 1, 1, first_hour, tzinfo=UTC),
        "last_seen_utc": datetime(2019, 1, 1, last_hour, tzinfo=UTC),
        "split": split,
    }


def pair(airport, taxi_minutes, idx, aircraft=None):
    aircraft = aircraft or f"ac_{idx}"
    fid = f"f_{airport}_{idx}"
    first = datetime(2019, 1, 1, idx % 20, tzinfo=UTC)
    events = [
        traj("OUT_BLOCK_PROXY", first + timedelta(minutes=10), aircraft=aircraft),
        traj("TAKEOFF", first + timedelta(minutes=10 + taxi_minutes), aircraft=aircraft),
    ]
    return flight(fid, airport, idx % 20, (idx % 20) + 3, aircraft=aircraft), events


def build_cell(airport, taxi_minutes, n, offset=0):
    flights, events = [], []
    for i in range(n):
        f, ev = pair(airport, taxi_minutes, i + offset)
        flights.append(f)
        events.extend(ev)
    return flights, events


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    flights, events = build_cell("B", 15, 50)
    first = build_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    second = build_taxi_reference(list(reversed(flights)), events, fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data1_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION


def test_median_per_origin_airport_and_units():
    flights_b, events_b = build_cell("B", 15, 50)
    flights_d, events_d = build_cell("D", 35, 50, offset=1000)
    ref = build_taxi_reference(flights_b + flights_d, events_b + events_d,
                               fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_minutes == 15.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_minutes == 35.0 and cell_d.fallback_level == "AIRPORT_CELL"
    assert ref.global_value_minutes == 25.0
    value = ref.lookup("B")
    assert value.value == 15.0
    assert value.unit == "minutes"
    assert value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE


def test_min_cell_50_fallback_to_global_with_provenance():
    flights_b, events_b = build_cell("B", 15, 50)
    flights_e, events_e = build_cell("E", 5, 10)
    ref = build_taxi_reference(flights_b + flights_e, events_b + events_e,
                               fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_minutes == ref.global_value_minutes
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert value.value == ref.global_value_minutes
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_zero_coverage_airport_abstains_per_option_a():
    flights, events = build_cell("B", 15, 50)
    ref = build_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    value = ref.lookup("ZZZ_NO_COVERAGE")
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN
    assert value.reason_code == "NO_TAXI_TRAJECTORY_EVIDENCE"


def test_proxy_named_events_keep_reference_degraded():
    flights, events = build_cell("B", 15, 50)
    ref = build_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    value = ref.lookup("B")
    assert value.support_state is SupportState.DEGRADED
    assert "TRAJECTORY_PAIR_TAXI_REFERENCE" in value.reason_code
    assert "REFERENCE_SOURCE_TRAJECTORY_PAIR" in value.quality_flags


def test_nontrain_flights_are_excluded_from_fit():
    flights, events = build_cell("B", 15, 50)
    base = build_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    dev_flight, dev_events = pair("X", 99, 999, aircraft="ac_dev")
    dev_flight["split"] = "development"
    with_dev = build_taxi_reference(flights + [dev_flight], events + dev_events,
                                    fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 50


def test_incomplete_pair_excluded():
    flights = [flight("f1", "B", 1, 3)]
    events = [traj("OUT_BLOCK_PROXY", datetime(2019, 1, 1, 1, 10, tzinfo=UTC))]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_PAIRS"):
        build_taxi_reference(flights, events, fit_period="2019-01..2019-06", min_cell_size=1)


def test_reversed_pair_order_excluded():
    flights = [flight("f1", "B", 1, 3)]
    events = [
        traj("TAKEOFF", datetime(2019, 1, 1, 1, 10, tzinfo=UTC)),
        traj("OUT_BLOCK_PROXY", datetime(2019, 1, 1, 1, 25, tzinfo=UTC)),
    ]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_PAIRS"):
        build_taxi_reference(flights, events, fit_period="2019-01..2019-06", min_cell_size=1)


def test_events_outside_flight_window_excluded():
    flights = [flight("f1", "B", 1, 2)]
    events = [
        traj("OUT_BLOCK_PROXY", datetime(2019, 1, 1, 0, 10, tzinfo=UTC)),
        traj("TAKEOFF", datetime(2019, 1, 1, 4, 0, tzinfo=UTC)),
    ]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_PAIRS"):
        build_taxi_reference(flights, events, fit_period="2019-01..2019-06", min_cell_size=1)


def test_latest_event_per_type_is_the_tie_break():
    flights = [flight("f1", "B", 1, 3)]
    events = [
        traj("OUT_BLOCK_PROXY", datetime(2019, 1, 1, 1, 10, tzinfo=UTC)),
        traj("OUT_BLOCK_PROXY", datetime(2019, 1, 1, 1, 12, tzinfo=UTC)),
        traj("TAKEOFF", datetime(2019, 1, 1, 1, 25, tzinfo=UTC)),
    ]
    ref = build_taxi_reference(flights, events, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_value_minutes == 13.0


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    flights, events = build_cell("B", 15, 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_taxi_reference(flights, events, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    flights = [flight("f1", "B", 1, 3, split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_taxi_reference(flights, [], fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    flights, events = build_cell("B", 15, 50)
    flights[0]["dataset_instance_id"] = "data2_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_taxi_reference(flights, events, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_pairs_and_registry_state():
    flights, events = build_cell("B", 15, 50)
    ref = build_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 50
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert isinstance(ref, TaxiReference)
    registry = current_transformation_registry()
    frozen = registry.get("TAXI_REFERENCE", "1.0.0")
    assert frozen.status is TransformationStatus.FROZEN
    assert "MIN_CELL_SIZE_50" in frozen.formula_or_algorithm
    candidate = registry.get("TAXI_REFERENCE", "0.1.0")
    assert candidate.status is TransformationStatus.DEVELOPMENT_CANDIDATE
    assert candidate.reason_code == "CONSTRUCTION_RULE_NOT_FROZEN"
