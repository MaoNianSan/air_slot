"""Freeze F1/F2 contract tests (2026-08-25): manuscript primitive coordinates.

F1: POINT medoid distance uses only (R_IB, D_OB, D_TX); D_TO is an identity
check and never enters the distance.  MARGINAL permutes the three primitives
independently and recomputes D_TO samplewise.  F2: no partial-q entry point.
All tests are CONTRACT_FAST; no artifacts are read.
"""

import inspect

import pytest

from exp.exp2.representation import (
    PRIMITIVE_FIELDS,
    ScenarioRepresentationAdapter,
)
from exp.exp2.variants import EXP2A_VARIANTS


def _adapter(rows):
    return ScenarioRepresentationAdapter(rows, artifact_version="M1_FIXTURE")


def test_f1_medoid_distance_uses_primitives_only():
    # s0 wins on the primitive triple; if D_TO were part of the distance,
    # s1 (whose derived D_TO is closest to the others) would win instead.
    rows = (
        {"scenario_id": 0, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 0.0, "D_TX": 0.0, "D_TO": 0.0, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 1 / 3, "T_IB_A00": 10.0, "D_OB": 1.0, "D_TX": 1.0, "D_TO": 2.0, "lineage": ("b",)},
        {"scenario_id": 2, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 10.0, "D_TX": 10.0, "D_TO": 20.0, "lineage": ("c",)},
    )
    point = _adapter(rows).transform("EXP2A_POINT")
    assert point.samples[0].scenario_id == "POINT:0"
    assert point.transform_metadata["medoid_coordinates"] == list(PRIMITIVE_FIELDS)
    assert point.transform_metadata["D_TO_ROLE"] == "IDENTITY_VALIDATION_ONLY"


def test_f1_d_to_identity_violation_rejected_before_distance():
    rows = (
        {"scenario_id": 0, "scenario_weight": 1.0, "T_IB_A00": 1.0, "D_OB": 3.0, "D_TX": 4.0, "D_TO": 99.0, "lineage": ("a",)},
    )
    with pytest.raises(ValueError, match="EXP2_SOURCE_D_TO_IDENTITY_VIOLATION"):
        _adapter(rows)


def test_f1_marginal_permutes_three_primitives_and_recomputes_d_to():
    rows = (
        {"scenario_id": 0, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 0.0, "D_TX": 0.0, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 1 / 3, "T_IB_A00": 1.0, "D_OB": 1.0, "D_TX": 1.0, "lineage": ("b",)},
        {"scenario_id": 2, "scenario_weight": 1 / 3, "T_IB_A00": 2.0, "D_OB": 2.0, "D_TX": 2.0, "lineage": ("c",)},
    )
    marginal = _adapter(rows).transform("EXP2A_MARGINAL")
    samples = marginal.samples
    # D_OB shift 0, D_TX shift 1, R_IB shift 2 within the weight stratum.
    assert [(item.R_IB, item.D_OB, item.D_TX) for item in samples] == [
        (2.0, 0.0, 1.0),
        (0.0, 1.0, 2.0),
        (1.0, 2.0, 0.0),
    ]
    assert [item.D_TO for item in samples] == [1.0, 3.0, 2.0]
    assert all(
        item.field_source_scenario_ids["D_TO"] == "DERIVED_FROM_D_OB_PLUS_D_TX"
        for item in samples
    )
    assert samples[0].field_source_scenario_ids["D_TX"] == 1
    assert marginal.transform_metadata["field_source_scenario_ids"]["R_IB"][0] == 2
    assert set(marginal.transform_metadata["field_source_scenario_ids"]) == set(PRIMITIVE_FIELDS)


def test_f1_marginal_preserves_each_primitive_distribution():
    rows = (
        {"scenario_id": 0, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 0.0, "D_TX": 0.0, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 1 / 3, "T_IB_A00": 1.0, "D_OB": 1.0, "D_TX": 1.0, "lineage": ("b",)},
        {"scenario_id": 2, "scenario_weight": 1 / 3, "T_IB_A00": 2.0, "D_OB": 2.0, "D_TX": 2.0, "lineage": ("c",)},
    )
    adapter = _adapter(rows)
    joint = adapter.transform("EXP2A_JOINT")
    marginal = adapter.transform("EXP2A_MARGINAL")
    for field in PRIMITIVE_FIELDS:
        assert sorted((getattr(item, field), item.scenario_weight) for item in joint.samples) == sorted(
            (getattr(item, field), item.scenario_weight) for item in marginal.samples
        )


def test_f2_no_partial_q_entry_point():
    signature = inspect.signature(ScenarioRepresentationAdapter.transform)
    assert set(signature.parameters) == {"self", "variant_id"}
    assert EXP2A_VARIANTS == ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT")


def test_f1_medoid_requires_complete_primitive_coordinates():
    # An OVERFLOW-like candidate (missing D_OB/D_TX) must never win the
    # medoid: its distance is only defined on complete candidates.
    rows = (
        {"scenario_id": 0, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": None, "D_TX": None, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 1.0, "D_TX": 1.0, "lineage": ("b",)},
        {"scenario_id": 2, "scenario_weight": 1 / 3, "T_IB_A00": 0.0, "D_OB": 3.0, "D_TX": 3.0, "lineage": ("c",)},
    )
    point = _adapter(rows).transform("EXP2A_POINT")
    assert point.samples[0].scenario_id != "POINT:0"
    assert point.samples[0].D_OB is not None and point.samples[0].D_TX is not None
    assert point.samples[0].D_TO == point.samples[0].D_OB + point.samples[0].D_TX
