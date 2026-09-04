"""M1 empirical positive-tail continuation contract tests."""

from pathlib import Path

import pytest
import torch

from model.M1.contracts import HurdleQuantileContract
from model.M1.scenario_layer.sampler import _sample_hurdle_quantile_with_metadata
from model.M1.tail import (
    EmpiricalTailContinuation,
    MINIMUM_TAIL_OBSERVATIONS,
    load_tail_continuations,
)
from model.common.errors import ContractError


def _tail(target="D_TX"):
    return EmpiricalTailContinuation.from_exceedances(
        target=target,
        positive_values=torch.tensor([1.0] * 360 + [float(x) for x in range(2, 42)]).numpy(),
        fit_start="2019-01-01",
        fit_end="2019-06-30",
        source_hashes={"synthetic": "sha256:" + "0" * 64},
    )


def _contract(target="D_TX"):
    return HurdleQuantileContract(
        target_name=target,
        bin_width_minutes=5,
        max_finite_minutes=60,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )


def test_empirical_tail_has_minimum_support_and_no_extrapolation():
    continuation = _tail()
    assert continuation.tail_n >= MINIMUM_TAIL_OBSERVATIONS
    assert continuation.excess_at(0.0) == pytest.approx(0.0)
    assert continuation.excess_at(1.0) == pytest.approx(continuation.max_excess)
    assert continuation.excess_at(0.95) <= continuation.max_excess
    assert continuation.excess_at(0.2) <= continuation.excess_at(0.8)


def test_boundary_quantile_routes_finite_q90_and_empirical_tail():
    continuation = _tail()
    contract = _contract()
    zero_logit = torch.tensor([[-100.0]])
    quantile_logits = torch.log(torch.expm1(torch.tensor([[1., 2., 3., 4., 5.]])))

    def draw(positive_uniform):
        overall = positive_uniform
        return _sample_hurdle_quantile_with_metadata(
            zero_logit,
            quantile_logits,
            contract,
            overall,
            tail_continuation=continuation,
        )

    finite = draw(0.899999)
    at_q90 = draw(0.900000)
    tail = draw(0.900001)
    assert finite[3] is False
    assert at_q90[3] is False
    assert tail[3] is True
    assert tail[0] >= at_q90[0]
    assert tail[4] == continuation.tail_continuation_id
    assert tail[5] == continuation.tail_reference_hash


def test_explicit_scientific_tail_requires_continuation():
    with pytest.raises(ContractError, match="M1_POSITIVE_TAIL_CONTINUATION_REQUIRED"):
        _sample_hurdle_quantile_with_metadata(
            torch.tensor([[-100.0]]),
            torch.log(torch.expm1(torch.tensor([[1., 2., 3., 4., 5.]]))),
            _contract(),
            0.95,
            tail_continuation=None,
        )


def test_materialized_artifact_round_trips_target_payloads():
    path = Path("artifacts/diagnostics/m1_positive_tail_continuation_v1/M1_POSITIVE_TAIL_CONTINUATION_V1.json")
    loaded = load_tail_continuations(path)
    assert set(loaded) == {"D_OB", "D_TX"}
    assert loaded["D_OB"].fit_partition == "train"
    assert loaded["D_OB"].train_positive_q90 == pytest.approx(91.0)
    assert loaded["D_OB"].tail_n == 59
    assert loaded["D_TX"].train_positive_q90 == pytest.approx(14.0)
    assert loaded["D_TX"].tail_n == 55

