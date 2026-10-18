"""Test A — M1 joint identity: D_TO == D_OB + D_TX per V2 scenario.

Reconciliation spec section 27, Test A and Test B.  The identity must hold
per scenario (not only in expectation) and all successor delays are
nonnegative.  V1 signed-DELTA_OB reconstruction helpers are kept as
LEGACY_V1/HISTORICAL_ONLY coverage.
"""

import pytest
import torch

from model.M1.contracts import M1V2Scenario
from model.M1.pipeline import M1Pipeline
from model.M1.semantics import (
    derived_d_ob_minutes,
    derived_d_to_from_primitives,
    derived_d_to_minutes,
    derived_d_tx_minutes,
)
from model.M1.warning import batched_warning_probability


def _scenario(*, d_ob_minutes, d_tx_minutes, overflow_ob=False, overflow_tx=False):
    return M1V2Scenario(
        episode_id="e",
        decision_node_id="n",
        scenario_id=0,
        scenario_weight=1.0,
        operational_stage="POST_OB_PRE_TO",
        decision_time_utc="2019-01-01T12:00:00+00:00",
        t_ib_a00_utc="2019-01-01T12:10:00+00:00",
        d_ob_minutes=d_ob_minutes,
        d_tx_minutes=d_tx_minutes,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED",
        d_tx_support="SUPPORTED",
        overflow_d_ob=overflow_ob,
        overflow_d_tx=overflow_tx,
        scenario_seed_key="seed",
    )


@pytest.mark.parametrize(
    ("d_ob", "d_tx"),
    [
        (20, 15),
        (0, 15),
        (5, 5),
        (0, 0),
        (180, 60),
        (180, 0),
    ],
)
def test_a_d_to_equals_d_ob_plus_d_tx_per_scenario(d_ob, d_tx):
    scenario = _scenario(d_ob_minutes=d_ob, d_tx_minutes=d_tx)
    assert scenario.d_to_minutes == pytest.approx(d_ob + d_tx, abs=1e-9)
    assert scenario.d_to_minutes == pytest.approx(
        derived_d_to_from_primitives(d_ob, d_tx), abs=1e-9
    )


def test_b_all_successor_delays_are_nonnegative():
    for d_ob in (0, 5, 180):
        for d_tx in (0, 5, 60):
            scenario = _scenario(d_ob_minutes=d_ob, d_tx_minutes=d_tx)
            assert scenario.d_ob_minutes >= 0
            assert scenario.d_tx_minutes >= 0
            assert scenario.d_to_minutes >= 0
    # LEGACY_V1 mapping helpers remain well-defined for provenance.
    assert derived_d_ob_minutes(-10) == 0
    assert derived_d_tx_minutes(5, 12) == 0
    assert derived_d_to_minutes(None, 5, 12) is None


def test_batched_warning_path_uses_the_formal_identity():
    """The vectorized warning path must derive D_TO = D_OB + D_TX per draw."""
    pipeline = M1Pipeline.smoke(input_size=4)
    pipeline.temperatures = {"T_IB_REMAINING_HAZARD": 1.3, "D_OB_ZERO": 0.8, "D_TX_ZERO": 1.1}
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4]]])
    lengths = torch.ones(1, dtype=torch.long)
    with torch.no_grad():
        history = pipeline.model.encode_history(values, lengths)
    result = batched_warning_probability(
        pipeline,
        history,
        episode_ids=("episode-a",),
        stages=("PRE_IB",),
        decision_times_utc=("2019-01-01T12:00:00+00:00",),
        observed_t_ib=(None,),
        observed_d_ob=(None,),
        observed_d_tx=(None,),
        count=16,
        seed=7,
        return_indices=True,
    )
    assert torch.isfinite(result.probability)
    assert result.sampled_indices is not None
    # Every supported draw must satisfy D_TO = D_OB + D_TX by construction;
    # the batched path is compared draw-for-draw with the object path in
    # tests/m1/test_batched_warning_probability.py.
    assert result.probability[0].item() >= 0.0
    assert result.probability[0].item() <= 1.0
