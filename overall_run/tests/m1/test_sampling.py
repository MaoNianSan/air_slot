from __future__ import annotations

import numpy as np

from overall_run.src.m1.distribution import DiscreteBins, fixed_uniform, sample_discrete


def test_fixed_random_numbers_are_stable_across_query_times() -> None:
    first = [fixed_uniform("ep-1", sample_id, "R_IB", 7) for sample_id in range(20)]
    second = [fixed_uniform("ep-1", sample_id, "R_IB", 7) for sample_id in range(20)]
    assert first == second
    assert first != [fixed_uniform("ep-1", sample_id, "R_OB", 7) for sample_id in range(20)]


def test_discrete_sampling_reports_overflow() -> None:
    bins = DiscreteBins((0.0, 5.0), (5.0, None))
    value, overflow = sample_discrete(np.array([0.1, 0.9]), bins, 0.95)
    assert overflow is True
    assert np.isnan(value)
