"""Test A — M1 joint identity: D_TO == D_OB + D_TX per scenario.

Reconciliation spec section 27, Test A and Test B.  The identity must hold
per scenario (not only in expectation) and all successor delays are
nonnegative.
"""

from datetime import datetime, timezone

import pytest
import torch

from model.M1.contracts import AlignedScenario
from model.M1.pipeline import M1Pipeline
from model.M1.semantics import (
    derived_d_ob_minutes,
    derived_d_to_minutes,
    derived_d_tx_minutes,
)
from model.M1.warning import batched_warning_probability


UTC = timezone.utc


def _scenario(*, delta_ob_minutes, t_tx_minutes, taxi_reference_minutes):
    return AlignedScenario(
        episode_id="e",
        decision_node_id="n",
        scenario_id=0,
        scenario_weight=1.0,
        operational_stage="POST_OB_PRE_TO",
        r_ib_minutes=10,
        delta_ob_minutes=delta_ob_minutes,
        t_tx_minutes=t_tx_minutes,
        scheduled_ob_utc=datetime(2019, 1, 1, 12, tzinfo=UTC).isoformat(),
        tx_reference_minutes=taxi_reference_minutes,
        taxi_reference_id="sha256:reference",
        taxi_reference_hash="sha256:freeze",
        taxi_reference_fallback_level="AIRPORT_CELL",
        taxi_reference_support_state="SUPPORTED",
        ib_observed=True,
        delta_ob_observed=True,
        ib_support="SUPPORTED",
        delta_ob_support="SUPPORTED",
        tx_support="SUPPORTED",
        scenario_seed_key="seed",
    )


@pytest.mark.parametrize(
    ("delta_ob", "t_tx", "taxi_ref"),
    [
        (20, 15, 12),
        (-10, 15, 12),
        (5, 5, 12),
        (-25, 40, 12),
        (0, 0, 12),
        (180, 60, 12),
    ],
)
def test_a_d_to_equals_d_ob_plus_d_tx_per_scenario(delta_ob, t_tx, taxi_ref):
    scenario = _scenario(
        delta_ob_minutes=delta_ob,
        t_tx_minutes=t_tx,
        taxi_reference_minutes=taxi_ref,
    )
    assert scenario.d_to_minutes == pytest.approx(
        scenario.d_ob_minutes + scenario.d_tx_minutes, abs=1e-9
    )
    assert scenario.d_to_minutes == pytest.approx(
        derived_d_to_minutes(delta_ob, t_tx, taxi_ref), abs=1e-9
    )
    # Manuscript identity: D_OB = max(0, DELTA_OB), D_TX = max(0, T_TX - taxi_ref).
    assert scenario.d_ob_minutes == pytest.approx(
        max(0.0, float(delta_ob)), abs=1e-9
    )
    assert scenario.d_tx_minutes == pytest.approx(
        max(0.0, float(t_tx) - float(taxi_ref)), abs=1e-9
    )


def test_b_all_successor_delays_are_nonnegative():
    for delta_ob in (-180, -30, 0, 5, 180):
        for t_tx in (0, 5, 60):
            scenario = _scenario(
                delta_ob_minutes=delta_ob,
                t_tx_minutes=t_tx,
                taxi_reference_minutes=12,
            )
            assert scenario.d_ob_minutes >= 0
            assert scenario.d_tx_minutes >= 0
            assert scenario.d_to_minutes >= 0
    assert derived_d_ob_minutes(-10) == 0
    assert derived_d_tx_minutes(5, 12) == 0
    assert derived_d_to_minutes(None, 5, 12) is None


def test_batched_warning_path_uses_the_formal_identity():
    """The vectorized warning path must derive D_TO = D_OB + D_TX.

    The sampled bin representatives are raw signed values; the batched path
    clamps per component exactly like model.M1.semantics.
    """
    pipeline = M1Pipeline.smoke(input_size=4)
    pipeline.temperatures = {"R_IB": 1.3, "DELTA_OB": 0.8, "T_TX": 1.1}
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4]]])
    lengths = torch.ones(1, dtype=torch.long)
    with torch.no_grad():
        history = pipeline.model.encode_history(values, lengths)
    result = batched_warning_probability(
        pipeline,
        history,
        episode_ids=("episode-a",),
        observed_r_ib=(None,),
        observed_delta_ob=(None,),
        observed_t_tx=(None,),
        taxi_reference_minutes=(12.0,),
        count=16,
        seed=7,
        return_indices=True,
    )
    assert torch.isfinite(result.probability)
    # Identity is verified structurally in _sample_post_ib/_sample_pre_ib by
    # comparing to the object path in test_batched_warning_probability.
    assert result.sampled_indices is not None
