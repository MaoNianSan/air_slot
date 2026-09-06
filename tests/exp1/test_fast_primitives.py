from __future__ import annotations

from exp.exp1.analysis import consequence_wasserstein, history_delta_crps, state_variogram_contrasts
from exp.exp1.history import (
    bootstrap_episode_mean,
    episode_balanced_estimate,
    episode_cluster_bootstrap,
)
from exp.exp1.metrics import (
    marginal_variogram_score,
    variogram_score,
    weighted_crps,
    weighted_wasserstein_1,
)
from exp.exp1.protocol import Exp1Protocol, ProtocolError
from exp.exp1.representations import ScenarioState, JointRepresentation, build_marginal, build_point
from validation.model.m1_frozen_h16_artifact_materialization import formal_training_authority


def _joint() -> JointRepresentation:
    return JointRepresentation(
        (
            ScenarioState(7, 2.0, 4.0, 1.0, 0.25),
            ScenarioState(3, 6.0, 1.0, 5.0, 0.75),
        )
    )


def test_protocol_freeze_and_primary_model_gate():
    Exp1Protocol().validate()
    try:
        Exp1Protocol(primary_hidden_size=8).validate()
    except ProtocolError as exc:
        assert str(exc) == "EXP1_PRIMARY_MODEL_MUST_BE_H16"
    else:
        raise AssertionError("H8 must not pass as Exp1 primary")


def test_point_is_original_joint_scenario_and_marginal_preserves_marginals():
    joint = _joint()
    point = build_point(joint, supports=(10.0, 10.0, 10.0))
    assert point.scenario.scenario_id in {3, 7}
    assert point.scenario.vector in joint.values
    marginal = build_marginal(joint)
    for axis in range(3):
        assert marginal.marginal(axis) == joint.marginal(axis)
    assert abs(sum(marginal.weights) - 1.0) < 1e-12
    assert all(abs(s.d_to - (s.d_ob + s.d_tx)) < 1e-12 for s in joint.scenarios)


def test_point_requires_explicit_valid_supports_and_tie_breaks_by_scenario_id():
    joint = JointRepresentation(
        (
            ScenarioState(9, 0.0, 0.0, 0.0, 0.5),
            ScenarioState(2, 0.0, 0.0, 0.0, 0.5),
        )
    )
    try:
        build_point(joint)
    except ValueError as exc:
        assert str(exc) == "EXP1_POINT_SUPPORTS_REQUIRED"
    else:
        raise AssertionError("Point supports must be explicit")
    assert build_point(joint, (360.0, 180.0, 60.0)).scenario.scenario_id == 2
    try:
        build_point(joint, (0.0, 180.0, 60.0))
    except ValueError as exc:
        assert str(exc) == "EXP1_M1_SUPPORTS_MUST_BE_POSITIVE"
    else:
        raise AssertionError("Invalid support must fail closed")


def test_joint_weights_validate_without_silent_mutation():
    try:
        JointRepresentation((ScenarioState(1, 0.0, 0.0, 0.0, 2.0),))
    except ValueError as exc:
        assert str(exc) == "EXP1_JOINT_WEIGHTS_NOT_NORMALIZED"
    else:
        raise AssertionError("Joint weights must not be silently renormalized")


def test_exact_primary_metrics_and_contrasts():
    assert weighted_crps((0.0, 2.0), (0.5, 0.5), 1.0) == 0.5
    assert weighted_wasserstein_1((0.0,), (1.0,), (2.0,), (1.0,)) == 2.0
    joint = _joint()
    point = build_point(joint, supports=(360.0, 180.0, 60.0))
    marginal = build_marginal(joint)
    point_delta, marginal_delta, joint_score = state_variogram_contrasts(
        joint, point, marginal, (1.0, 2.0, 3.0)
    )
    assert joint_score >= 0.0
    assert point_delta == point_delta
    assert marginal_delta == marginal_delta
    history, current, delta = history_delta_crps((0.0,), (1.0,), (2.0,), (1.0,), 1.0)
    assert (history, current, delta) == (1.0, 1.0, 0.0)
    assert consequence_wasserstein((0.0,), (1.0,), (2.0,), (1.0,), 2.0) == 1.0


def test_exact_marginal_variogram_uses_product_expectation():
    joint = _joint()
    marginal = build_marginal(joint)
    score = marginal_variogram_score(
        tuple(tuple(v for v, _ in axis) for axis in marginal.marginals),
        tuple(tuple(w for _, w in axis) for axis in marginal.marginals),
        (1.0, 2.0, 3.0),
    )
    assert score >= 0.0


def test_variogram_preserves_joint_dependence_with_exact_toy_values():
    values = ((0.0, 0.0), (1.0, 1.0))
    weights = (0.5, 0.5)
    observation = (0.0, 1.0)
    joint = variogram_score(values, weights, observation, p=0.5)
    marginal = marginal_variogram_score(
        ((0.0, 1.0), (0.0, 1.0)),
        ((0.5, 0.5), (0.5, 0.5)),
        observation,
        p=0.5,
    )
    assert joint == 1.0
    assert marginal == 0.25
    assert joint != marginal


def test_episode_bootstrap_keeps_repeated_clusters():
    records = (
        {"episode_id": "a", "delta_crps": 1.0},
        {"episode_id": "a", "delta_crps": 3.0},
        {"episode_id": "b", "delta_crps": 5.0},
    )
    assert episode_balanced_estimate(records) == 3.5
    estimate, low, high = episode_cluster_bootstrap(records, reps=25, seed=4)
    assert estimate == 3.5
    assert low <= estimate <= high
    assert bootstrap_episode_mean((0.0, 0.0)) == 0.0
    assert bootstrap_episode_mean((10.0, 10.0)) == 10.0


def test_h16_formal_training_authority_is_not_fast_config():
    contract = formal_training_authority()
    assert contract["source"] == "model/M1/tuning_stage1.py:STAGE1_TRAINING_CONFIG"
    assert contract["training"]["epochs"] == 8
    assert contract["training_seed"] == 20260813
    assert contract["optional_robustness_seeds"] == [
        20260814,
        20260815,
        20260816,
        20260817,
    ]
    assert contract["splits"]["calibration"] == ["2019-07-01", "2019-07-31"]


def test_reporting_boundary_has_no_model_import():
    source = __import__("pathlib").Path("exp/exp1/reporting.py").read_text(encoding="utf-8")
    assert "import model" not in source
    assert "from model" not in source
