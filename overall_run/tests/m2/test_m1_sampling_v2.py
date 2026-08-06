from __future__ import annotations

import numpy as np
import pytest

from overall_run.src.m1.distribution import DiscreteBins, build_empirical_tail_artifact
from overall_run.src.m1.distribution.sampling import fixed_uniform_purpose, sample_discrete


def test_finite_bin_uses_stable_within_bin_uniform() -> None:
    bins = DiscreteBins((0.0, 5.0), (5.0, None))
    first = sample_discrete(np.array([1.0, 0.0]), bins, 0.2, episode_id="ep", sample_id=1, target_name="R_IB", base_seed=7)
    second = sample_discrete(np.array([1.0, 0.0]), bins, 0.2, episode_id="ep", sample_id=1, target_name="R_IB", base_seed=7)
    assert first == second
    assert 0.0 < first[0] < 5.0


def test_sampling_purposes_use_distinct_streams() -> None:
    within = fixed_uniform_purpose("ep", 1, "R_IB", 7, "WITHIN_BIN")
    tail = fixed_uniform_purpose("ep", 1, "R_IB", 7, "OVERFLOW_TAIL")
    assert within != tail


def test_empirical_tail_is_training_only_and_unresolved_without_support() -> None:
    artifact = build_empirical_tail_artifact("R_IB", (5.0, 6.0), 5.0, artifact_version="tail-v1", minimum_tail_count=3)
    assert artifact.resolution_status == "TAIL_UNRESOLVED"
    with pytest.raises(ValueError, match="M1_TAIL_ARTIFACT_NON_TRAIN_SOURCE"):
        build_empirical_tail_artifact("R_IB", (5.0,), 5.0, artifact_version="tail-v1", source_split="VALIDATION")


def test_overflow_never_silently_returns_lower_bound() -> None:
    bins = DiscreteBins((0.0, 5.0), (5.0, None))
    unresolved, flag = sample_discrete(np.array([0.0, 1.0]), bins, 0.8, episode_id="ep", sample_id=1, target_name="R_IB", base_seed=7)
    assert flag is True
    assert np.isnan(unresolved)
    resolved, flag = sample_discrete(np.array([0.0, 1.0]), bins, 0.8, overflow_tail_values=(7.0, 9.0), episode_id="ep", sample_id=1, target_name="R_IB", base_seed=7)
    assert flag is True
    assert resolved >= 5.0
