from __future__ import annotations

import pytest
import torch

from overall_run.src.m1.model import SingleLightweightGRU


@pytest.mark.parametrize("hidden_size", [8, 16])
def test_full_sequence_keeps_node_logits(hidden_size: int) -> None:
    model = SingleLightweightGRU(
        4, {"R_IB": 98, "R_OB": 12, "T_TX": 8}, hidden_size=hidden_size
    )
    output = model.forward_sequence(torch.zeros(3, 5, 4))
    assert model.gru.num_layers == 1
    assert model.gru.bidirectional is False
    assert output.logits_by_target["R_IB"].shape == (3, 5, 98)
    assert output.hidden_by_node.shape == (3, 5, hidden_size)
    assert output.final_hidden.shape == (1, 3, hidden_size)


def test_incremental_step_rejects_more_than_one_node() -> None:
    model = SingleLightweightGRU(4, {"R_IB": 2})
    with pytest.raises(ValueError, match="M1_INCREMENTAL_STEP_REQUIRES_SINGLE_NODE"):
        model.step(torch.zeros(1, 2, 4), None)


def test_ambiguous_forward_interface_is_rejected() -> None:
    model = SingleLightweightGRU(4, {"R_IB": 2})
    with pytest.raises(RuntimeError, match="M1_EXPLICIT_FORWARD_INTERFACE_REQUIRED"):
        model(torch.zeros(1, 1, 4))


def test_unsupported_hidden_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="M1_HIDDEN_SIZE_NOT_SUPPORTED"):
        SingleLightweightGRU(2, {"R_IB": 2}, hidden_size=32)
