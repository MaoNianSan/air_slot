"""Real-Data2 FAST bindings stay distinct from source-free contract fixtures."""

import pytest

from exp.common.context import real_fast_context
from exp.common.real_fast import state_vintage_bindings
from exp.common.result_schema import MetricLevel, MetricObservation, SupportStatus
from exp.exp1.runner import Exp1Runner
from exp.exp2.protocol import Exp2RunContext
from exp.exp2.representation import ScenarioRepresentationAdapter
from exp.exp2.runner import Exp2Runner
from exp.exp3.runner import Exp3Runner
from exp.exp4.runner import Exp4Runner
from model.common.errors import ContractError


def _representation_inputs():
    scenarios = tuple(
        {
            "scenario_id": scenario_id,
            "scenario_weight": 1 / 3,
            "D_OB": float(3 * (scenario_id + 1)),
            "D_TX": float(2 * (scenario_id + 1)),
            "D_TO": float(5 * (scenario_id + 1)),
            "lineage": (f"m1:{scenario_id}",),
        }
        for scenario_id in range(3)
    )
    component_ids = (
        "F_continuity", "F_execution", "F_propagation", "P_time",
        "P_itinerary", "P_service", "R_operating",
    )
    channels = ("Flight", "Flight", "Flight", "Passenger", "Passenger", "Passenger", "Resource")
    consequences = tuple({
        "scenario_id": scenario_id,
        "scenario_weight": 1 / 3,
        "components": tuple({
            "component_id": component_id,
            "aspect": channel,
            "constructed_value_cu": float(index + scenario_id),
            "support_state": "SUPPORTED",
            "reference_lineage": (f"m2:{scenario_id}:{component_id}",),
        } for index, (component_id, channel) in enumerate(
            zip(component_ids, channels, strict=True), start=1)),
    } for scenario_id in range(3))
    return scenarios, consequences


def test_real_fast_reuses_one_frozen_data2_development_context():
    context = real_fast_context(seed=17)
    results = tuple(
        result
        for runner in (Exp1Runner(), Exp2Runner(), Exp3Runner(), Exp4Runner())
        for result in runner.execute_real_fast(context=context)
    )
    assert context.execution_tier.value == "REAL_DATA_FAST"
    assert context.dataset_id == "DATA2"
    assert context.split == "DEVELOPMENT"
    assert context.episode_count == 5
    assert context.node_count == 69
    assert {result.lineage["cohort_hash"] for result in results} == {
        context.lineage["cohort_hash"],
    }
    assert {result.final_test_access_count for result in results} == {0}


def test_exp1_fixed_history_is_explicit_sensitivity_only():
    runner = Exp1Runner()
    assert "EXP1B_FIXED_HISTORY_30" not in runner.variants
    assert "EXP1B_FIXED_HISTORY_30" in runner.variants_for(include_sensitivity=True)
    assert tuple(item.variant_id for item in runner.execute_fast()) == runner.variants
    assert tuple(item.variant_id for item in runner.execute_fast(include_sensitivity=True))[-1] == (
        "EXP1B_FIXED_HISTORY_30"
    )


def test_exp2_representation_stage_remains_partial_when_m4_is_blocked():
    m1_scenarios, m2_consequences = _representation_inputs()
    result = Exp2Runner().execute(Exp2RunContext(
        variant_id="EXP2A_POINT",
        dataset_id="DATA2_FIXTURE",
        seed=7,
        m1_scenarios=m1_scenarios,
        m2_consequences=m2_consequences,
        m1_artifact_version="M1_FIXTURE_V1",
        m2_artifact_version="M2_FIXTURE_V1",
        model_versions={"M1": "V2", "M2": "V2", "M3": "V4", "M4": "V2"},
        downstream=None,
        representation_metrics={
            "STATE_CRPS": MetricObservation(
                metric_id="STATE_CRPS",
                level=MetricLevel.STATE,
                value=1.25,
                unit="minutes",
                support_status=SupportStatus.SUPPORTED,
            ),
        },
    ))
    assert result.support_status is SupportStatus.PARTIAL
    assert result.metrics["STATE_CRPS"].support_status is SupportStatus.SUPPORTED
    assert result.metrics["DECISION_ACTION_DISAGREEMENT"].support_status is SupportStatus.NOT_RUN
    assert result.provenance["representation_status"] == "SUPPORTED"
    assert result.provenance["downstream_status"] == "BLOCKED"


def test_exp2_rejects_non_equal_weight_marginal_without_approximation():
    scenarios = (
        {"scenario_id": 0, "scenario_weight": 0.7, "D_OB": 1, "D_TX": 2, "lineage": ("a",)},
        {"scenario_id": 1, "scenario_weight": 0.3, "D_OB": 3, "D_TX": 4, "lineage": ("b",)},
    )
    adapter = ScenarioRepresentationAdapter(scenarios, artifact_version="M1_FIXTURE")
    with pytest.raises(ContractError, match="BLOCKED_WEIGHTED_TRANSFORM_NOT_IMPLEMENTED"):
        adapter.transform("EXP2A_MARGINAL")


def test_exp3_lag_uses_only_prior_vintage_state():
    context = real_fast_context()
    lagged = state_vintage_bindings(context, lag_minutes=5)
    assert all(item["current_state_read"] is False for item in lagged)
    assert all(
        item["state_vintage_node_id"] is None
        or item["state_vintage_node_id"] != item["decision_node_id"]
        for item in lagged
    )
    results = {item.variant_id: item for item in Exp3Runner().execute_real_fast(context=context)}
    assert results["EXP3B_STATE_LAG_5"].metrics["STATE_VINTAGE_COVERAGE"].metadata[
        "current_state_read"
    ] is False


def test_exp4_real_fast_reports_all_latency_percentiles_and_budgets():
    results = Exp4Runner().execute_real_fast(context=real_fast_context())
    runtime = next(item for item in results if item.variant_id == "EXP4D_END_TO_END_RUNTIME")
    assert all(
        runtime.metrics[key].value is not None
        for key in ("E2E_P50_SECONDS", "E2E_P95_SECONDS", "E2E_P99_SECONDS")
    )
    assert all(
        runtime.metrics[key].metadata["budget_seconds"] == budget
        for key, budget in (("WITHIN_60S", 60), ("WITHIN_120S", 120), ("WITHIN_300S", 300))
    )
