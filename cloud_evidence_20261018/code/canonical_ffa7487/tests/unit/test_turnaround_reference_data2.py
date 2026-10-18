from datetime import datetime, timedelta, timezone

import pytest

from model.PRE.reference.turnaround_data2 import (
    RULE_ID,
    RULE_VERSION,
    Data2TurnaroundReference,
    build_data2_turnaround_reference,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from pathlib import Path

UTC = timezone.utc


def leg(fid, aircraft, origin, destination, arr, dep, *, crs_shift=15,
        split="train", dataset="data2_2019"):
    """DIRECT-gate flight row: actual arr/dep plus CRS anchor fields.

    event_start_time = pred.CRSArr, event_end_time = pred.CRSDep (D2-2 anchors).
    """
    return {
        "dataset_instance_id": dataset,
        "aircraft_id_namespace": "REGISTRATION",
        "aircraft_id": aircraft,
        "flight_id": fid,
        "origin_airport_id": origin,
        "destination_airport_id": destination,
        "event_start_time": arr - timedelta(minutes=crs_shift),
        "event_end_time": dep - timedelta(minutes=crs_shift),
        "actual_arrival_utc": arr,
        "actual_departure_utc": dep,
        "split": split,
    }


def two_legs(fid, airport, gap, start_hour, aircraft=None):
    """Pred arrives at `airport` at t (departs t+30); succ departs t+gap.

    Requires gap > 30 so the successor sorts after the predecessor in the
    actual-departure ordering; the DIRECT gate turnaround gap equals `gap`.
    """
    aircraft = aircraft or f"ac_{fid}"
    t = datetime(2019, 1, 1, start_hour, tzinfo=UTC)
    return [
        leg(f"{fid}_a", aircraft, "ORIG", airport, t, t + timedelta(minutes=30)),
        leg(f"{fid}_b", aircraft, airport, "DEST",
            t + timedelta(minutes=gap + 30), t + timedelta(minutes=gap)),
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
    first = build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")
    second = build_data2_turnaround_reference(list(reversed(rows)), fit_period="2019-01..2019-06")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data2_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION


def test_median_per_airport_grouping_and_units():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("D", 120, 50)
    ref = build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")
    cell_b = next(c for c in ref.cells if c.airport_id == "B")
    cell_d = next(c for c in ref.cells if c.airport_id == "D")
    assert cell_b.value_minutes == 60.0 and cell_b.fallback_level == "AIRPORT_CELL"
    assert cell_d.value_minutes == 120.0 and cell_d.fallback_level == "AIRPORT_CELL"
    assert ref.global_value_minutes == 90.0
    value = ref.lookup("B")
    assert value.value == 60.0
    assert value.unit == "minutes"
    assert value.evidence_class is EvidenceClass.DIRECT
    assert value.support_ceiling is EvidenceClass.DIRECT


def test_min_cell_50_fallback_to_global_with_provenance():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("E", 45, 10)
    ref = build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")
    cell_e = next(c for c in ref.cells if c.airport_id == "E")
    assert cell_e.sample_count == 10
    assert cell_e.value_minutes == ref.global_value_minutes
    assert cell_e.fallback_level == "GLOBAL"
    value = ref.lookup("E")
    assert value.value == ref.global_value_minutes
    assert "FALLBACK_GLOBAL" in value.reason_code
    assert "REFERENCE_CELL_MIN_SUPPORT_FALLBACK" in value.quality_flags


def test_unknown_airport_resolves_to_global_fallback():
    ref = build_data2_turnaround_reference(build_airport_cell("B", 60, 50),
                                           fit_period="2019-01..2019-06")
    value = ref.lookup("NOT_IN_TRAIN")
    assert value.value == ref.global_value_minutes
    assert value.support_state is SupportState.SUPPORTED
    assert "REFERENCE_LEVEL_GLOBAL" in value.quality_flags


def test_direct_actual_basis_is_supported_with_reason():
    ref = build_data2_turnaround_reference(build_airport_cell("B", 60, 50),
                                           fit_period="2019-01..2019-06")
    value = ref.lookup("B")
    assert value.support_state is SupportState.SUPPORTED
    assert value.reason_code
    assert "DIRECT_GATE_TURNAROUND_REFERENCE" in value.reason_code
    assert "REFERENCE_SOURCE_DIRECT_GATE_ACTUALS" in value.quality_flags
    assert value.evidence_class is EvidenceClass.DIRECT
    assert value.support_ceiling is EvidenceClass.DIRECT


def test_data1_proxy_reference_remains_degraded_empirical():
    from model.PRE.reference.turnaround import (
        build_turnaround_reference as build_data1_turnaround_reference,
    )

    data2_ref = build_data2_turnaround_reference(build_airport_cell("B", 60, 50),
                                                 fit_period="2019-01..2019-06")
    data2_value = data2_ref.lookup("B")
    assert data2_value.support_state is SupportState.SUPPORTED
    assert data2_value.evidence_class is EvidenceClass.DIRECT

    data1_rows = [
        {
            **row,
            "dataset_instance_id": "data1_2019",
            "first_seen_utc": row["actual_arrival_utc"],
            "last_seen_utc": row["actual_departure_utc"],
        }
        for row in build_airport_cell("B", 60, 50)
    ]
    data1_ref = build_data1_turnaround_reference(data1_rows, fit_period="2019-01..2019-06")
    data1_value = data1_ref.lookup("B")
    assert data1_value.support_state is SupportState.DEGRADED
    assert data1_value.evidence_class is EvidenceClass.EMPIRICAL_REFERENCE
    assert "FLIGHTLIST_PROXY_GAP_REFERENCE" in data1_value.reason_code


def test_nontrain_rows_are_excluded_from_fit():
    train = build_airport_cell("B", 60, 50)
    base = build_data2_turnaround_reference(train, fit_period="2019-01..2019-06")
    t = datetime(2019, 1, 1, 8, 0, tzinfo=UTC)
    dev = [
        leg("dev1", "ac_x", "B", "C", t, t + timedelta(minutes=40)),
        leg("dev2", "ac_x", "C", "D", t + timedelta(minutes=70), t + timedelta(minutes=130),
            split="development"),
    ]
    with_dev = build_data2_turnaround_reference(train + dev, fit_period="2019-01..2019-06")
    assert base == with_dev
    assert with_dev.global_sample_count == 50


def test_zero_and_negative_actual_gate_gaps_are_not_fit_evidence():
    t = datetime(2019, 1, 1, 1, 0, tzinfo=UTC)
    rows = [
        leg("f1", "a1", "A", "B", t + timedelta(minutes=60), t + timedelta(minutes=30)),
        leg("f2", "a1", "B", "C", t + timedelta(minutes=105), t + timedelta(minutes=60)),
    ]
    # f2 dep == f1 arr (zero gate gap) -> time order invalid -> link rejected
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_GAPS"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)

    rows_neg = [
        leg("f1", "a1", "A", "B", t + timedelta(minutes=60), t + timedelta(minutes=30)),
        leg("f2", "a1", "B", "C", t + timedelta(minutes=105), t + timedelta(minutes=45)),
    ]
    # f2 dep (1:45) < f1 arr (2:00) -> negative gate gap -> link rejected
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_GAPS"):
        build_data2_turnaround_reference(rows_neg, fit_period="2019-01..2019-06", min_cell_size=1)


def test_max_gap_360_boundary_from_chain_rule():
    t = datetime(2019, 1, 1, 1, 0, tzinfo=UTC)
    rows = [
        leg("a", "a1", "A", "B", t, t + timedelta(minutes=30)),
        leg("b", "a1", "B", "C", t + timedelta(minutes=390), t + timedelta(minutes=360)),
        leg("c", "a1", "C", "D", t + timedelta(minutes=781), t + timedelta(minutes=751)),
    ]
    ref = build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref.global_sample_count == 1
    assert ref.global_value_minutes == 360.0


def test_actual_gate_times_drive_reference_not_crs_anchors():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    rows_a = [
        leg("p", "a1", "A", "B", t, t + timedelta(minutes=40), crs_shift=15),
        leg("s", "a1", "B", "C", t + timedelta(minutes=100), t + timedelta(minutes=60),
            crs_shift=15),
    ]
    rows_b = [
        leg("p", "a1", "A", "B", t, t + timedelta(minutes=40), crs_shift=120),
        leg("s", "a1", "B", "C", t + timedelta(minutes=100), t + timedelta(minutes=60),
            crs_shift=120),
    ]
    ref_a = build_data2_turnaround_reference(rows_a, fit_period="2019-01..2019-06", min_cell_size=1)
    ref_b = build_data2_turnaround_reference(rows_b, fit_period="2019-01..2019-06", min_cell_size=1)
    assert ref_a == ref_b
    assert ref_a.global_value_minutes == 60.0


def test_inverted_crs_window_pairs_are_excluded_from_fit():
    t = datetime(2019, 1, 1, 6, 0, tzinfo=UTC)
    rows = [
        leg("p", "a1", "A", "B", t, t + timedelta(minutes=30), crs_shift=-60),
        leg("s", "a1", "B", "C", t + timedelta(minutes=120), t + timedelta(minutes=90),
            crs_shift=60),
    ]
    # pred.CRSArr (t+60) >= succ.CRSDep (t+30) -> inverted schedule window
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_NO_LEGAL_GAPS"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06", min_cell_size=1)


def test_global_below_min_cell_size_raises_explicit_fit_failure():
    rows = build_airport_cell("B", 60, 10)
    with pytest.raises(ContractError, match="REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_empty_train_partition_raises():
    rows = [leg("f1", "a1", "A", "B", datetime(2019, 1, 1, 1, tzinfo=UTC),
                datetime(2019, 1, 1, 1, 30, tzinfo=UTC), split="development"),
            leg("f2", "a1", "B", "C", datetime(2019, 1, 1, 3, tzinfo=UTC),
                datetime(2019, 1, 1, 2, 30, tzinfo=UTC), split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_dataset_boundary_isolation():
    rows = build_airport_cell("B", 60, 50)
    rows[0]["dataset_instance_id"] = "data1_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_missing_actual_field_rejected():
    rows = build_airport_cell("B", 60, 50)
    del rows[0]["actual_departure_utc"]
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:actual_departure_utc"):
        build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")


def test_manifest_freezes_train_gaps_only_and_is_reproducible():
    rows = build_airport_cell("B", 60, 50) + build_airport_cell("D", 120, 50)
    ref = build_data2_turnaround_reference(rows, fit_period="2019-01..2019-06")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.global_sample_count == 100
    assert ref.minimum_support_rule == "MIN_CELL_SIZE_50"
    assert ref.fallback_hierarchy == ("AIRPORT_CELL", "GLOBAL")
    assert ref.support_state is SupportState.SUPPORTED
    assert ref.reason_code == "DIRECT_GATE_TURNAROUND_REFERENCE"
    assert isinstance(ref, Data2TurnaroundReference)


def test_registry_frozen_rule_and_data1_rule_untouched():
    registry = current_transformation_registry()
    rule = registry.get("DATA2_TURNAROUND_REFERENCE", "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    assert rule.construction_type.value == "TRAIN_FROZEN_REFERENCE"
    assert "MIN_CELL_SIZE_50" in rule.formula_or_algorithm
    assert "actual_departure_utc" in rule.formula_or_algorithm
    assert rule.evidence_class is EvidenceClass.DIRECT
    data1_rule = registry.get("TURNAROUND_REFERENCE", "1.0.0")
    assert data1_rule.status is TransformationStatus.FROZEN
    assert "first_seen_utc" in data1_rule.formula_or_algorithm
    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-TURNAROUND-REFERENCE" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-TURNAROUND-REFERENCE")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert d2.evidence_class is EvidenceClass.DIRECT
    assert "D2-BTS-ACTUAL" in d2.external_evidence_rule_ids
    assert "D2-CHAIN-GATE-GAP" in d2.external_evidence_rule_ids