from __future__ import annotations

import torch

from .factories import build_untrained_test_model


def test_incremental_steps_match_full_sequence_final_state() -> None:
    model = build_untrained_test_model().eval()
    sequence = torch.tensor([[[1.0], [2.0], [3.0]]])
    full = model.forward_sequence(sequence)
    hidden = None
    for index in range(sequence.shape[1]):
        _, hidden = model.step(sequence[:, index : index + 1, :], hidden)
    torch.testing.assert_close(hidden, full.final_hidden)
