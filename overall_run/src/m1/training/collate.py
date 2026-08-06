from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import torch

from .dataset import M1TrainingEpisode


@dataclass(frozen=True)
class M1TrainingBatch:
    episode_ids: tuple[str, ...]
    feature_sequence: torch.Tensor
    target_distributions: Mapping[str, torch.Tensor]
    target_available_mask: Mapping[str, torch.Tensor]
    valid_node_mask: torch.Tensor
    sequence_lengths: torch.Tensor
    episode_weights: torch.Tensor
    partitions: tuple[str, ...]


def collate_training_episodes(
    episodes: Sequence[M1TrainingEpisode],
) -> M1TrainingBatch:
    if not episodes:
        raise ValueError("M1_TRAINING_BATCH_EMPTY")
    batch_size = len(episodes)
    max_nodes = max(item.feature_sequence.shape[0] for item in episodes)
    feature_size = episodes[0].feature_sequence.shape[1]
    features = torch.zeros(batch_size, max_nodes, feature_size, dtype=torch.float32)
    valid = torch.zeros(batch_size, max_nodes, dtype=torch.bool)
    lengths = torch.zeros(batch_size, dtype=torch.long)
    targets = sorted({name for item in episodes for name in item.target_distributions})
    distributions: dict[str, torch.Tensor] = {}
    available: dict[str, torch.Tensor] = {}
    for target in targets:
        bin_counts = {
            item.target_distributions[target].shape[1]
            for item in episodes
            if target in item.target_distributions
        }
        if len(bin_counts) != 1:
            raise ValueError(f"M1_TRAINING_TARGET_BIN_MISMATCH:{target}")
        bins = next(iter(bin_counts))
        distributions[target] = torch.zeros(batch_size, max_nodes, bins)
        available[target] = torch.zeros(batch_size, max_nodes, dtype=torch.bool)
    for index, item in enumerate(episodes):
        nodes = item.feature_sequence.shape[0]
        features[index, :nodes] = item.feature_sequence
        valid[index, :nodes] = item.valid_node_mask.to(dtype=torch.bool)
        lengths[index] = int(item.valid_node_mask.sum())
        for target, values in item.target_distributions.items():
            distributions[target][index, :nodes] = values
            available[target][index, :nodes] = item.target_available_mask[target]
    return M1TrainingBatch(
        episode_ids=tuple(item.episode_id for item in episodes),
        feature_sequence=features,
        target_distributions=distributions,
        target_available_mask=available,
        valid_node_mask=valid,
        sequence_lengths=lengths,
        episode_weights=torch.tensor(
            [item.episode_weight for item in episodes], dtype=torch.float32
        ),
        partitions=tuple(item.partition for item in episodes),
    )
