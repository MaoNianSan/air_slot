from collections import Counter
from dataclasses import dataclass
import torch


@dataclass(frozen=True)
class M1SequenceBatch:
    values: torch.Tensor
    lengths: torch.Tensor
    episode_weights: torch.Tensor
    episode_ids: tuple[str, ...]


def episode_normalized_weights(episode_ids: list[str]) -> torch.Tensor:
    counts = Counter(episode_ids)
    return torch.tensor([1.0 / counts[item] for item in episode_ids], dtype=torch.float32)


def encode_supported_sequence(nodes: list[dict], feature_order: tuple[str, ...]) -> torch.Tensor:
    rows = []
    for node in nodes:
        values = []
        for feature in feature_order:
            item = node.get(feature)
            present = item is not None and item.get("support_state") != "ABSTAIN"
            values.extend([float(item.get("value", 0) or 0) if present else 0.0,
                           0.0 if present else 1.0, float(item.get("age_seconds", 0) or 0),
                           float(item.get("support_indicator", 0) or 0)])
        rows.append(values)
    return torch.tensor(rows, dtype=torch.float32)
