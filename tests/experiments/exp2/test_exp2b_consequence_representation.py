"""Contract tests for Exp2B consequence-representation records (r=7/3/1)."""

from __future__ import annotations

import pandas as pd
import pytest

from exp.exp2.exp2b_consequence_representation import (
    CHANNELS,
    RECORDS_SCHEMA,
    SAFETY,
    _baseline_channel_shares,
    _matched_case_rows,
    _scenario_loss,
    _select_top1,
)


def _post(**overrides) -> dict:
    values = {
        "F_continuity": 10.0,
        "F_execution": 20.0,
        "F_propagation": 30.0,
        "P_time": 40.0,
        "P_itinerary": 2.0,
        "P_service": 3.0,
        "R_operating": 50.0,
    }
    values.update(overrides)
    return values


RATES = {
    "F_continuity": 72.0,
    "F_execution": 72.0,
    "F_propagation": 72.0,
    "P_time": 0.30,
    "P_itinerary": None,
    "P_service": None,
    "R_operating": 72.0,
}


def test_r7_scalar_loss_definition() -> None:
    post = _post()
    loss, itin, svc = _scenario_loss(post, RATES, "r7")
    expected = (10.0 + 20.0 + 30.0) * 72.0 + 40.0 * 0.30 + 50.0 * 72.0
    assert loss == pytest.approx(expected)
    assert itin == 2.0 and svc == 3.0  # event counts stay visible


def test_r3_channel_loss_definition() -> None:
    post = _post()
    loss, _, _ = _scenario_loss(post, RATES, "r3")
    expected = (10.0 + 20.0 + 30.0) * 72.0 + 40.0 * 0.30 + 50.0 * 72.0
    assert loss == pytest.approx(expected)


def test_r1_scalar_loss_definition() -> None:
    post = _post()
    loss, _, _ = _scenario_loss(post, RATES, "r1")
    expected = (10.0 + 20.0 + 30.0 + 50.0) * 72.0 + 40.0 * 0.30
    assert loss == pytest.approx(expected)


def test_abstain_components_never_zero_filled() -> None:
    # P_time unsupported -> Passenger channel empty in r3; total excludes it in r1
    post = _post(P_time=None)
    loss_r3, _, _ = _scenario_loss(post, RATES, "r3")
    loss_r1, _, _ = _scenario_loss(post, RATES, "r1")
    expected = (10.0 + 20.0 + 30.0 + 50.0) * 72.0
    assert loss_r3 == pytest.approx(expected)
    assert loss_r1 == pytest.approx(expected)
    # all monetary components unsupported -> None, not zero
    empty = _post(F_continuity=None, F_execution=None, F_propagation=None,
                  P_time=None, R_operating=None)
    assert _scenario_loss(empty, RATES, "r3")[0] is None
    assert _scenario_loss(empty, RATES, "r1")[0] is None
    assert _scenario_loss(empty, RATES, "r7")[0] is None


def test_channel_grouping() -> None:
    assert CHANNELS["Flight"] == ("F_continuity", "F_execution", "F_propagation")
    assert CHANNELS["Passenger"] == ("P_time",)
    assert CHANNELS["Resource"] == ("R_operating",)


def test_top1_deterministic_tie_break() -> None:
    rows = [
        {"action_id": "B11", "residual_risk_objective": 5.0},
        {"action_id": "A00", "residual_risk_objective": 5.0},
        {"action_id": "A21", "residual_risk_objective": 3.0},
    ]
    selected = _select_top1(rows)
    assert selected[0]["action_id"] == "A21"
    # tie between A00 and B11 resolved by action_id order
    rows = [
        {"action_id": "B11", "residual_risk_objective": 5.0},
        {"action_id": "A00", "residual_risk_objective": 5.0},
    ]
    assert _select_top1(rows)[0]["action_id"] == "A00"


def test_top1_abstained_rows_excluded() -> None:
    rows = [
        {"action_id": "A00", "residual_risk_objective": None},
        {"action_id": "A21", "residual_risk_objective": 3.0},
    ]
    selected = _select_top1(rows)
    assert len(selected) == 1 and selected[0]["action_id"] == "A21"


def test_baseline_channel_shares_supported_only() -> None:
    rows = [
        {
            "scenario_weight": 1.0,
            "components_json": (
                '[{"component_id": "F_continuity", "constructed_value_cu": 10.0},'
                '{"component_id": "F_execution", "constructed_value_cu": 20.0},'
                '{"component_id": "F_propagation", "constructed_value_cu": 30.0},'
                '{"component_id": "P_time", "constructed_value_cu": null},'
                '{"component_id": "P_itinerary", "constructed_value_cu": 5.0},'
                '{"component_id": "P_service", "constructed_value_cu": 6.0},'
                '{"component_id": "R_operating", "constructed_value_cu": 50.0}]'
            ),
        }
    ]
    shares = _baseline_channel_shares(rows, RATES)
    flight = (10.0 + 20.0 + 30.0) * 72.0
    resource = 50.0 * 72.0
    total = flight + resource
    assert shares["total"] == pytest.approx(total)
    assert shares["Flight"] == pytest.approx(flight / total)
    assert shares["Passenger"] == 0.0
    assert shares["Resource"] == pytest.approx(resource / total)


def _node_frame_for_matched_case(n_episodes: int = 24) -> pd.DataFrame:
    rows = []
    for episode in range(n_episodes):
        for node in range(4):
            rows.append({
                "episode_id": f"EP{episode:02d}",
                "decision_node_id": f"EP{episode:02d}_N{node}",
                "top1_r7": "A00",
                "top1_r3": "A21" if (episode + node) % 3 == 0 else "A00",
                "top1_r1": "A00",
                "family_r7": "TIMING",
                "family_r3": "PASSENGER",
                "family_r1": "TIMING",
                "baseline_total_constructed_eur": 100.0 + 10.0 * episode,
                "channel_share_flight": 0.60 - 0.05 * (episode % 2),
                "channel_share_passenger": 0.20,
                "channel_share_resource": 0.20 + 0.05 * (episode % 2),
                "exclusion_reason": None,
            })
    return pd.DataFrame(rows)


def _records_frame_for_matched_case(n_episodes: int = 24) -> pd.DataFrame:
    rows = []
    for episode in range(n_episodes):
        for node in range(4):
            j = 500.0 + 50.0 * episode + 5.0 * node
            rows.append({
                "episode_id": f"EP{episode:02d}",
                "decision_node_id": f"EP{episode:02d}_N{node}",
                "representation": "r7",
                "action_id": "A00",
                "residual_risk_objective": j,
                "top1": True,
            })
            rows.append({
                "episode_id": f"EP{episode:02d}",
                "decision_node_id": f"EP{episode:02d}_N{node}",
                "representation": "r7",
                "action_id": "A21",
                "residual_risk_objective": j + 10.0,
                "top1": False,
            })
    return pd.DataFrame(rows)


def test_matched_case_rows_d1a_pairing() -> None:
    rows = _matched_case_rows(_node_frame_for_matched_case(), _records_frame_for_matched_case())
    assert len(rows) > 0
    # both directions are reported per pair
    pair_ids = {row["pair_id"] for row in rows}
    for pair_id in pair_ids:
        directions = {row["direction"] for row in rows if row["pair_id"] == pair_id}
        assert directions == {"A_TO_B", "B_TO_A"}
    # deterministic output
    again = _matched_case_rows(_node_frame_for_matched_case(), _records_frame_for_matched_case())
    assert rows == again


def test_matched_case_rows_composition_flip() -> None:
    rows = _matched_case_rows(_node_frame_for_matched_case(), _records_frame_for_matched_case())
    # even episodes: shares (0.60, 0.20, 0.20) -> ranks F=1, P=2, R=3
    # odd episodes:  shares (0.55, 0.20, 0.25) -> ranks F=1, R=2, P=3
    # a same-band even/odd pair flips P and R -> composition_different=True
    differing = [row for row in rows if row["composition_different"]]
    same = [row for row in rows if not row["composition_different"]]
    assert differing and same
    for row in differing:
        assert set(row["flipped_channels"].split("|")) <= {"Flight", "Passenger", "Resource"}
        assert len(row["flipped_channels"].split("|")) >= 2
    # deterministic tie-break: shares 0.2/0.2 -> fixed channel order
    from exp.exp2.exp2b_consequence_representation import _channel_ranks
    ranks = _channel_ranks({"share_flight": 0.3, "share_passenger": 0.3, "share_resource": 0.4})
    assert ranks["Resource"] == 1
    assert ranks["Flight"] == 2
    assert ranks["Passenger"] == 3


def test_matched_case_rows_excludes_unsupported_nodes() -> None:
    frame = _node_frame_for_matched_case()
    frame.loc[frame["decision_node_id"] == "EP00_N0", "exclusion_reason"] = "EXP2B_NOT_IN_COMMON_SCOPE"
    records = _records_frame_for_matched_case()
    rows = _matched_case_rows(frame, records)
    ep00 = [row for row in rows if row["episode_a"] == "EP00"]
    assert ep00
    assert all(row["n_common_scope_nodes_a"] == 3 for row in ep00)


def test_records_schema_fields() -> None:
    names = {field.name for field in RECORDS_SCHEMA}
    required = {
        "episode_id", "decision_node_id", "representation", "action_id",
        "action_family", "residual_risk_objective", "top1", "rank_position",
        "exclusion_reason",
    }
    assert required <= names


def test_safety_all_zero() -> None:
    assert SAFETY["FINAL_TEST_ACCESS_COUNT"] == 0
    assert SAFETY["EXP2_RUNS"] == 0
    assert SAFETY["PAPER_FULL_RUN"] is False
