from __future__ import annotations

import pytest
import torch

from overall_run.src.m1.model import SingleLightweightGRU


@pytest.mark.parametrize("hidden_size", [8, 16])
def test_single_layer_gru_shapes_and_three_heads(hidden_size: int) -> None:
    model = SingleLightweightGRU(
        4, {"R_IB": 98, "R_OB": 12, "T_TX": 8}, hidden_size=hidden_size
    )
    logits, hidden = model(torch.zeros(3, 5, 4))
    assert model.gru.num_layers == 1
    assert model.gru.bidirectional is False
    assert set(logits) == {"R_IB", "R_OB", "T_TX"}
    assert logits["R_IB"].shape == (3, 98)
    assert hidden.shape == (1, 3, hidden_size)


def test_unsupported_hidden_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="M1_HIDDEN_SIZE_NOT_SUPPORTED"):
        SingleLightweightGRU(2, {"R_IB": 2}, hidden_size=32)
