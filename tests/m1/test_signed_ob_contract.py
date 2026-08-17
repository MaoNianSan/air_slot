from datetime import datetime, timezone

import pytest
import torch

from model.M1.contracts import AlignedScenario
from model.M1.pipeline import M1Pipeline
from model.M1.semantics import total_takeoff_delay_minutes
from model.M2.drivers import _scenario_value
from model.common.enums import SupportState


UTC = timezone.utc


def _scenario(*, delta_ob_minutes, tx_reference_minutes):
    return AlignedScenario(
        episode_id="e",
        decision_node_id="n",
        scenario_id=0,
        scenario_weight=1.0,
        operational_stage="POST_OB_PRE_TO",
        r_ib_minutes=10,
        delta_ob_minutes=delta_ob_minutes,
        t_tx_minutes=15,
        scheduled_ob_utc=datetime(2019, 1, 1, 12, tzinfo=UTC).isoformat(),
        tx_reference_minutes=tx_reference_minutes,
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


def test_signed_scenario_derives_r_ob_and_event_time_identities():
    scenario = _scenario(delta_ob_minutes=-10, tx_reference_minutes=12)
    assert scenario.r_ob_minutes == 0
    assert scenario.t_ob_utc == datetime(2019, 1, 1, 11, 50, tzinfo=UTC).isoformat()
    assert scenario.t_to_utc == datetime(2019, 1, 1, 12, 5, tzinfo=UTC).isoformat()
    assert scenario.d_to_minutes == 0
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=20, t_tx_minutes=15, taxi_reference_minutes=12
    ) == 23


def test_missing_train_frozen_taxi_reference_abstains_from_d_to():
    scenario = _scenario(delta_ob_minutes=20, tx_reference_minutes=None)
    assert scenario.d_to_minutes is None


def test_post_ob_stage_requires_and_preserves_observed_signed_delta():
    pipe = M1Pipeline.smoke(input_size=4)
    distributions = pipe.predict_distributions(torch.zeros(1, 2, 4), torch.tensor([2]))
    scenarios = pipe.sample_aligned(
        distributions,
        episode_id="e",
        decision_node_id="n",
        stage="POST_OB_PRE_TO",
        observed={"R_IB": 5, "DELTA_OB": -15},
        count=3,
        seed=7,
    )
    assert all(row.delta_ob_observed and row.delta_ob_minutes == -15 for row in scenarios)
    assert all(row.r_ob_minutes == 0 for row in scenarios)


def test_network_uses_unambiguous_delta_ob_head_and_m2_reads_derived_r_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    assert hasattr(pipe.model, "delta_ob_head")
    assert not hasattr(pipe.model, "ob_head")
    scenario = _scenario(delta_ob_minutes=25, tx_reference_minutes=12)
    assert _scenario_value(scenario.model_dump(), "r_ob_minutes") == (25, SupportState.SUPPORTED)


def test_aligned_scenario_rejects_independent_legacy_r_ob_input():
    with pytest.raises(Exception, match="Extra inputs"):
        AlignedScenario(
            episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=1,
            operational_stage="PRE_IB", r_ib_minutes=1, delta_ob_minutes=1, t_tx_minutes=1,
            scenario_seed_key="seed", r_ob_minutes=1,
        )
