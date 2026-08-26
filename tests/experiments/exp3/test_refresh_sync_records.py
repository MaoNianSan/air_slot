"""Exp3 refresh/sync materialization contract tests (V3 T3, 2026-08-26).

Fast synthetic tests only: no parquet reads, no model inference.  Covers the
F3 frozen semantics: exact-vintage bindings without fallback, One-Shot/Rolling
anchors (eq:exp_anchor), deterministic Top-1 (min J, tie-break action_id,
A00 in the comparison set), executability typed from eligibility + J
availability, and eq:exp_post_replay restricted to a common J basis.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from exp.common.context import ExecutionTier, ExperimentContext
from exp.common.context import real_fast_context
from exp.exp3.refresh_sync_records import (
    BOOTSTRAP_SEED,
    build_refresh_node_records,
    build_state_sync_records,
    episode_refresh_values,
    episode_state_sync_values,
    find_anchor_node,
    select_top1_action,
    summary_from_values,
)
from exp.exp3.vintage import exact_vintage_bindings


def _action(identifier: str, j: float | None, eligible: str = "TRUE") -> dict:
    return {
        "action_id": identifier,
        "residual_risk": j,
        "eligibility_state": eligible,
        "response_support": "SCENARIO_ASSUMPTION" if identifier != "A00" else "IDENTITY",
        "diagnostic_support_status": "PARTIAL_DIAGNOSTIC",
    }


def _records_frame(nodes: list[dict]) -> pd.DataFrame:
    rows = []
    for node in nodes:
        for action in node["actions"]:
            rows.append(
                {
                    "episode_id": node["episode_id"],
                    "decision_node_id": node["decision_node_id"],
                    "decision_time": node["decision_time"],
                    "action_id": action["action_id"],
                    "response_sensitivity": "BASE",
                    "eligibility_state": action["eligibility_state"],
                    "response_support": action["response_support"],
                    "diagnostic_support_status": action["diagnostic_support_status"],
                    "conditional_residual_risk": action["residual_risk"],
                    "conditional_diagnostic_rank": None,
                }
            )
    return pd.DataFrame(rows)


def _node_frame(nodes: list[dict]) -> dict:
    out = {}
    for node in nodes:
        out[node["decision_node_id"]] = {
            action["action_id"]: dict(action) for action in node["actions"]
        }
    return out


def _synthetic_episode_nodes() -> list[dict]:
    return [
        {
            "episode_id": "ep1",
            "decision_node_id": "n1",
            "decision_time": "2019-08-16T10:00:00Z",
            "actions": [
                _action("A00", 40.0),
                _action("B01", 30.0),
                _action("C02", 25.0),
            ],
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "n2",
            "decision_time": "2019-08-16T10:05:00Z",
            "actions": [
                _action("A00", 41.0),
                _action("B01", 35.0),
                _action("C02", None),
            ],
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "n3",
            "decision_time": "2019-08-16T10:10:00Z",
            "actions": [
                _action("A00", None),
                _action("B01", 28.0),
                _action("C02", 20.0),
            ],
        },
    ]


def test_top1_min_j_with_deterministic_tie_break():
    rows = [
        _action("A00", 40.0),
        _action("B01", 30.0),
        _action("C02", 30.0),
        _action("D03", None),
    ]
    assert select_top1_action(rows) == "B01"
    tie = [_action("A00", 40.0), _action("Z99", 25.0), _action("A01", 25.0)]
    assert select_top1_action(tie) == "A01"


def test_anchor_rule_requires_two_comparable_and_one_non_a00():
    nodes = _synthetic_episode_nodes()
    anchor_nodes = [
        {"decision_node_id": n["decision_node_id"], "action_rows": n["actions"]}
        for n in nodes
    ]
    assert find_anchor_node(anchor_nodes) == "n1"
    only_a00 = [
        {
            "decision_node_id": "x1",
            "action_rows": [_action("A00", 40.0)],
        },
        {
            "decision_node_id": "x2",
            "action_rows": [_action("A00", 41.0), _action("B01", 30.0)],
        },
    ]
    assert find_anchor_node(only_a00) == "x2"
    one_ranked = [
        {
            "decision_node_id": "y1",
            "action_rows": [_action("A00", None), _action("B01", 30.0)],
        },
        {
            "decision_node_id": "y2",
            "action_rows": [_action("A00", 41.0), _action("B01", 30.0), _action("C02", 25.0)],
        },
    ]
    assert find_anchor_node(one_ranked) == "y2"
    one_ranked = [
        {
            "decision_node_id": "y1",
            "action_rows": [_action("A00", None), _action("B01", 30.0)],
        },
        {
            "decision_node_id": "y2",
            "action_rows": [_action("A00", 41.0), _action("B01", 30.0), _action("C02", 25.0)],
        },
    ]
    assert find_anchor_node(one_ranked) == "y2"


def test_refresh_records_one_shot_holds_anchor_rolling_refreshes():
    nodes = _synthetic_episode_nodes()
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    refresh = build_refresh_node_records(frame, node_frame)
    assert len(refresh) == 3
    by_node = refresh.set_index("decision_node_id")
    assert bool(by_node.loc["n1", "is_anchor_node"]) is True
    assert by_node.loc["n1", "one_shot_action_id"] == "C02"
    # Rolling refreshes to the current node Top-1 while One-Shot holds C02.
    assert by_node.loc["n2", "one_shot_action_id"] == "C02"
    assert by_node.loc["n2", "rolling_action_id"] == "B01"
    assert bool(by_node.loc["n2", "selected_action_difference"]) is True
    # C02 has no J at n2 -> not executable, no common post-replay basis.
    assert bool(by_node.loc["n2", "one_shot_action_j_available"]) is False
    assert bool(by_node.loc["n2", "one_shot_executable"]) is False
    assert bool(by_node.loc["n2", "post_replay_comparable"]) is False
    # At n3 C02 is available again -> executable, common basis, identical action.
    assert bool(by_node.loc["n3", "one_shot_executable"]) is True
    assert by_node.loc["n3", "rolling_action_id"] == "C02"
    assert bool(by_node.loc["n3", "selected_action_difference"]) is False
    assert bool(by_node.loc["n3", "post_replay_comparable"]) is True
    assert by_node.loc["n3", "post_replay_residual_risk_difference"] == pytest.approx(0.0)


def test_refresh_executable_requires_j_availability_and_eligibility():
    nodes = [
        {
            "episode_id": "ep1",
            "decision_node_id": "n1",
            "decision_time": "2019-08-16T10:00:00Z",
            "actions": [_action("A00", 40.0), _action("B01", 30.0)],
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "n2",
            "decision_time": "2019-08-16T10:05:00Z",
            "actions": [_action("A00", 41.0), _action("B01", None)],
        },
    ]
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    refresh = build_refresh_node_records(frame, node_frame)
    row = refresh.set_index("decision_node_id").loc["n2"]
    assert row["one_shot_action_id"] == "B01"
    assert bool(row["one_shot_action_j_available"]) is False
    assert bool(row["one_shot_executable"]) is False
    assert bool(row["selected_action_difference"]) is True  # B01 (held) vs A00 (refreshed)
    assert bool(row["post_replay_comparable"]) is False


def test_episode_values_and_bootstrap_summary_deterministic():
    nodes = _synthetic_episode_nodes()
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    refresh = build_refresh_node_records(frame, node_frame)
    values = episode_refresh_values(refresh)
    assert set(values["comparison"]) >= {"ONE_SHOT_EXECUTABLE", "ROLLING_COMPARABLE"}
    first = summary_from_values(values)
    second = summary_from_values(values)
    assert first.equals(second)
    assert first["episodes"].iloc[0] == 1


def test_state_sync_delta0_self_and_lag_exclusion_typed():
    nodes = _synthetic_episode_nodes()
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    state = build_state_sync_records(frame, node_frame, {})
    delta0 = state.loc[state["delta_minutes"] == 0]
    assert bool(delta0["exact_vintage_match"].all())
    assert bool((delta0["state_vintage_node_id"] == delta0["decision_node_id"]).all())
    lagged = state.loc[state["delta_minutes"] == 5]
    assert bool((lagged["exclusion_code"] == "EXP3B_VINTAGE_NOT_AVAILABLE").all())
    assert lagged["selected_action_difference_vs_sync"].isna().all()


def test_state_sync_with_exact_vintage_binding():
    nodes = _synthetic_episode_nodes()
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    vintage = [
        {
            "episode_id": "ep1",
            "decision_node_id": "n2",
            "exact_vintage_match": True,
            "state_vintage_node_id": "n1",
            "state_vintage_time": "2019-08-16T10:00:00Z",
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "n3",
            "exact_vintage_match": False,
            "state_vintage_node_id": None,
            "state_vintage_time": None,
        },
    ]
    state = build_state_sync_records(frame, node_frame, {5: vintage})
    row = state.loc[
        (state["decision_node_id"] == "n2") & (state["delta_minutes"] == 5)
    ].iloc[0]
    assert row["state_vintage_node_id"] == "n1"
    assert row["vintage_top1_action_id"] == "C02"
    assert row["current_top1_action_id"] == "B01"
    assert bool(row["selected_action_difference_vs_sync"]) is True
    # C02 has no J at n2 -> no common ex-post basis at the current node.
    assert bool(row["post_replay_comparable"]) is False
    excluded = state.loc[
        (state["decision_node_id"] == "n3") & (state["delta_minutes"] == 5)
    ].iloc[0]
    assert excluded["exclusion_code"] == "EXP3B_VINTAGE_NOT_AVAILABLE"
    assert excluded["vintage_top1_action_id"] is None


def test_exact_vintage_bindings_full_semantics_no_fallback():
    context = real_fast_context()
    bound = exact_vintage_bindings(context, lag_minutes=5)
    assert bound
    assert any(item["exact_vintage_match"] is False for item in bound)
    for item in bound:
        assert item["current_state_read"] is False
        if not item["exact_vintage_match"]:
            assert item["state_vintage_node_id"] is None
            assert item["state_vintage_time"] is None


def test_state_sync_episode_values_coverage_from_vintage():
    nodes = _synthetic_episode_nodes()
    frame = _records_frame(nodes)
    node_frame = _node_frame(nodes)
    vintage = [
        {
            "episode_id": "ep1",
            "decision_node_id": "n2",
            "exact_vintage_match": True,
            "state_vintage_node_id": "n1",
            "state_vintage_time": "2019-08-16T10:00:00Z",
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "n3",
            "exact_vintage_match": False,
            "state_vintage_node_id": None,
            "state_vintage_time": None,
        },
    ]
    state = build_state_sync_records(frame, node_frame, {5: vintage})
    values = episode_state_sync_values(state)
    row = values.loc[values["comparison"] == "STATE_SYNC_5"].iloc[0]
    assert row["coverage"] == pytest.approx(1 / 3)


def test_context_safety_boundaries_are_enforced():
    with pytest.raises(ValueError):
        ExperimentContext(
            dataset_id="DATA2",
            split="DEVELOPMENT",
            execution_tier=ExecutionTier.REAL_DATA_FAST,
            seed=0,
            config_hash="sha256:" + "0" * 64,
            scenario_hash="sha256:" + "0" * 64,
            final_test_access_count=1,
        )
    assert BOOTSTRAP_SEED == 20260825
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    assert rng.integers(0, 10, size=3).tolist() == [9, 7, 3]


