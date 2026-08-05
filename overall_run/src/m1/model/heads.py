from __future__ import annotations

from collections.abc import Mapping

import torch
from torch import nn


class DistributionHeads(nn.Module):
    def __init__(self, hidden_size: int, bin_counts: Mapping[str, int]) -> None:
        super().__init__()
        self.layers = nn.ModuleDict(
            {name: nn.Linear(hidden_size, int(count)) for name, count in bin_counts.items()}
        )

    def forward(self, hidden: torch.Tensor) -> dict[str, torch.Tensor]:
        return {name: layer(hidden) for name, layer in self.layers.items()}
