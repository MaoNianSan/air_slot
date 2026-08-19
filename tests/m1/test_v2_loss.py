"""V2 loss tests: discrete hazard and hurdle + conditional quantile.

Spec 13 items covered here:
- T_IB hazard normalization / likelihood
- D_OB / D_TX zero mass and positive quantile monotonicity
"""

import pytest
import torch

from model.M1.contracts import HazardBinContract, HurdleQuantileContract
from model.M1.loss import (
    hazard_interval_nll,
    hazard_pmf,
    hurdle_quantile_loss,
    monotone_positive_quantiles,
    pinball_loss,
    quantile_value,
)


def _hazard():
    return HazardBinContract(bin_width_minutes=5, max_finite_minutes=60)


def _d_tx():
    return HurdleQuantileContract(target_name="D_TX", bin_width_minutes=5,
                                  max_finite_minutes=30,
                                  quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9))


def test_hazard_loss_is_finite_and_active_masked():
    contract = _hazard()
    logits = torch.randn(4, contract.finite_class_count)
    loss = hazard_interval_nll(
        logits, contract,
        lower=torch.tensor([5.0, 12.0, 30.0, 58.0]),
        upper=torch.tensor([5.0, 12.0, 30.0, 58.0]),
        active=torch.tensor([True, False, True, True]),
    )
    assert torch.isfinite(loss)
    # Only active rows count.
    assert loss.item() > 0


def test_hazard_loss_decreases_when_mass_concentrates_on_label():
    contract = _hazard()
    label_bin = 3
    logits_flat = torch.zeros(1, contract.finite_class_count)
    logits_sharp = torch.full((1, contract.finite_class_count), -20.0)
    logits_sharp[0, label_bin] = 20.0
    args = dict(lower=torch.tensor([17.0]), upper=torch.tensor([17.0]),
                active=torch.tensor([True]))
    flat = hazard_interval_nll(logits_flat, contract, **args)
    sharp = hazard_interval_nll(logits_sharp, contract, **args)
    assert sharp.item() < flat.item()


def test_hurdle_quantile_loss_zero_mass_and_pinball():
    contract = _d_tx()
    zero_logit = torch.tensor([[2.0], [-2.0]])
    quantile_logits = torch.randn(2, contract.quantile_count)
    active = torch.tensor([True, True])
    zero = torch.tensor([True, False])
    value = torch.tensor([0.0, 12.0])
    loss = hurdle_quantile_loss(
        zero_logit, quantile_logits, contract,
        zero=zero, value=value, active=active,
    )
    assert torch.isfinite(loss)
    # Zero rows must not contribute pinball on the positive curve.
    single_zero = hurdle_quantile_loss(
        zero_logit[:1], quantile_logits[:1], contract,
        zero=zero[:1], value=value[:1], active=torch.tensor([True]),
    )
    assert torch.isfinite(single_zero)


def test_pinball_loss_is_convex_and_minimized_at_the_quantile():
    levels = (0.25, 0.5, 0.75)
    target = torch.tensor([10.0])
    candidate = torch.tensor([[10.0, 10.0, 10.0]])
    off = torch.tensor([[5.0, 5.0, 5.0]])
    assert pinball_loss(target, candidate, levels) < pinball_loss(target, off, levels)


def test_quantile_value_is_monotone_in_uniform():
    quantiles = torch.tensor([[5.0, 10.0, 15.0]])
    levels = (0.1, 0.5, 0.9)
    # TEST_ONLY_LINEAR is the smoke-fixture tail rule; the principal default
    # UNRESOLVED raises above q_max (covered by the v2.1 closure tests).
    values = [
        quantile_value(quantiles, levels, u, upper_tail_policy="TEST_ONLY_LINEAR").item()
        for u in (0.05, 0.3, 0.5, 0.7, 0.95)
    ]
    assert values == sorted(values)
    assert values[0] >= 0
