from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from .heads import DistributionHeads


@dataclass(frozen=True)
class M1SequenceOutput:
    logits_by_target: Mapping[str, torch.Tensor]
    hidden_by_node: torch.Tensor
    final_hidden: torch.Tensor


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
        self.bin_counts = {name: int(count) for name, count in bin_counts.items()}
        self.gru = nn.GRU(
            input_size=self.input_size,
            hidden_size=self.hidden_size,
            num_layers=1,
            batch_first=True,
            bidirectional=False,
            dropout=0.0,
        )
        self.heads = DistributionHeads(self.hidden_size, self.bin_counts)

    def zero_state(
        self,
        batch_size: int,
        device: torch.device | None = None,
    ) -> torch.Tensor:
        return torch.zeros(1, batch_size, self.hidden_size, device=device)

    def _validate_sequence(self, sequence: torch.Tensor) -> None:
        if sequence.ndim != 3 or sequence.shape[-1] != self.input_size:
            raise ValueError("M1_NETWORK_INPUT_SHAPE_INVALID")

    def forward_sequence(
        self,
        sequence: torch.Tensor,
        valid_mask: torch.Tensor | None = None,
        initial_hidden: torch.Tensor | None = None,
    ) -> M1SequenceOutput:
        self._validate_sequence(sequence)
        initial = (
            initial_hidden
            if initial_hidden is not None
            else self.zero_state(sequence.shape[0], sequence.device)
        )
        if valid_mask is None:
            hidden_by_node, final_hidden = self.gru(sequence, initial)
        else:
            if valid_mask.shape != sequence.shape[:2]:
                raise ValueError("M1_VALID_NODE_MASK_SHAPE_INVALID")
            mask = valid_mask.to(dtype=torch.bool)
            if ((~mask[:, :-1]) & mask[:, 1:]).any():
                raise ValueError("M1_VALID_NODE_MASK_NOT_LEFT_ALIGNED")
            lengths = mask.sum(dim=1)
            if (lengths <= 0).any():
                raise ValueError("M1_SEQUENCE_HAS_NO_VALID_NODE")
            packed = pack_padded_sequence(
                sequence,
                lengths.cpu(),
                batch_first=True,
                enforce_sorted=False,
            )
            packed_output, final_hidden = self.gru(packed, initial)
            hidden_by_node, _ = pad_packed_sequence(
                packed_output,
                batch_first=True,
                total_length=sequence.shape[1],
            )
        return M1SequenceOutput(
            logits_by_target=self.heads(hidden_by_node),
            hidden_by_node=hidden_by_node,
            final_hidden=final_hidden,
        )

    def step(
        self,
        snapshot_vector: torch.Tensor,
        previous_hidden: torch.Tensor | None,
    ) -> tuple[dict[str, torch.Tensor], torch.Tensor]:
        if snapshot_vector.ndim != 3 or snapshot_vector.shape[1] != 1:
            raise ValueError("M1_INCREMENTAL_STEP_REQUIRES_SINGLE_NODE")
        self._validate_sequence(snapshot_vector)
        initial = (
            previous_hidden
            if previous_hidden is not None
            else self.zero_state(snapshot_vector.shape[0], snapshot_vector.device)
        )
        hidden_by_node, final_hidden = self.gru(snapshot_vector, initial)
        return self.heads(hidden_by_node[:, 0, :]), final_hidden

    def forward(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("M1_EXPLICIT_FORWARD_INTERFACE_REQUIRED")
