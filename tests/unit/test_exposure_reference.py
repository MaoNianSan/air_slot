from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.exposure import (
    RULE_ID,
    RULE_VERSION,
    ExposureReference,
    build_downstream_exposure,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError

UTC = timezone.utc


def leg(fid, hour, origin, destination, aircraft="a1", minutes=60, split="train"):
    first = datetime(2019, 1, 1, hour, tzinfo=UTC)
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
        "split": split,
    }


def chain_count2(aircraft, dest):  # f1 has 2 successors within H=360
    return [
        leg(f"{aircraft}_1", 1, "ORIG", dest, aircraft),
        leg(f"{aircraft}_2", 3, dest, "MID", aircraft),
        leg(f"{aircraft}_3", 5, "MID", "END", aircraft),
    ]


def chain_count1(aircraft, dest):  # f1 has 1 successor within H=360 (third leg at +7h)
    return [
        leg(f"{aircraft}_1", 1, "ORIG", dest, aircraft),
        leg(f"{aircraft}_2", 3, dest, "MID", aircraft),
        leg(f"{aircraft}_3", 8, "MID", "END", aircraft),
    ]


def build_cell(chain_builder, dest, n, offset=0):
    rows = []
    for i in range(n):
        rows.extend(chain_builder(f"ac_{i + offset}", dest))
    return rows


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    rows = build_cell(chain_count1, "B", 50)
    first = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    second = build_downstream_exposure(list(reversed(rows)), fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION
    assert first.horizon_minutes == 360


def test_median_per_connection_airport_and_units():
    rows = build_cell(chain_count1, "B", 50, offset=0) + build_cell(chain_count2, "D", 50, offset=1000)
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_legs == 1.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_legs == 2.0 and cell_d.fallback_level == "AIRPORT_CELL"
    assert ref.global_value_legs == 1.0
    value = ref.lookup("B")
    assert value.value == 1.0
    assert value.unit == "legs"
    assert value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE


def test_horizon_360_boundary_counts_successor_at_exactly_360():
    rows = chain_count2("ac_x", "B")  # f3 at 5:00 -> 240 min, counted
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.lookup("B").value == 2.0


def test_horizon_excludes_successor_beyond_360():
    rows = chain_count1("ac_x", "B")  # f3 at 8:00 -> 420 min, not counted
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.lookup("B").value == 1.0


def test_min_cell_50_fallback_to_global_with_provenance():
    rows = build_cell(chain_count1, "B", 50) + build_cell(chain_count1, "E", 10, offset=2000)
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_legs == ref.global_value_legs
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_zero_coverage_airport_abstains():
    rows = build_cell(chain_count1, "B", 50)
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    value = ref.lookup("ZZZ_NO_COVERAGE")
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN
    assert value.reason_code == "NO_DOWNSTREAM_CHAIN_EVIDENCE"


def test_archive_chain_keeps_reference_degraded():
    rows = build_cell(chain_count1, "B", 50)
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    value = ref.lookup("B")
    assert value.support_state is SupportState.DEGRADED
    assert "TRAIN_CHAIN_EXPECTED_EXPOSURE" in value.reason_code
    assert "REFERENCE_SOURCE_TRAIN_CHAIN" in value.quality_flags


def test_nontrain_flights_are_excluded_from_fit():
    rows = build_cell(chain_count1, "B", 50)
    base = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    dev = chain_count1("ac_dev", "X")
    for row in dev:
        row["split"] = "development"
    with_dev = build_downstream_exposure(rows + dev, fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 150


def test_airport_discontinuity_breaks_chain_and_yields_zero_exposure():
    rows = [
        leg("f1", 1, "A", "B"),
        leg("f2", 3, "X", "C"),  # no airport continuity
    ]
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_value_legs == 0.0
    assert ref.lookup("B").value == 0.0


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    rows = build_cell(chain_count1, "B", 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    rows = [leg("f1", 1, "A", "B", split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    rows = build_cell(chain_count1, "B", 50)
    rows[0]["dataset_instance_id"] = "data2_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_missing_chain_identity_key_rejected():
    rows = build_cell(chain_count1, "B", 50)
    del rows[0]["destination_airport_id"]
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:destination_airport_id"):
        build_downstream_exposure(rows, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_flights_and_registry_state():
    rows = build_cell(chain_count1, "B", 50)
    ref = build_downstream_exposure(rows, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 150
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert isinstance(ref, ExposureReference)
    registry = current_transformation_registry()
    frozen = registry.get("EXPECTED_DOWNSTREAM_EXPOSURE", "1.0.0")
    assert frozen.status is TransformationStatus.FROZEN
    assert "H=360" in frozen.formula_or_algorithm
    candidate = registry.get("EXPECTED_DOWNSTREAM_EXPOSURE", "0.1.0")
    assert candidate.status is TransformationStatus.DEVELOPMENT_CANDIDATE
