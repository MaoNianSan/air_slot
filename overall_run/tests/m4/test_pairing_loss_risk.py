from __future__ import annotations

import numpy as np
import pytest

from src.m4 import (
    calculate_post_loss,
    normalize_weights,
    response_draw_index,
    risk_score,
    run_m4_synthetic_integration,
    weighted_cvar,
    weighted_mean,
    weighted_positive_probability,
    weighted_var,
)
from src.m4.contracts import M4RiskConfig, M4_DRAW_PAIRING_VERSION


def _index(sample_id: int, m3_artifact) -> int:
    return response_draw_index(
        episode_id="ep-m4",
        sample_id=sample_id,
        m3_sample_hash=m3_artifact.sample_hash,
        n_draws=m3_artifact.n_draws,
    )


def test_draw_pairing_snapshot_invariant(m3_artifact) -> None:
    assert _index(3, m3_artifact) == _index(3, m3_artifact)


def test_draw_pairing_action_aligned(m3_artifact) -> None:
    draw_for_a11 = _index(2, m3_artifact)
    draw_for_a52 = _index(2, m3_artifact)
    assert draw_for_a11 == draw_for_a52


def test_draw_pairing_row_order_invariant(m3_artifact) -> None:
    first = {sample_id: _index(sample_id, m3_artifact) for sample_id in (0, 1, 2, 3)}
    second = {sample_id: _index(sample_id, m3_artifact) for sample_id in (3, 1, 0, 2)}
    assert first == second


def test_draw_pairing_worker_invariant(m3_artifact) -> None:
    serial = [_index(sample_id, m3_artifact) for sample_id in range(20)]
    partitioned = [
        value
        for partition in (range(0, 20, 2), range(1, 20, 2))
        for value in [_index(sample_id, m3_artifact) for sample_id in partition]
    ]
    assert sorted(serial) == sorted(partitioned)


def test_draw_pairing_within_range(m3_artifact) -> None:
    assert all(0 <= _index(sample_id, m3_artifact) < m3_artifact.n_draws for sample_id in range(100))


def test_draw_pairing_versioned() -> None:
    assert M4_DRAW_PAIRING_VERSION == "M4_STABLE_SHARED_DRAW_INDEX_V1"


def test_A00_sample_identity(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A00", losses=losses, artifact=m3_artifact)
    assert np.array_equal(post.pre_total_loss_rmb, post.post_total_loss_rmb)


def test_subitem_post_loss_formula(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A12", losses=losses, artifact=m3_artifact)
    sample = 1
    draw = post.draw_indices[sample]
    subitem = "F_WAIT"
    index = list(post.pre_subitem_loss_rmb).index(subitem)
    recovery = m3_artifact.subitem_recovery_rates["A12"][draw, index]
    expected = (1.0 - recovery) * losses[sample].subitem_loss_rmb[subitem]
    assert np.isclose(post.post_subitem_loss_rmb[subitem][sample], expected)


def test_structural_zero_recovery(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A11", losses=losses, artifact=m3_artifact)
    footprint = m3_artifact.footprint_table
    zero_subitem = footprint[
        footprint["action_id"].eq("A11") & footprint["footprint_role"].eq("NONE")
    ].iloc[0]["subitem_id"]
    assert np.array_equal(
        post.post_subitem_loss_rmb[zero_subitem],
        post.pre_subitem_loss_rmb[zero_subitem],
    )


def test_channel_cost_added_once(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A12", losses=losses, artifact=m3_artifact)
    expected_f = sum(
        post.post_subitem_loss_rmb[name] for name in ("F_TURN", "F_WAIT", "F_PROPAGATION")
    ) + post.implementation_costs_rmb["F"]
    assert np.allclose(post.post_channel_loss_rmb["F"], expected_f)


def test_channel_sum_equals_total(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A22", losses=losses, artifact=m3_artifact)
    assert np.allclose(
        post.post_total_loss_rmb,
        sum(post.post_channel_loss_rmb[channel] for channel in ("F", "P", "R")),
    )


def test_post_loss_nonnegative(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    for action_id in m3_artifact.action_catalog:
        post = calculate_post_loss(action_id=action_id, losses=losses, artifact=m3_artifact)
        assert np.all(post.post_total_loss_rmb >= 0.0)


def test_m3_cost_not_rescaled_by_m4(m4_input_factory, m3_artifact) -> None:
    _, losses = m4_input_factory()
    post = calculate_post_loss(action_id="A12", losses=losses, artifact=m3_artifact)
    for sample, draw in enumerate(post.draw_indices):
        assert post.implementation_costs_rmb["P"][sample] == m3_artifact.implementation_costs_rmb["A12"][draw, 1]


def test_sample_weight_normalization() -> None:
    normalized = normalize_weights(np.array([1.0, 2.0, 3.0]))
    assert np.allclose(normalized, [1 / 6, 2 / 6, 3 / 6])


def test_weighted_mean() -> None:
    assert weighted_mean(np.array([0.0, 10.0]), np.array([0.75, 0.25])) == 2.5


def test_weighted_var() -> None:
    assert weighted_var(np.array([0.0, 10.0]), np.array([0.9, 0.1]), 0.9) == 0.0


def test_weighted_cvar90() -> None:
    assert weighted_cvar(np.array([0.0, 10.0]), np.array([0.9, 0.1]), 0.9) == pytest.approx(10.0)


def test_risk_weights_sum_to_one() -> None:
    with pytest.raises(ValueError, match="SUM_TO_ONE"):
        risk_score(
            np.array([1.0, 2.0]),
            np.array([0.5, 0.5]),
            M4RiskConfig(expected_weight=0.8, cvar_weight=0.3),
        )


def test_A00_paired_improvement(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = run_m4_synthetic_integration(
        bundle,
        losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping={"TURNAROUND": "t1"},
        opportunity_overrides=opportunity_overrides,
    )
    a00 = artifact.action_frame.set_index("action_id").loc["A00"]
    assert a00["expected_improvement_vs_a00"] == pytest.approx(0.0)
    assert a00["tail_improvement_vs_a00"] == pytest.approx(0.0)
    assert a00["risk_score_improvement_vs_a00"] == pytest.approx(0.0)


def test_weighted_net_benefit_probability() -> None:
    probability = weighted_positive_probability(
        np.array([-1.0, 2.0, 3.0]),
        np.array([0.2, 0.3, 0.5]),
    )
    assert probability == pytest.approx(0.8)
