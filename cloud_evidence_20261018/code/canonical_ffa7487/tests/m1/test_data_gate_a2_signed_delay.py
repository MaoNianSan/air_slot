from collections import Counter
from pathlib import Path

from model.PRE.adapters.registry import SourceAdapterRegistry
from model.PRE.feature_registry.loader import load_registry_bundle
from model.PRE.streaming.data2 import preparation_state_key
from validation.m1_v2_data_gate_a2 import _hist_median, _reference_payload
from validation.m1_v2_data_gate_a2_source import (
    ConsistencyAccumulator,
    RelationshipAccumulator,
    _gate_status,
)


def test_signed_delay_reporting_relationship_accepts_early_operation():
    accumulator = RelationshipAccumulator()
    accumulator.add(-7.0, 0.0, {"row": 1})
    accumulator.add(12.0, 12.0, {"row": 2})
    accumulator.add(4.0, 7.0, {"row": 3})
    payload = accumulator.payload()

    assert payload["both_available"] == 3
    assert payload["negative_signed_count"] == 1
    assert payload["exact_relation_rate"] == 2 / 3
    assert payload["within_1min_relation_rate"] == 2 / 3
    assert payload["violation_count"] == 1


def test_consistency_gate_uses_strong_then_rounding_thresholds():
    def payload(within_1: float, within_5: float):
        return {
            split: {
                side: {
                    "within_1min_rate": within_1,
                    "within_5min_rate": within_5,
                }
                for side in ("departure", "arrival")
            }
            for split in ("train", "calibration", "development")
        }

    assert _gate_status(payload(0.99, 0.99)) == "PASS_STRONG"
    assert _gate_status(payload(0.96, 0.995)) == "PASS_WITH_SOURCE_ROUNDING"
    assert _gate_status(payload(0.94, 1.0)) == "HUMAN_REVIEW"


def test_empty_consistency_strata_are_explicit_not_division_errors():
    payload = ConsistencyAccumulator().payload()
    assert payload["both_available_count"] == 0
    assert payload["stratification"]["negative_delay"]["count"] == 0
    assert payload["stratification"]["negative_delay"]["within_1min_rate"] is None


def test_a2_semantic_token_invalidates_preparation_state_identity(tmp_path: Path):
    source = tmp_path / "month.csv"
    source.write_text("x\n", encoding="utf-8")
    counts = {"train": 1, "calibration": 0, "development": 0, "test": 0}
    old = preparation_state_key(tmp_path, (source,), counts, 7)
    unchanged = preparation_state_key(tmp_path, (source,), counts, 7)
    corrected = preparation_state_key(
        tmp_path,
        (source,),
        counts,
        7,
        semantic_token="BTS_SIGNED_DELAY_SEMANTIC_CORRECTION",
    )

    assert old == unchanged
    assert corrected != old


def test_registry_declares_signed_and_reporting_delay_roles():
    source = SourceAdapterRegistry.load(
        Path("registries/source_adapter_registry.yaml")
    ).get("data2_2019", "bts_ontime")
    assert {"DepDelay", "ArrDelay", "DepDelayMinutes", "ArrDelayMinutes"} <= set(
        source.projected_columns
    )
    assert source.column_roles == {
        "DepDelay": "SIGNED_TIME_OFFSET",
        "ArrDelay": "SIGNED_TIME_OFFSET",
        "DepDelayMinutes": "NONNEGATIVE_DELAY_REPORTING_ONLY",
        "ArrDelayMinutes": "NONNEGATIVE_DELAY_REPORTING_ONLY",
    }

    rule = next(
        item
        for item in load_registry_bundle(Path("registries")).data_usage_rules
        if item.rule_id == "D2-BTS-ACTUAL"
    )
    assert rule.raw_column_roles == source.column_roles
    assert "signed_delay" in rule.transformation_rule


def test_a2_reference_payload_preserves_medians_and_semantic_identity():
    template = {
        "reference_id": "sha256:old",
        "manifest_freeze_id": "sha256:old-manifest",
        "rule_id": "DATA2_TURNAROUND_REFERENCE",
        "rule_version": "1.0.0",
        "dataset_instance_id": "data2_2019",
        "fit_period": "2019-H1",
        "statistic_id": "MEDIAN",
        "minimum_support_rule": "MIN_CELL_SIZE_50",
        "fallback_hierarchy": ["AIRPORT_CELL", "GLOBAL"],
        "applicability_scope": "AIRPORT_GROUP",
        "global_value_minutes": 0,
        "global_sample_count": 0,
        "cells": [],
        "support_state": "SUPPORTED",
        "reason_code": "DIRECT_GATE_TURNAROUND_REFERENCE",
    }
    global_histogram = Counter({10.0: 50, 20.0: 50})
    airport_histograms = {"JFK": Counter({10.0: 50}), "LAX": Counter({20.0: 2})}
    payload = _reference_payload(
        template=template,
        global_histogram=global_histogram,
        airport_histograms=airport_histograms,
        scope="TEST",
    )

    assert _hist_median(global_histogram) == 15.0
    assert payload["global_value_minutes"] == 15.0
    assert payload["reference_id"] != template["reference_id"]
    assert next(item for item in payload["cells"] if item["airport_id"] == "LAX")[
        "fallback_level"
    ] == "GLOBAL"
