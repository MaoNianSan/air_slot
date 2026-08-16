from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.taxi_data2 import (
    RULE_ID,
    RULE_VERSION,
    Data2TaxiReference,
    build_data2_taxi_reference,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from pathlib import Path

UTC = timezone.utc


def row(fid, airport, taxi_out, *, aircraft="a1", split="train", dataset="data2_2019"):
    return {
        "dataset_instance_id": dataset,
        "aircraft_id": aircraft,
        "flight_id": fid,
        "origin_airport_id": airport,
        "taxi_out_minutes": taxi_out,
        "split": split,
    }


def build_cell(airport, taxi_minutes, n, offset=0):
    return [row(f"{airport}_{i + offset}", airport, taxi_minutes) for i in range(n)]


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    rows = build_cell("B", 15, 50)
    first = build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")
    second = build_data2_taxi_reference(list(reversed(rows)), fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data2_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION


def test_median_per_origin_airport_and_units():
    rows = build_cell("B", 15, 50) + build_cell("D", 35, 50, offset=1000)
    ref = build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_minutes == 15.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_minutes == 35.0 and cell_d.fallback_level == "AIRPORT_CELL"
    assert ref.global_value_minutes == 25.0
    value = ref.lookup("B")
    assert value.value == 15.0
    assert value.unit == "minutes"
    assert value.evidence_class is EvidenceClass.DIRECT
    assert value.support_ceiling is EvidenceClass.DIRECT


def test_min_cell_50_fallback_to_global_with_provenance():
    rows = build_cell("B", 15, 50) + build_cell("E", 5, 10)
    ref = build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_minutes == ref.global_value_minutes
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert value.value == ref.global_value_minutes
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_zero_coverage_airport_abstains_per_option_a():
    ref = build_data2_taxi_reference(build_cell("B", 15, 50), fit_period="2019-01..2019-06")
    value = ref.lookup("ZZZ_NO_COVERAGE")
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN
    assert value.reason_code == "NO_TAXI_DIRECT_EVIDENCE"
    assert "REFERENCE_SOURCE_DIRECT_TAXI_OUT" in value.quality_flags


def test_direct_official_column_support_supported_with_reason():
    ref = build_data2_taxi_reference(build_cell("B", 15, 50), fit_period="2019-01..2019-06")
    value = ref.lookup("B")
    assert value.support_state is SupportState.SUPPORTED
    assert "DIRECT_TAXI_OUT_REFERENCE" in value.reason_code
    assert "REFERENCE_SOURCE_DIRECT_TAXI_OUT" in value.quality_flags
    assert value.evidence_class is EvidenceClass.DIRECT
    assert value.support_ceiling is EvidenceClass.DIRECT


def test_data1_proxy_reference_remains_degraded_empirical():
    from model.PRE.canonical.normalization import canonicalize_trajectory_event
    from model.PRE.episode.event_detection import (
        MotionState,
        TrajectoryDetectorConfig,
        TrajectoryEventRecord,
    )
    from model.PRE.reference.taxi import build_taxi_reference as build_data1_taxi_reference

    def traj(event_type, t, aircraft):
        return canonicalize_trajectory_event(TrajectoryEventRecord(
            event_type=event_type, event_time=t, aircraft_id=aircraft,
            prev_time=t - timedelta(minutes=1), cur_time=t,
            prev_state=MotionState.TAXI, cur_state=MotionState.AIR,
            support_state=SupportState.SUPPORTED, quality_flags=(),
            detector_parameters=TrajectoryDetectorConfig().parameters()), flight_id="F1")

    flights, events = [], []
    for i in range(50):
        first = datetime(2019, 1, 1, i % 20, tzinfo=UTC)
        flights.append({"dataset_instance_id": "data1_2019", "aircraft_id": f"ac_{i}",
                        "flight_id": f"f_{i}", "origin_airport_id": "B",
                        "first_seen_utc": first, "last_seen_utc": first + timedelta(hours=3),
                        "split": "train"})
        events.append(traj("OUT_BLOCK_PROXY", first + timedelta(minutes=10), f"ac_{i}"))
        events.append(traj("TAKEOFF", first + timedelta(minutes=25), f"ac_{i}"))

    data1_ref = build_data1_taxi_reference(flights, events, fit_period="2019-01..2019-06")
    data1_value = data1_ref.lookup("B")
    assert data1_value.support_state is SupportState.DEGRADED
    assert data1_value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE
    assert "TRAJECTORY_PAIR_TAXI_REFERENCE" in data1_value.reason_code

    data2_ref = build_data2_taxi_reference(build_cell("B", 15, 50), fit_period="2019-01..2019-06")
    data2_value = data2_ref.lookup("B")
    assert data2_value.support_state is SupportState.SUPPORTED
    assert data2_value.evidence_class is EvidenceClass.DIRECT


def test_nontrain_rows_are_excluded_from_fit():
    train = build_cell("B", 15, 50)
    base = build_data2_taxi_reference(train, fit_period="2019-01..2019-06")
    dev = [row("dev1", "X", 99, aircraft="ac_dev", split="development")]
    with_dev = build_data2_taxi_reference(train + dev, fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 50


def test_zero_and_negative_taxi_values_are_not_fit_evidence():
    rows = [
        row("f1", "B", 0),
        row("f2", "B", -5),
        row("f3", "B", "not-a-number"),
    ]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_VALUES"):
        build_data2_taxi_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    mixed = [row("f0", "B", 12)] + rows
    ref = build_data2_taxi_reference(mixed, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_sample_count == 1
    assert ref.global_value_minutes == 12.0


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    rows = build_cell("B", 15, 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    rows = [row("f1", "B", 15, split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    rows = build_cell("B", 15, 50)
    rows[0]["dataset_instance_id"] = "data1_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")


def test_missing_field_rejected():
    rows = build_cell("B", 15, 50)
    del rows[0]["taxi_out_minutes"]
    with pytest.raises(ContractError, match="REFERENCE_FLIGHT_MISSING:taxi_out_minutes"):
        build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_rows_and_registry_state():
    rows = build_cell("B", 15, 50) + build_cell("D", 35, 50, offset=1000)
    ref = build_data2_taxi_reference(rows, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 100
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert ref.support_state is SupportState.SUPPORTED
    assert ref.reason_code == "DIRECT_TAXI_OUT_REFERENCE"
    assert isinstance(ref, Data2TaxiReference)

    registry = current_transformation_registry()
    rule = registry.get("DATA2_TAXI_REFERENCE", "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    assert "MIN_CELL_SIZE_50" in rule.formula_or_algorithm
    assert "TaxiOut" in rule.formula_or_algorithm
    assert rule.evidence_class is EvidenceClass.DIRECT
    data1_rule = registry.get("TAXI_REFERENCE", "1.0.0")
    assert data1_rule.status is TransformationStatus.FROZEN
    assert "OUT_BLOCK_PROXY" in data1_rule.formula_or_algorithm

    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-TAXI-REFERENCE" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-TAXI-REFERENCE")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert d2.evidence_class is EvidenceClass.DIRECT
    assert "D2-BTS-ACTUAL" in d2.external_evidence_rule_ids