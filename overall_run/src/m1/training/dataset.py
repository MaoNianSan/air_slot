from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import torch
from torch.utils.data import Dataset


@dataclass(frozen=True)
class M1TrainingEpisode:
    episode_id: str
    feature_sequence: torch.Tensor
    target_distributions: Mapping[str, torch.Tensor]
    target_available_mask: Mapping[str, torch.Tensor]
    valid_node_mask: torch.Tensor
    episode_weight: float
    partition: str

    def __post_init__(self) -> None:
        if self.feature_sequence.ndim != 2:
            raise ValueError("M1_TRAINING_FEATURE_SEQUENCE_SHAPE_INVALID")
        node_count = self.feature_sequence.shape[0]
        if self.valid_node_mask.shape != (node_count,):
            raise ValueError("M1_TRAINING_VALID_MASK_SHAPE_INVALID")
        if self.episode_weight <= 0:
            raise ValueError("M1_TRAINING_EPISODE_WEIGHT_INVALID")
        if not self.partition:
            raise ValueError("M1_TRAINING_PARTITION_MISSING")
        for target, distribution in self.target_distributions.items():
            if distribution.ndim != 2 or distribution.shape[0] != node_count:
                raise ValueError(f"M1_TRAINING_TARGET_SHAPE_INVALID:{target}")
            mask = self.target_available_mask.get(target)
            if mask is None or mask.shape != (node_count,):
                raise ValueError(f"M1_TRAINING_TARGET_MASK_INVALID:{target}")


class M1EpisodeDataset(Dataset[M1TrainingEpisode]):
    def __init__(self, episodes: tuple[M1TrainingEpisode, ...]) -> None:
        if not episodes:
            raise ValueError("M1_TRAINING_DATASET_EMPTY")
        identities = {episode.episode_id: episode.partition for episode in episodes}
        if len(identities) != len(episodes):
            raise ValueError("M1_EPISODE_DUPLICATED_ACROSS_PARTITIONS")
        feature_sizes = {episode.feature_sequence.shape[1] for episode in episodes}
        if len(feature_sizes) != 1:
            raise ValueError("M1_TRAINING_FEATURE_DIMENSION_MISMATCH")
        self._episodes = episodes

    def __len__(self) -> int:
        return len(self._episodes)

    def __getitem__(self, index: int) -> M1TrainingEpisode:
        return self._episodes[index]
