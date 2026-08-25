from __future__ import annotations

import numpy as np
import pandas as pd

from exp.reporting.section5_secondary_analysis import (
    _representation_draws,
    _variogram_score,
    episode_bootstrap,
)


def test_episode_bootstrap_is_deterministic_and_episode_level():
    first = episode_bootstrap([1.0, 3.0, 5.0], replicates=200, seed=7)
    second = episode_bootstrap([1.0, 3.0, 5.0], replicates=200, seed=7)
    assert first == second
    assert first.estimate == 3.0
    assert first.n_episodes == 3


def test_exp2_representation_transforms_do_not_reuse_joint_pairs():
    rows = pd.DataFrame(
        {
            "scenario_id": [0, 1, 2],
            "scenario_weight": [1 / 3, 1 / 3, 1 / 3],
            "D_OB": [0.0, 10.0, 20.0],
            "D_TX": [0.0, 20.0, 10.0],
        }
    )
    joint = _representation_draws(rows, "JOINT")
    marginal = _representation_draws(rows, "MARGINAL")
    point = _representation_draws(rows, "POINT")
    assert not np.array_equal(joint, marginal)
    assert point.shape == (1, 2)
    assert _variogram_score(joint, (5.0, 15.0)) != _variogram_score(marginal, (5.0, 15.0))
