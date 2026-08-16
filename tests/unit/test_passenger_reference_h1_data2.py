# -*- coding: utf-8 -*-
"""D2-10 passenger reference H1 variant (Q1+Q2 coupon files) tests.

Covers: H1 aggregation and x10 scaling, directed route semantics, carrier
columns ignored (placeholder carriers do not matter), registry freeze
(transformation DATA2_PASSENGER_REFERENCE_H1 + data usage
D2-PASSENGER-REFERENCE-H1), dataset isolation, non-train exclusion, and
non-regression of the Q1 default (DATA2_PASSENGER_REFERENCE unchanged).
"""
from pathlib import Path

import pytest

from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.reference.passenger_data2 import (H1_RULE_ID, RULE_ID, RULE_VERSION,
                                                 build_data2_passenger_reference)
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError


def coupon(origin, dest, passengers, *, rid="r1", period="2019", split="train",
           dataset="data2_2019", carrier="--"):
    # Carrier columns are intentionally present in the raw-shaped dict; the
    # builder must never read them (DB1B placeholder carriers `--` / `99`).
    return {
        "dataset_instance_id": dataset,
        "canonical_record_id": rid,
        "join_key": {"origin": origin, "destination": dest},
        "reference_period": period,
        "value": passengers,
        "split": split,
        "OpCarrier": carrier,
        "TkCarrier": carrier,
    }


@pytest.fixture(scope="module")
def data_usage_rules():
    return load_registry_bundle(Path("registries")).data_usage_rules


def test_h1_fit_aggregates_q1_and_q2_files_with_x10():
    q1_rows = [coupon("ATL", "ORD", 2, rid="a1"), coupon("ATL", "ORD", 4, rid="a2")]
    q2_rows = [coupon("ATL", "ORD", 1, rid="a3"), coupon("ATL", "ORD", 6, rid="a4")]
    ref = build_data2_passenger_reference(q1_rows + q2_rows, fit_period="2019-H1",
                                          rule_id=H1_RULE_ID)
    assert ref.rule_id == H1_RULE_ID and ref.rule_version == "1.0.0"
    assert ref.fit_period == "2019-H1"
    assert ref.scale_factor == 10
    assert ref.total_passengers == (2 + 4 + 1 + 6) * 10
    assert ref.total_sample_count == 4
    assert ref.route_count == 1
    cell = ref.cells[0]
    assert cell.value_passengers == 130.0 and cell.sample_count == 4


def test_h1_route_grain_is_directed_and_carrier_ignored():
    rows = [
        coupon("ATL", "ORD", 5, carrier="--"),
        coupon("ORD", "ATL", 3, carrier="99"),
        coupon("ATL", "ORD", 7, carrier="WN"),
    ]
    ref = build_data2_passenger_reference(rows, fit_period="2019-H1", rule_id=H1_RULE_ID)
    assert ref.route_count == 2
    assert ref.lookup("ATL", "ORD").value == (5 + 7) * 10
    assert ref.lookup("ORD", "ATL").value == 30.0


def test_h1_lookup_flags_and_reason():
    ref = build_data2_passenger_reference([coupon("ATL", "ORD", 9)], fit_period="2019-H1",
                                          rule_id=H1_RULE_ID)
    result = ref.lookup("ATL", "ORD")
    assert result.value == 90.0
    assert result.support_state is SupportState.SUPPORTED
    assert result.reason_code == "DB1B_COUPON_OFFICIAL_10PCT_X10;ROUTE_H1_SUM"
    assert "REFERENCE_SOURCE_DB1B_COUPON_H1" in result.quality_flags
    missing = ref.lookup("MIA", "LAX")
    assert missing.support_state is SupportState.ABSTAIN
    assert "REFERENCE_SOURCE_DB1B_COUPON_H1" in missing.quality_flags


def test_transformation_rule_is_frozen():
    rule = current_transformation_registry().get(H1_RULE_ID, "1.0.0")
    assert rule.status is TransformationStatus.FROZEN
    assert rule.evidence_class is EvidenceClass.DOMAIN_PROXY
    assert rule.support_ceiling is EvidenceClass.DOMAIN_PROXY


def test_data_usage_rule_registered(data_usage_rules):
    matches = [rule for rule in data_usage_rules if rule.rule_id == "D2-PASSENGER-REFERENCE-H1"]
    assert len(matches) == 1
    rule = matches[0]
    assert rule.rule_version == "1.0.0"
    assert rule.freeze_state.value == "FROZEN"
    assert rule.dataset_id == "data2_2019"
    assert rule.canonical_variable == "passenger_reference"
    assert rule.external_evidence_rule_ids == ("D2-DB1B",)


def test_dataset_isolation_rejects_data1_rows():
    rows = [coupon("ATL", "ORD", 5, dataset="data1_2019")]
    with pytest.raises(ContractError) as exc:
        build_data2_passenger_reference(rows, fit_period="2019-H1", rule_id=H1_RULE_ID)
    assert "REFERENCE_DATASET_MISMATCH" in str(exc.value)


def test_non_train_rows_excluded_from_h1_fit():
    rows = [coupon("ATL", "ORD", 5, split="train"),
            coupon("ATL", "ORD", 100, split="test")]
    ref = build_data2_passenger_reference(rows, fit_period="2019-H1", rule_id=H1_RULE_ID)
    assert ref.total_passengers == 50.0 and ref.total_sample_count == 1


def test_q1_default_unchanged():
    rows = [coupon("ATL", "ORD", 9)]
    ref = build_data2_passenger_reference(rows, fit_period="2019-Q1")
    assert ref.rule_id == RULE_ID and ref.rule_version == RULE_VERSION
    assert ref.fit_period == "2019-Q1"
    result = ref.lookup("ATL", "ORD")
    assert result.reason_code == "DB1B_COUPON_OFFICIAL_10PCT_X10;ROUTE_QUARTER_SUM"
    assert "REFERENCE_SOURCE_DB1B_COUPON_Q1" in result.quality_flags
