from __future__ import annotations

from collections.abc import Mapping

import torch
from torch import nn

from .heads import DistributionHeads


class SingleLightweightGRU(nn.Module):
    def __init__(
        self,
        input_size: int,
        bin_counts: Mapping[str, int],
        *,
        hidden_size: int = 8,
    ) -> None:
        super().__init__()
        if hidden_size not in {8, 16}:
            raise ValueError("M1_HIDDEN_SIZE_NOT_SUPPORTED")
        self.input_size = int(input_size)
        self.hidden_size = int(hidden_size)
        self.gru = nn.GRU(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_layers=1,
            batch_first=True,
            bidirectional=False,
            dropout=0.0,
        )
        self.heads = DistributionHeads(self.hidden_size, bin_counts)

    def zero_state(self, batch_size: int, device: torch.device | None = None) -> torch.Tensor:
        return torch.zeros(1, batch_size, self.hidden_size, device=device)

    def forward(
        self,
        sequence: torch.Tensor,
        hidden: torch.Tensor | None = None,
    ) -> tuple[dict[str, torch.Tensor], torch.Tensor]:
        if sequence.ndim != 3 or sequence.shape[-1] != self.input_size:
            raise ValueError("M1_NETWORK_INPUT_SHAPE_INVALID")
        initial = hidden if hidden is not None else self.zero_state(sequence.shape[0], sequence.device)
        output, next_hidden = self.gru(sequence, initial)
        logits = self.heads(output[:, -1, :])
        return logits, next_hidden
