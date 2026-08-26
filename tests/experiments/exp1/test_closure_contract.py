"""CONTRACT_FAST tests for the Exp1 Development closure (2026-08-25 supplement).

Covers the frozen-input contracts of ``exp.exp1.closure`` with synthetic rows:
REDUCED context filtering, consequence invariants, S_i support fractions and
typed exclusions, ranking-stat determinism, lead-time rules, weighted-median
points, and CRPS-supported flags.  No Final Test access; no model training.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exp.exp1.closure import (
    M4_GATE_REASON,
    _channels_equal,
    _episode_mean_bootstrap,
    _lead_time_for,
    _pre_facts,
    _ranking_stats,
    _structural_fact_set,
    build_exp1a_records,
    build_exp1b_records,
    build_sorting_diagnostic,
)
from model.M3.registry import ActionRegistry
from model.M3.response_registry import load_response_registry

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ActionRegistry.load(ROOT / "registries/action_templates.yaml")
RESPONSE_REGISTRY = load_response_registry(
    ROOT / "registries/m3_response_scenarios.yaml",
    structural_path=ROOT / "registries/action_templates.yaml",
)

SCENARIO_WEIGHT = 1.0 / 250.0


def _pre_state(episode_id: str, node_id: str) -> dict:
    weather = {
        "support_state": "SUPPORTED",
        "value": {"ceiling_base_m": 1000.0},
    }
    return {
        "decision_node": {
            "episode_id": episode_id,
            "decision_node_id": node_id,
            "decision_time": "2019-08-16T20:24:00Z",
            "information_cutoff": "2019-08-16T20:24:00Z",
        },
        "predecessor_state": {},
        "current_state": {"current_weather": weather},
        "successor_state": {
            "schedule_reference": {
                "support_state": "SUPPORTED",
                "value": {"scheduled_departure_utc": "2019-08-16T21:10:00Z"},
            }
        },
        "reference_state": {},
    }


def _m2_row(episode_id: str, node_id: str, scenario_id: int, status: str) -> dict:
    return {
        "episode_id": episode_id,
        "decision_node_id": node_id,
        "scenario_id": scenario_id,
        "scenario_weight": SCENARIO_WEIGHT,
        "formal_five_component_status": status,
        "formal_five_component_value_cu": 1.0 if status == "FORMAL_AVAILABLE" else None,
        "channels_json": (
            '[]'
            if status != "FORMAL_AVAILABLE"
            else (
                '[{"channel_id": "Flight", "component_ids": ["F_continuity", '
                '"F_execution", "F_propagation"], "support_state": "SUPPORTED", '
                '"value_cu": 0.5}, {"channel_id": "Resource", "component_ids": '
                '["R_operating"], "support_state": "SUPPORTED", "value_cu": 0.2}]'
            )
        ),
        "components_json": (
            '[]'
            if status != "FORMAL_AVAILABLE"
            else (
                '[{"component_id": "P_time", "support_state": "SUPPORTED", '
                '"constructed_value_cu": 0.25, "native_quantity": 10.0, '
                '"native_unit": "passenger_minutes", "monetary_status": null}, '
                '{"component_id": "P_itinerary", "support_state": "SUPPORTED", '
                '"constructed_value_cu": 0.0, "native_quantity": 1.0, '
                '"native_unit": "events", "monetary_status": "NOT_ANCHORED"}]'
            )
        ),
    }


def test_structural_fact_set_blocks_weather_and_history():
    structural = _structural_fact_set(REGISTRY)
    assert "current_weather" not in structural
    assert "upstream_hidden_history" not in structural
    assert "successor_schedule" in structural


def test_reduced_facts_keep_only_structural_names():
    pre = _pre_state("ep1", "node1")
    facts_full, _ = _pre_facts(pre)
    assert "current_weather" in facts_full
    structural = _structural_fact_set(REGISTRY)
    facts_reduced = {
        name: value for name, value in facts_full.items() if name in structural
    }
    assert "current_weather" not in facts_reduced
    assert set(facts_reduced) <= structural


def test_exp1a_records_m4_gate_fields_and_invariants():
    pre_states = [_pre_state("ep1", "node1")]
    consequence_rows = [
        _m2_row("ep1", "node1", scenario_id, "FORMAL_AVAILABLE")
        for scenario_id in range(250)
    ]
    records, meta = build_exp1a_records(
        consequence_rows=consequence_rows,
        pre_states=pre_states,
        registry=REGISTRY,
        response_registry=RESPONSE_REGISTRY,
    )
    assert len(records) == 2
    assert {record["variant"] for record in records} == {
        "EXP1A_FULL", "EXP1A_REDUCED",
    }
    for record in records:
        assert record["comparison_available"] is False
        assert record["comparison_reason"] == M4_GATE_REASON
        assert record["n_comparable_actions"] == 0
        assert record["top1_action"] is None
        assert record["ranking_available"] is False
        assert record["consequence_available"] is True
        assert record["F_consequence"] == pytest.approx(0.5)
        assert record["P_consequence"] == pytest.approx(0.25)
        assert record["R_consequence"] == pytest.approx(0.2)
        assert record["P_itinerary_events"] == pytest.approx(1.0)
    assert meta["m4_gate_reason"] == M4_GATE_REASON
    assert all(
        record["consequence_invariant_to_reduced_context"] for record in records
    )
    assert all(
        record["action_instantiation_invariant_to_reduced_context"]
        for record in records
    )


def test_consequence_unavailable_when_no_formal_rows():
    consequence_rows = [
        _m2_row("ep1", "node1", scenario_id, "FORMAL_AGGREGATE_UNRESOLVED")
        for scenario_id in range(250)
    ]
    records, _ = build_exp1a_records(
        consequence_rows=consequence_rows,
        pre_states=[_pre_state("ep1", "node1")],
        registry=REGISTRY,
        response_registry=RESPONSE_REGISTRY,
    )
    assert all(record["consequence_available"] is False for record in records)
    assert all(record["F_consequence"] is None for record in records)


def _scenario_row(
    episode_id: str, node_id: str, scenario_id: int, d_to: float | None,
) -> dict:
    return {
        "episode_id": episode_id,
        "decision_node_id": node_id,
        "scenario_id": scenario_id,
        "scenario_weight": SCENARIO_WEIGHT,
        "operational_stage": "POST_IB_PRE_OB",
        "decision_time_utc": "2019-08-16T20:24:00+00:00",
        "T_IB_A00": 5.0,
        "D_OB": 5.0,
        "D_TX": 5.0,
        "D_TO": d_to,
    }


def test_sorting_diagnostic_support_fractions_and_typed_exclusions():
    scenario_rows: list[dict] = []
    consequence_rows: list[dict] = []
    # node1: fully supported -> main.
    for scenario_id in range(250):
        scenario_rows.append(_scenario_row("ep1", "node1", scenario_id, 10.0))
        consequence_rows.append(
            _m2_row("ep1", "node1", scenario_id, "FORMAL_AVAILABLE")
        )
    # node2: 200/250 supported -> sensitivity only.
    for scenario_id in range(250):
        d_to = 20.0 if scenario_id < 200 else None
        status = (
            "FORMAL_AVAILABLE"
            if scenario_id < 200
            else "FORMAL_AGGREGATE_UNRESOLVED"
        )
        scenario_rows.append(_scenario_row("ep1", "node2", scenario_id, d_to))
        consequence_rows.append(_m2_row("ep1", "node2", scenario_id, status))
    # node3: finite D_TO but no FORMAL_AVAILABLE -> M2 exclusion.
    for scenario_id in range(250):
        scenario_rows.append(_scenario_row("ep1", "node3", scenario_id, 30.0))
        consequence_rows.append(
            _m2_row("ep1", "node3", scenario_id, "FORMAL_AGGREGATE_UNRESOLVED")
        )
    # node4: no finite D_TO -> M1 exclusion.
    for scenario_id in range(250):
        scenario_rows.append(_scenario_row("ep1", "node4", scenario_id, None))
        consequence_rows.append(
            _m2_row("ep1", "node4", scenario_id, "FORMAL_AVAILABLE")
        )

    node_rows, stats = build_sorting_diagnostic(
        scenario_rows=scenario_rows,
        consequence_rows=consequence_rows,
        replicates=50,
        seed=20260825,
    )
    by_node = {row["decision_node_id"]: row for row in node_rows}
    assert by_node["node1"]["support_fraction"] == 1.0
    assert by_node["node1"]["included_main"] is True
    assert by_node["node1"]["q_state"] == pytest.approx(10.0)
    assert by_node["node1"]["q_ctx"] == pytest.approx(1.0)
    assert by_node["node2"]["support_fraction"] == 0.8
    assert by_node["node2"]["included_main"] is False
    assert by_node["node2"]["included_sensitivity"] is True
    assert by_node["node2"]["exclusion_reason"] == "EXCLUDED_SUPPORT_BELOW_THRESHOLD"
    assert by_node["node2"]["q_state"] == pytest.approx(20.0)
    assert by_node["node3"]["exclusion_reason"] == "EXCLUDED_M2_NOT_AVAILABLE"
    assert by_node["node4"]["exclusion_reason"] == "EXCLUDED_M1_NONFINITE"
    assert stats["included_main_nodes"] == 1
    assert stats["included_sensitivity_nodes"] == 2
    assert stats["excluded_by_reason"] == {
        "EXCLUDED_M1_NONFINITE": 1,
        "EXCLUDED_M2_NOT_AVAILABLE": 1,
        "EXCLUDED_SUPPORT_BELOW_THRESHOLD": 1,
    }


def test_ranking_stats_deterministic_and_formulas():
    rows = [
        {
            "episode_id": "ep1",
            "decision_node_id": f"node{index}",
            "q_state": float(index + 1),
            "q_ctx": float(10 - index),
        }
        for index in range(10)
    ]
    first = _ranking_stats(
        rows, include_bootstrap=True, replicates=100, seed=20260825,
    )
    second = _ranking_stats(
        rows, include_bootstrap=True, replicates=100, seed=20260825,
    )
    assert first == second
    assert first["spearman_rho"] == pytest.approx(-1.0)
    assert first["kendall_tau"] == pytest.approx(-1.0)
    assert first["top10_overlap_rate"] == 0.0
    assert first["top20_overlap_rate"] == 0.0
    assert first["decile_divergence_rate"] == pytest.approx(0.8)
    assert first["spearman_rho_bootstrap"]["estimate"] == pytest.approx(-1.0)
    assert first["spearman_rho_bootstrap"]["replicates_run"] == 100


def test_lead_time_rules():
    pre = _pre_state("ep1", "node1")
    decision_time = "2019-08-16T20:24:00Z"
    lead, source = _lead_time_for("T_IB_A00", 7.5, pre, decision_time)
    assert lead == 7.5
    assert source == "REALIZED_REMAINING_MINUTES"
    lead, source = _lead_time_for("D_OB", None, pre, decision_time)
    assert lead == 46.0
    assert source == "PLANNED_SCHEDULE_HORIZON"
    lead, source = _lead_time_for("D_TX", 1.0, pre, decision_time)
    assert lead is None
    assert source == "NA_NO_PLANNED_WHEELS_OFF"
    lead, source = _lead_time_for("T_IB_A00", None, pre, decision_time)
    assert lead is None
    assert source == "NA_NO_OBSERVED_REMAINING_MINUTES"


def test_exp1b_weighted_median_and_crps_supported():
    scenario_rows = [
        {
            "episode_id": "ep1",
            "decision_node_id": "node1",
            "scenario_id": scenario_id,
            "scenario_weight": 0.25,
            "T_IB_A00": [2.0, 4.0, 4.0, 8.0][scenario_id],
            "D_OB": [None, 1.0, 2.0, 3.0][scenario_id],
            "D_TX": [None, None, None, None][scenario_id],
        }
        for scenario_id in range(4)
    ]
    label_rows = [
        {
            "episode_id": "ep1",
            "decision_node_id": "node1",
            "target_name": "T_IB_REMAINING_HAZARD",
            "exact_minutes": 4.0,
            "active": True,
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "node1",
            "target_name": "D_OB",
            "exact_minutes": 2.0,
            "active": True,
        },
        {
            "episode_id": "ep1",
            "decision_node_id": "node1",
            "target_name": "D_TX",
            "exact_minutes": 0.0,
            "active": False,
        },
    ]
    records, _ = build_exp1b_records(
        scenario_rows=scenario_rows,
        label_rows=label_rows,
        pre_states=[],
        model_id="M1_V2_GRU_H32_CURRENT_ONLY",
        model_role="CURRENT",
    )
    by_target = {record["target"]: record for record in records}
    assert by_target["T_IB_A00"]["point_prediction"] == 4.0
    assert by_target["T_IB_A00"]["observed_minutes"] == 4.0
    assert by_target["T_IB_A00"]["absolute_error"] == 0.0
    assert by_target["T_IB_A00"]["crps_supported"] is True
    assert by_target["D_OB"]["point_prediction"] == 2.0
    assert by_target["D_OB"]["crps_supported"] is True
    assert by_target["D_TX"]["point_prediction"] is None
    assert by_target["D_TX"]["crps_supported"] is False
    assert by_target["D_TX"]["absolute_error"] is None
    assert by_target["D_TX"]["crps"] is None


def test_episode_mean_bootstrap_aggregates_within_episode():
    rows = [
        {"episode_id": "ep1", "absolute_error": 1.0},
        {"episode_id": "ep1", "absolute_error": 3.0},
        {"episode_id": "ep2", "absolute_error": 10.0},
    ]
    first = _episode_mean_bootstrap(
        rows, "absolute_error", replicates=100, seed=20260825,
    )
    second = _episode_mean_bootstrap(
        rows, "absolute_error", replicates=100, seed=20260825,
    )
    assert first == second
    assert first["n_episodes"] == 2
    assert first["estimate"] == (2.0 + 10.0) / 2.0
    assert len(first["ci_95"]) == 2


def test_channels_equal_semantics():
    left = {
        "Flight": {"value_cu": 0.5, "supported_scenario_count": 2},
        "Passenger": {"value_cu": 0.25, "supported_scenario_count": 2},
        "Resource": {"value_cu": 0.2, "supported_scenario_count": 2},
        "P_itinerary_events": 1.0,
        "P_service_events": None,
    }
    right = {
        "Flight": {"value_cu": 0.5, "supported_scenario_count": 2},
        "Passenger": {"value_cu": 0.25, "supported_scenario_count": 2},
        "Resource": {"value_cu": 0.2, "supported_scenario_count": 2},
        "P_itinerary_events": 1.0,
        "P_service_events": None,
    }
    assert _channels_equal(left, right) is True
    right["Resource"] = {"value_cu": 0.3, "supported_scenario_count": 2}
    assert _channels_equal(left, right) is False
    right["Resource"] = {"value_cu": 0.2, "supported_scenario_count": 2}
    right["P_service_events"] = 5.0
    assert _channels_equal(left, right) is False
