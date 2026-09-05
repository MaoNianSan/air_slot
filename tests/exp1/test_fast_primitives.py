from __future__ import annotations

from exp.exp1.analysis import consequence_wasserstein, history_delta_crps, state_variogram_contrasts
from exp.exp1.history import episode_balanced_estimate, episode_cluster_bootstrap
from exp.exp1.metrics import variogram_score, weighted_crps, weighted_wasserstein_1
from exp.exp1.protocol import Exp1Protocol, ProtocolError
from exp.exp1.representations import ScenarioState, JointRepresentation, build_marginal, build_point


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


def test_exact_primary_metrics_and_contrasts():
    assert weighted_crps((0.0, 2.0), (0.5, 0.5), 1.0) == 0.5
    assert weighted_wasserstein_1((0.0,), (1.0,), (2.0,), (1.0,)) == 2.0
    joint = _joint()
    point = build_point(joint)
    marginal = build_marginal(joint)
    point_delta, marginal_delta, joint_score = state_variogram_contrasts(
        joint, point, marginal, (1.0, 2.0, 3.0)
    )
    assert joint_score >= 0.0
    assert point_delta >= 0.0
    assert marginal_delta >= 0.0
    history, current, delta = history_delta_crps((0.0,), (1.0,), (2.0,), (1.0,), 1.0)
    assert (history, current, delta) == (1.0, 1.0, 0.0)
    assert consequence_wasserstein((0.0,), (1.0,), (2.0,), (1.0,), 2.0) == 1.0


def test_exact_marginal_variogram_uses_product_expectation():
    joint = _joint()
    marginal = build_marginal(joint)
    score = variogram_score(
        marginal.values,
        marginal.weights,
        (1.0, 2.0, 3.0),
        marginal_values=tuple(tuple(v for v, _ in axis) for axis in marginal.marginals),
        marginal_weights=tuple(tuple(w for _, w in axis) for axis in marginal.marginals),
    )
    assert score >= 0.0


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
