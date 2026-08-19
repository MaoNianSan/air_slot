"""V2 contract tests: hazard support, hurdle-quantile support, scenario identity.

Spec 13 items covered here:
- T_IB hazard normalization / likelihood
- D_OB / D_TX zero mass and positive quantile monotonicity
- D_TO == D_OB + D_TX per scenario
- nonnegative D_* quantities
"""

from datetime import datetime, timezone

import pytest
import torch
from pydantic import ValidationError

from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1V2Scenario,
)
from model.M1.loss import (
    hazard_interval_nll,
    hazard_pmf,
    monotone_positive_quantiles,
)
from model.M1.semantics import derived_r_ib_minutes


UTC = timezone.utc


def _hazard(max_finite=60, width=5):
    return HazardBinContract(target_name="T_IB_REMAINING_HAZARD",
                             bin_width_minutes=width,
                             max_finite_minutes=max_finite)


def _d_ob():
    return HurdleQuantileContract(target_name="D_OB", bin_width_minutes=5,
                                  max_finite_minutes=60,
                                  quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9))


def test_hazard_contract_support_and_encoding():
    contract = _hazard()
    assert contract.finite_class_count == 12
    assert contract.class_count == 13
    assert contract.encode(0) == 0
    assert contract.encode(24) == 4
    assert contract.encode(60) == contract.overflow_index
    assert contract.representative(contract.overflow_index)[2] is True
    with pytest.raises(ValueError):
        contract.encode(-1)


def test_hazard_pmf_normalizes_for_arbitrary_logits():
    contract = _hazard()
    logits = torch.randn(4, contract.finite_class_count)
    pmf = hazard_pmf(logits, contract)
    assert pmf.shape == (4, contract.class_count)
    assert torch.allclose(pmf.sum(dim=-1), torch.ones(4), atol=1e-5)
    assert (pmf >= 0).all()


def test_hazard_interval_likelihood_matches_exact_bin_mass():
    contract = _hazard()
    logits = torch.zeros(1, contract.finite_class_count)
    pmf = hazard_pmf(logits, contract)
    # Bin 2 covers [10, 15): an exact label at 12 should get -log P(bin 2).
    loss = hazard_interval_nll(
        logits, contract,
        lower=torch.tensor([12.0]), upper=torch.tensor([12.0]),
        active=torch.tensor([True]),
    )
    assert loss.item() == pytest.approx(-float(torch.log(pmf[0, 2])), rel=1e-5)


def test_hurdle_quantile_contract_rejects_non_monotone_levels():
    with pytest.raises(ValidationError):
        HurdleQuantileContract(target_name="D_OB", bin_width_minutes=5,
                               max_finite_minutes=60,
                               quantile_levels=(0.5, 0.3, 0.9))
    with pytest.raises(ValidationError):
        HurdleQuantileContract(target_name="D_TX", bin_width_minutes=5,
                               max_finite_minutes=60, quantile_levels=(0.0, 0.9))
    with pytest.raises(ValidationError):
        HurdleQuantileContract(target_name="D_TX", bin_width_minutes=5,
                               max_finite_minutes=60, quantile_levels=())


def test_positive_quantiles_are_strictly_increasing_and_positive():
    logits = torch.randn(3, 5)
    quantiles = monotone_positive_quantiles(logits)
    assert (quantiles > 0).all()
    assert (torch.diff(quantiles, dim=-1) > 0).all()


def test_d_ob_zero_mass_and_positive_support_contract():
    contract = _d_ob()
    assert contract.encode(0) == 0
    assert contract.encode(59) == 11
    assert contract.encode(60) == contract.overflow_index
    assert contract.quantile_count == 5


def test_v2_scenario_d_to_identity_and_nonnegativity():
    decision = datetime(2019, 1, 1, 12, 0, tzinfo=UTC).isoformat()
    t_ib = datetime(2019, 1, 1, 12, 30, tzinfo=UTC).isoformat()
    scenario = M1V2Scenario(
        episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=0.5,
        operational_stage="PRE_IB", decision_time_utc=decision,
        t_ib_a00_utc=t_ib, d_ob_minutes=20.0, d_tx_minutes=10.0,
        t_ib_support="SUPPORTED", d_ob_support="SUPPORTED", d_tx_support="SUPPORTED",
        scenario_seed_key="seed",
    )
    assert scenario.r_ib_minutes == 30.0
    assert scenario.r_ib_minutes == pytest.approx(
        derived_r_ib_minutes(t_ib, decision))
    assert scenario.d_to_minutes == 30.0
    assert scenario.d_to_minutes == scenario.d_ob_minutes + scenario.d_tx_minutes
    assert scenario.d_to_support == "SUPPORTED"


def test_v2_scenario_rejects_negative_delays_and_d_to_mismatch():
    decision = datetime(2019, 1, 1, 12, 0, tzinfo=UTC).isoformat()
    base = dict(
        episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=1.0,
        operational_stage="PRE_IB", decision_time_utc=decision,
        t_ib_a00_utc=decision, d_ob_support="SUPPORTED", d_tx_support="SUPPORTED",
        scenario_seed_key="seed",
    )
    with pytest.raises(ValidationError):
        M1V2Scenario(**base, d_ob_minutes=-1.0, d_tx_minutes=5.0)
    with pytest.raises(ValidationError):
        M1V2Scenario(**base, d_ob_minutes=5.0, d_tx_minutes=-1.0)
    # D_TO is always derived; cannot be set independently.
    with pytest.raises(Exception):
        M1V2Scenario(**base, d_ob_minutes=5.0, d_tx_minutes=5.0, d_to_minutes=9.0)


def test_v2_scenario_abstains_from_d_to_when_any_component_absent():
    decision = datetime(2019, 1, 1, 12, 0, tzinfo=UTC).isoformat()
    scenario = M1V2Scenario(
        episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=1.0,
        operational_stage="PRE_IB", decision_time_utc=decision,
        t_ib_a00_utc=decision, d_ob_minutes=5.0, d_tx_minutes=None,
        d_ob_support="SUPPORTED", d_tx_support="ABSTAIN",
        scenario_seed_key="seed",
    )
    assert scenario.d_to_minutes is None
    assert scenario.d_to_support == "ABSTAIN"
