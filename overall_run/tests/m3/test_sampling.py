from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from src.m3 import (
    SUBITEMS_M2_V2,
    generate_m3_library,
    generate_test_fixture_library,
    synthetic_test_parameters,
)


def test_formal_generator_blocks_unfrozen_parameters(m3_contract, cfg) -> None:
    with pytest.raises(RuntimeError, match="M3_PARAMETER_NOT_FROZEN"):
        generate_m3_library(
            m3_contract,
            n_draws=16,
            m2_contract=cfg.scientific["m2"],
        )


def test_fixture_shapes_bounds_costs_and_a00(fixture_artifact) -> None:
    for action_id in fixture_artifact.action_catalog:
        recovery = fixture_artifact.subitem_recovery_rates[action_id]
        costs = fixture_artifact.implementation_costs_rmb[action_id]
        assert recovery.shape == (256, 9)
        assert costs.shape == (256, 3)
        assert np.all((recovery >= 0.0) & (recovery <= 1.0))
        assert np.all(costs >= 0.0)
    assert np.all(fixture_artifact.subitem_recovery_rates["A00"] == 0.0)
    assert np.all(fixture_artifact.implementation_costs_rmb["A00"] == 0.0)
    assert np.all(fixture_artifact.success_draws["A00"])


def test_failure_zero_and_shared_action_intensity(m3_contract, fixture_artifact) -> None:
    action_id = "A12"
    success = fixture_artifact.success_draws[action_id]
    assert (~success).any()
    recovery = fixture_artifact.subitem_recovery_rates[action_id]
    assert np.all(recovery[~success] == 0.0)
    primary = recovery[:, SUBITEMS_M2_V2.index("F_WAIT")]
    secondary = recovery[:, SUBITEMS_M2_V2.index("F_PROPAGATION")]
    intensity = fixture_artifact.response_intensities[action_id]
    assert np.array_equal(primary[success], intensity[success])
    assert np.allclose(secondary[success], 0.35 * intensity[success])
    assert np.all(secondary <= primary)


def test_structural_zeros_are_exact(fixture_artifact) -> None:
    frame = fixture_artifact.response_samples_frame()
    zeros = frame[frame["footprint_role"].eq("NONE")]
    assert zeros["subitem_recovery_rate"].eq(0.0).all()
    assert "sample_id" not in frame.columns
    assert "response_draw_id" in frame.columns


def test_fixed_random_stream_reproducibility_and_identity(m3_contract, cfg) -> None:
    first = generate_test_fixture_library(
        m3_contract, n_draws=128, base_seed=17, m2_contract=cfg.scientific["m2"]
    )
    second = generate_test_fixture_library(
        m3_contract, n_draws=128, base_seed=17, m2_contract=cfg.scientific["m2"]
    )
    assert first.sample_hash == second.sample_hash
    assert np.array_equal(first.response_intensities["A61"], second.response_intensities["A61"])
    assert not np.array_equal(first.response_intensities["A61"], first.response_intensities["A62"])


def test_parameter_version_changes_sample_hash(m3_contract, cfg) -> None:
    responses, costs = synthetic_test_parameters(m3_contract)
    first = generate_m3_library(
        m3_contract,
        n_draws=64,
        base_seed=19,
        response_parameters=responses,
        cost_parameters=costs,
        m2_contract=cfg.scientific["m2"],
        formal=False,
    )
    changed = dict(responses)
    changed["A11"] = replace(changed["A11"], parameter_version="M3_V4_SYNTHETIC_FIXTURE_V2")
    second = generate_m3_library(
        m3_contract,
        n_draws=64,
        base_seed=19,
        response_parameters=changed,
        cost_parameters=costs,
        m2_contract=cfg.scientific["m2"],
        formal=False,
    )
    assert first.parameter_hash != second.parameter_hash
    assert first.sample_hash != second.sample_hash
