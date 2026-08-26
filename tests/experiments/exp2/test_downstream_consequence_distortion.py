from __future__ import annotations

import math

import pandas as pd
import pytest

from exp.exp2.downstream_consequence_distortion import (
    ALPHA,
    BOOTSTRAP_SEED,
    SAFETY,
    adapted_m2_row,
    bootstrap_summary,
    episode_aggregate,
    weighted_cvar,
    weighted_mean,
    _component_distribution,
)


def _row(*, value: float | None = 2.0, support: str = "SUPPORTED", weight: float = 0.5) -> dict:
    return {
        "scenario_weight": weight,
        "components": [{"component_id": "F_execution", "constructed_value_cu": value, "support_state": support}],
    }


def test_weighted_mean_requires_normalized_finite_distribution() -> None:
    assert weighted_mean([1.0, 3.0], [0.25, 0.75]) == 2.5
    with pytest.raises(RuntimeError, match="SCENARIO_WEIGHT_INVALID"):
        weighted_mean([1.0, 3.0], [0.25, 0.50])
    with pytest.raises(RuntimeError, match="NONFINITE_COMPONENT_VALUE"):
        weighted_mean([1.0, math.nan], [0.5, 0.5])


def test_weighted_cvar_uses_boundary_mass_splitting() -> None:
    assert weighted_cvar([0.0, 10.0, 20.0], [0.85, 0.10, 0.05], ALPHA) == pytest.approx(15.0)


def test_component_distribution_never_drops_unsupported_scenarios() -> None:
    result, reason = _component_distribution([_row(), _row(support="ABSTAIN")], "F_execution")
    assert result is None
    assert reason == "COMPONENT_ABSTAIN"


def test_component_distribution_never_renormalizes_invalid_weights() -> None:
    result, reason = _component_distribution([_row(weight=0.4), _row(weight=0.4)], "F_execution")
    assert result is None
    assert reason == "SCENARIO_WEIGHT_INVALID"


def test_component_distribution_rejects_nonfinite_values() -> None:
    result, reason = _component_distribution([_row(value=1.0), _row(value=float("inf"))], "F_execution")
    assert result is None
    assert reason == "NONFINITE_COMPONENT_VALUE"


def test_episode_aggregate_precedes_bootstrap() -> None:
    records = pd.DataFrame([
        {"episode_id": "e1", "decision_node_id": "n1", "operational_stage": "PRE", "component": "F_execution", "channel": "Flight", "comparison": "POINT_MINUS_JOINT", "absolute_mean_distortion": 1.0, "absolute_tail_distortion": 3.0},
        {"episode_id": "e1", "decision_node_id": "n2", "operational_stage": "POST", "component": "F_execution", "channel": "Flight", "comparison": "POINT_MINUS_JOINT", "absolute_mean_distortion": 3.0, "absolute_tail_distortion": 5.0},
    ])
    result = episode_aggregate(records)
    assert result.loc[0, "n_nodes"] == 2
    assert result.loc[0, "absolute_mean_distortion"] == 2.0
    assert result.loc[0, "absolute_tail_distortion"] == 4.0


def test_bootstrap_is_deterministic_at_episode_unit() -> None:
    episodes = pd.DataFrame([
        {"episode_id": f"e{i}", "component": "F_execution", "channel": "Flight", "comparison": "POINT_MINUS_JOINT", "absolute_mean_distortion": float(i), "absolute_tail_distortion": float(i + 1), "n_nodes": 1}
        for i in range(1, 5)
    ])
    first = bootstrap_summary(episodes, reps=50, seed=BOOTSTRAP_SEED)
    second = bootstrap_summary(episodes, reps=50, seed=BOOTSTRAP_SEED)
    pd.testing.assert_frame_equal(first, second)


def test_adapted_row_preserves_identity_and_recomputes_dto() -> None:
    class Sample:
        scenario_id = 7
        scenario_weight = 1.0
        R_IB = 3.0
        D_OB = 4.0
        D_TX = 5.0
        D_TO = 9.0
        field_source_scenario_ids = {"R_IB": 5, "D_OB": 6, "D_TX": 7, "D_TO": "DERIVED_FROM_D_OB_PLUS_D_TX"}

    base = {
        "scenario_id": 7, "scenario_weight": 0.004, "T_IB_A00": 1.0, "D_OB": 2.0, "D_TX": 3.0, "D_TO": 5.0,
        "lineage": ("M1",),
        "target_envelopes": [
            {"target_name": "T_IB_A00", "scalar_minutes": 1.0},
            {"target_name": "D_OB", "scalar_minutes": 2.0},
            {"target_name": "D_TX", "scalar_minutes": 3.0},
        ],
    }
    result = adapted_m2_row(base, Sample(), variant_id="EXP2A_MARGINAL", representation_hash="sha256:test")
    assert result["scenario_id"] == 7 and result["scenario_weight"] == 1.0
    assert result["D_TO"] == result["D_OB"] + result["D_TX"] == 9.0
    assert base["D_TO"] == 5.0


def test_execution_safety_forbids_final_test_and_paper_full() -> None:
    assert SAFETY == {
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "DEVELOPMENT_TUNING": False,
    }
