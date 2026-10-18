# -*- coding: utf-8 -*-
"""D2-10 formal temporal split (train/calibration/development/test) tests.

Covers: window boundaries, FROZEN registry state (transformation + data
usage), data2-only scope, and data1 non-regression (no D1 rule touched).
"""
from datetime import date

import pytest

from model.M1.splits import (ALL_SPLITS, CALIBRATION_END, DEVELOPMENT_END,
                             RULE_ID, RULE_VERSION, TRAIN_END, split_for_date)
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.transformation import TransformationStatus, current_transformation_registry
from model.common.errors import ContractError


@pytest.fixture(scope="module")
def data_usage_rules():
    bundle = load_registry_bundle(__import__("pathlib").Path("registries"))
    return bundle.data_usage_rules


def test_boundaries_assign_expected_splits():
    assert split_for_date(date(2019, 6, 30)) == "train"
    assert split_for_date(date(2019, 1, 1)) == "train"
    assert split_for_date(date(2019, 7, 1)) == "calibration"
    assert split_for_date(date(2019, 7, 31)) == "calibration"
    assert split_for_date(date(2019, 8, 1)) == "development"
    assert split_for_date(date(2019, 9, 30)) == "development"
    assert split_for_date(date(2019, 10, 1)) == "test"
    assert split_for_date(date(2019, 12, 31)) == "test"


def test_frozen_constants_match_rule():
    assert TRAIN_END == date(2019, 6, 30)
    assert CALIBRATION_END == date(2019, 7, 31)
    assert DEVELOPMENT_END == date(2019, 9, 30)
    assert ALL_SPLITS == ("train", "calibration", "development", "test")


def test_transformation_rule_is_frozen():
    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    assert rule.status is TransformationStatus.FROZEN
    assert rule.temporal_rule == "TRAIN_PARTITION_ONLY"


def test_data_usage_rule_registered_for_data2_only(data_usage_rules):
    matches = [rule for rule in data_usage_rules if rule.rule_id == "D2-TEMPORAL-SPLIT"]
    assert len(matches) == 1
    rule = matches[0]
    assert rule.rule_version == "1.0.0"
    assert rule.freeze_state.value == "FROZEN"
    assert rule.dataset_id == "data2_2019"
    assert rule.logical_source == "bts_ontime"
    assert rule.canonical_variable == "dataset_partition"
    assert "M1" in rule.downstream_consumers


def test_data1_rules_untouched(data_usage_rules):
    d1 = [rule for rule in data_usage_rules if rule.dataset_id == "data1_2019"]
    assert len(d1) == 7
    assert all(rule.freeze_state.value == "FROZEN" for rule in d1)
    assert all(rule.rule_version == "1.0.0" for rule in d1)
    expected = {"D1-OPENSKY-STATE", "D1-OPENSKY-FLIGHT", "D1-OPENSKY-FLIGHT-EVENT",
                "D1-TRAJECTORY-EVENT", "D1-EUROSTAT", "D1-METAR", "D1-OURAIRPORTS"}
    assert {rule.rule_id for rule in d1} == expected


def test_split_rule_is_not_a_pre_evidence_rule(data_usage_rules):
    rule = next(r for r in data_usage_rules if r.rule_id == "D2-TEMPORAL-SPLIT")
    assert rule.evidence_class.value == "DERIVED"
    assert rule.availability_rule == "posthoc_only"
