from __future__ import annotations

import torch
from torch.nn import functional as F


def episode_balanced_cross_entropy(
    logits: torch.Tensor,
    soft_targets: torch.Tensor,
    episode_ids: list[str] | tuple[str, ...],
) -> torch.Tensor:
    if logits.shape != soft_targets.shape or logits.shape[0] != len(episode_ids):
        raise ValueError("M1_LOSS_SHAPE_INVALID")
    counts: dict[str, int] = {}
    for episode_id in episode_ids:
        counts[episode_id] = counts.get(episode_id, 0) + 1
    weights = torch.tensor(
        [1.0 / counts[episode_id] for episode_id in episode_ids],
        dtype=logits.dtype,
        device=logits.device,
    )
    row_loss = -(soft_targets * F.log_softmax(logits, dim=-1)).sum(dim=-1)
    return (row_loss * weights).sum() / weights.sum()
