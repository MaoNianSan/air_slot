from __future__ import annotations

import numpy as np
import torch

from overall_run.src.m1.distribution import (
    hard_label,
    interval_soft_label,
    learned_upper_bins,
    predecessor_bins,
)
from overall_run.src.m1.model.loss import episode_balanced_cross_entropy


def test_bins_overflow_and_soft_labels() -> None:
    ib = predecessor_bins()
    assert ib.lower_minutes[-1] == 480.0
    assert ib.upper_minutes[-1] is None
    learned = learned_upper_bins([5.0, 10.0, 21.0], quantile=1.0)
    assert learned.lower_minutes[-1] == 25.0
    assert hard_label(999.0, learned)[-1] == 1.0
    soft = interval_soft_label(2.5, 7.5, learned)
    np.testing.assert_allclose(soft[:2], [0.5, 0.5])
    assert np.isclose(soft.sum(), 1.0)


def test_episode_balanced_cross_entropy_weights_each_episode_equally() -> None:
    logits = torch.tensor([[3.0, 0.0], [3.0, 0.0], [0.0, 3.0]])
    targets = torch.tensor([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
    loss = episode_balanced_cross_entropy(logits, targets, ["a", "a", "b"])
    row = -(targets * torch.log_softmax(logits, dim=-1)).sum(dim=-1)
    expected = (row[:2].mean() + row[2]) / 2.0
    assert torch.allclose(loss, expected)
