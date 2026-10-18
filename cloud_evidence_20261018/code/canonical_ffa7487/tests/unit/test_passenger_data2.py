from pathlib import Path

import pytest

from model.PRE.reference.passenger_data2 import (
    RULE_ID,
    RULE_VERSION,
    Data2PassengerReference,
    build_data2_passenger_reference,
)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError


def coupon(origin, dest, passengers, *, rid="r1", period="2019", split="train",
           dataset="data2_2019"):
    return {
        "dataset_instance_id": dataset,
        "canonical_record_id": rid,
        "join_key": {"origin": origin, "destination": dest},
        "reference_period": period,
        "value": passengers,
        "split": split,
    }


def build_cell(origin, dest, n, *, offset=0, split="train"):
    return [coupon(origin, dest, (i + offset) % 7 + 1, rid=f"{origin}_{dest}_{i + offset}",
                   split=split) for i in range(n)]


def test_train_only_fit_is_reproducible_and_row_order_invariant():
    rows = build_cell("ATL", "ORD", 50)
    first = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    second = build_data2_passenger_reference(list(reversed(rows)), fit_period="2019-Q1")
    assert first == second
    assert first.reference_id == second.reference_id
    assert first.manifest_freeze_id == second.manifest_freeze_id
    assert first.dataset_instance_id == "data2_2019"
    assert first.rule_id == RULE_ID and first.rule_version == RULE_VERSION
    assert first.scale_factor == 10


def test_x10_scaling_of_route_sum():
    rows = [
        coupon("ATL", "ORD", 2),
        coupon("ATL", "ORD", 4),
        coupon("ATL", "ORD", 1),
    ]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    cell = ref.cells[0]
    assert cell.value_passengers == (2 + 4 + 1) * 10
    assert cell.sample_count == 3
    assert ref.total_passengers == 70.0
    assert ref.total_sample_count == 3
    assert ref.route_count == 1


def test_route_grain_is_directed():
    rows = [coupon("ATL", "ORD", 5), coupon("ORD", "ATL", 3)]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    assert ref.route_count == 2
    lookup = ref.lookup("ATL", "ORD")
    assert lookup.value == 50.0
    reverse = ref.lookup("ORD", "ATL")
    assert reverse.value == 30.0


def test_lookup_covered_route_is_supported():
    rows = [coupon("ATL", "ORD", 9)]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    result = ref.lookup("ATL", "ORD")
    assert result.value == 90.0
    assert result.unit == "passengers"
    assert result.evidence_class is EvidenceClass.DOMAIN_PROXY
    assert result.support_ceiling is EvidenceClass.DOMAIN_PROXY
    assert result.support_state is SupportState.SUPPORTED
    assert "REFERENCE_LEVEL_ROUTE" in result.quality_flags
    assert "REFERENCE_SOURCE_DB1B_COUPON_Q1" in result.quality_flags
    assert "REFERENCE_ROUTE_N=1" in result.quality_flags
    assert result.reason_code == "DB1B_COUPON_OFFICIAL_10PCT_X10;ROUTE_QUARTER_SUM"


def test_lookup_zero_coverage_route_abstains():
    ref = build_data2_passenger_reference([coupon("ATL", "ORD", 1)], fit_period="2019-Q1")
    result = ref.lookup("MIA", "LAX")
    assert result.value is None
    assert result.support_state is SupportState.ABSTAIN
    assert result.reason_code == "NO_DB1B_COUPON_ROUTE_EVIDENCE"
    assert result.quality_flags == ("REFERENCE_SOURCE_DB1B_COUPON_Q1",)


def test_placeholder_carriers_are_irrelevant_to_route_reference():
    # D2-7 decision: the reference key is (Origin, Dest) only; the DB1B
    # placeholder carriers `--` / `99` (Op/TkCarrier) never enter the key,
    # so rows carry no carrier columns at all and still fit.
    rows = [coupon("ATL", "ORD", 7)]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    assert ref.lookup("ATL", "ORD").value == 70.0


def test_dataset_boundary_isolation():
    rows = build_cell("ATL", "ORD", 10)
    rows[0]["dataset_instance_id"] = "data1_2019"
    with pytest.raises(ContractError, match="REFERENCE_DATASET_MISMATCH"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")


def test_missing_route_key_rejected():
    rows = build_cell("ATL", "ORD", 10)
    del rows[0]["join_key"]
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:join_key"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")
    rows = build_cell("ATL", "ORD", 10)
    rows[0]["join_key"] = {"origin": "ATL"}
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:join_key"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")


def test_missing_value_rejected_not_silently_zeroed():
    rows = build_cell("ATL", "ORD", 10)
    rows[0]["value"] = None
    with pytest.raises(ContractError, match="REFERENCE_ROW_MISSING:value"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")


def test_wrong_reference_period_rejected():
    rows = [coupon("ATL", "ORD", 5, period="2018-Q4")]
    with pytest.raises(ContractError, match="REFERENCE_PERIOD_MISMATCH"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")


def test_empty_train_partition_raises():
    rows = [coupon("ATL", "ORD", 5, split="development")]
    with pytest.raises(ContractError, match="REFERENCE_TRAIN_PARTITION_EMPTY"):
        build_data2_passenger_reference(rows, fit_period="2019-Q1")


def test_nontrain_rows_are_excluded_from_fit():
    train = build_cell("ATL", "ORD", 10)
    base = build_data2_passenger_reference(train, fit_period="2019-Q1")
    dev = [coupon("MIA", "LAX", 999, rid="dev1", split="development")]
    with_dev = build_data2_passenger_reference(train + dev, fit_period="2019-Q1")
    assert base == with_dev
    assert with_dev.total_sample_count == 10
    assert with_dev.lookup("MIA", "LAX").support_state is SupportState.ABSTAIN


def test_zero_passenger_rows_are_legitimate_sample_rows():
    rows = [coupon("ATL", "ORD", 0), coupon("ATL", "ORD", 3)]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    result = ref.lookup("ATL", "ORD")
    assert result.value == 30.0
    assert result.support_state is SupportState.SUPPORTED


def test_manifest_freezes_route_table_and_registry_state():
    rows = build_cell("ATL", "ORD", 10) + build_cell("MIA", "LAX", 10, offset=100)
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    assert ref.manifest_freeze_id.startswith("sha256:")
    assert ref.total_sample_count == 20
    assert ref.route_count == 2
    assert ref.minimum_support_rule == "OFFICIAL_QUARTER_SAMPLE_NO_MIN_CELL"
    assert ref.fallback_hierarchy == ()
    assert ref.support_state is SupportState.SUPPORTED
    assert ref.reason_code == "DB1B_COUPON_OFFICIAL_10PCT_X10"
    assert isinstance(ref, Data2PassengerReference)

    registry = current_transformation_registry()
    rule = registry.get("DATA2_PASSENGER_REFERENCE", "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    assert "x10" in rule.formula_or_algorithm
    assert "10PCT" in rule.formula_or_algorithm
    assert rule.evidence_class is EvidenceClass.DOMAIN_PROXY
    assert rule.support_ceiling is EvidenceClass.DOMAIN_PROXY

    bundle = load_registry_bundle(Path("registries"))
    rule_ids = {r.rule_id for r in bundle.data_usage_rules}
    assert "D2-PASSENGER-REFERENCE" in rule_ids
    assert "D1-OPENSKY-FLIGHT" in rule_ids
    d2 = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-PASSENGER-REFERENCE")
    assert d2.freeze_state.value == "FROZEN"
    assert d2.dataset_id == "data2_2019"
    assert d2.logical_source == "bts_db1b"
    assert d2.external_evidence_rule_ids == ("D2-DB1B",)
    db1b = next(r for r in bundle.data_usage_rules if r.rule_id == "D2-DB1B")
    assert db1b.freeze_state.value == "FROZEN"
    assert db1b.transformation_rule == "declared_ten_percent_scaling"
    d1_eurostat = next(r for r in bundle.data_usage_rules if r.rule_id == "D1-EUROSTAT")
    assert d1_eurostat.freeze_state.value == "FROZEN"
    assert d1_eurostat.dataset_id == "data1_2019"


def test_scale_factor_is_frozen_default_and_parameterized():
    rows = build_cell("ATL", "ORD", 10)
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    explicit = build_data2_passenger_reference(rows, fit_period="2019-Q1", scale_factor=10)
    assert ref == explicit
    assert ref.cells[0].value_passengers == explicit.cells[0].value_passengers
