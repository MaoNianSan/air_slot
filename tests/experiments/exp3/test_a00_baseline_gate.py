"""Tests for the fail-closed A00 baseline gate."""

from __future__ import annotations

import math

import pandas as pd

from exp.exp3.a00_baseline_gate import evaluate_records, summary


def _row(
    action_id: str,
    objective: float | None,
    *,
    eligibility: str = "UNKNOWN",
    support: str = "SCENARIO_ASSUMPTION",
    node: str = "n1",
    band: str = "BASE",
) -> dict:
    return {
        "decision_node_id": node,
        "response_sensitivity": band,
        "action_id": action_id,
        "eligibility_state": eligibility,
        "response_support": support,
        "conditional_residual_risk": objective,
    }


def test_unknown_non_a00_never_becomes_a00_recommendation() -> None:
    records = pd.DataFrame([
        _row("A00", 10.0, eligibility="TRUE", support="IDENTITY"),
        _row("A21", 1.0),
    ])
    result = evaluate_records(records)
    row = result.iloc[0]
    assert row["conditional_diagnostic_top1_action_id"] == "A21"
    assert row["recommendation_status"] == "ABSTAIN_NO_FACTUALLY_ELIGIBLE_NON_A00"
    assert pd.isna(row["recommended_action_id"])
    assert row["a00_baseline_action_id"] == "A00"
    assert row["response_sensitivity"] == "BASE"
    assert summary(result)["a00_recommendation_count"] == 0


def test_true_but_scenario_only_non_a00_is_abstained() -> None:
    records = pd.DataFrame([
        _row("A00", 10.0, eligibility="TRUE", support="IDENTITY"),
        _row("A21", 1.0, eligibility="TRUE", support="SCENARIO_ASSUMPTION"),
    ])
    row = evaluate_records(records).iloc[0]
    assert row["recommendation_status"] == "ABSTAIN_NO_FACTUALLY_SUPPORTED_NON_A00"
    assert pd.isna(row["recommended_action_id"])


def test_supported_true_non_a00_can_be_recommended_without_a00() -> None:
    records = pd.DataFrame([
        _row("A00", 1.0, eligibility="TRUE", support="IDENTITY"),
        _row("A21", 3.0, eligibility="TRUE", support="SUPPORTED"),
        _row("A23", 2.0, eligibility="TRUE", support="SUPPORTED"),
    ])
    row = evaluate_records(records).iloc[0]
    assert row["conditional_diagnostic_top1_action_id"] == "A00"
    assert row["recommendation_status"] == "RECOMMEND_NON_A00"
    assert row["recommended_action_id"] == "A23"
    assert row["operational_non_a00_candidate_count"] == 2


def test_nonfinite_supported_non_a00_is_fail_closed() -> None:
    records = pd.DataFrame([
        _row("A00", 1.0, eligibility="TRUE", support="IDENTITY"),
        _row("A21", math.inf, eligibility="TRUE", support="SUPPORTED"),
        _row("A23", -math.inf, eligibility="TRUE", support="SUPPORTED"),
    ])
    row = evaluate_records(records).iloc[0]
    assert row["conditional_diagnostic_top1_action_id"] == "A00"
    assert row["recommendation_status"] == "ABSTAIN_NO_FINITE_SUPPORTED_NON_A00"
    assert row["operational_non_a00_candidate_count"] == 0
    assert pd.isna(row["recommended_action_id"])
