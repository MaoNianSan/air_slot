"""M1 formal D_OB contract + LEGACY_V1 signed-scenario provenance.

The V2 principal estimator is T_IB_A00 -> D_OB -> D_TX with nonnegative
formal delays; signed DELTA_OB and the V1 ``AlignedScenario`` derived
quantities remain only as LEGACY_V1 / HISTORICAL_ONLY tests.
"""

from datetime import datetime, timezone

import pytest
import torch

from model.M1.contracts import AlignedScenario, M1V2Scenario
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample_v2
from model.M1.semantics import total_takeoff_delay_minutes
from model.M2.drivers import _scenario_value
from model.common.enums import SupportState
from model.common.errors import ContractError


UTC = timezone.utc


def _legacy_scenario(*, delta_ob_minutes, tx_reference_minutes):
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


def test_legacy_signed_scenario_derives_r_ob_and_event_time_identities():
    """HISTORICAL_ONLY: V1 signed DELTA_OB -> R_OB/D_TO reconstruction."""
    scenario = _legacy_scenario(delta_ob_minutes=-10, tx_reference_minutes=12)
    assert scenario.r_ob_minutes == 0
    assert scenario.d_ob_minutes == 0
    assert scenario.d_tx_minutes == 3
    assert scenario.d_to_minutes == 3
    assert scenario.d_to_minutes == scenario.d_ob_minutes + scenario.d_tx_minutes
    assert scenario.t_ob_utc == datetime(2019, 1, 1, 11, 50, tzinfo=UTC).isoformat()
    assert scenario.t_to_utc == datetime(2019, 1, 1, 12, 5, tzinfo=UTC).isoformat()
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=20, t_tx_minutes=15, taxi_reference_minutes=12
    ) == 23


def test_legacy_missing_train_frozen_taxi_reference_abstains_from_d_to():
    """HISTORICAL_ONLY: V1 warning dependency on the taxi reference."""
    scenario = _legacy_scenario(delta_ob_minutes=20, tx_reference_minutes=None)
    assert scenario.d_to_minutes is None


def test_post_ob_stage_requires_and_preserves_observed_formal_d_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    history = pipe.model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    support = {name: "SUPPORTED" for name in pipe.contracts}
    with pytest.raises(ContractError, match="M1_STAGE_OBSERVATION_MISSING"):
        ancestral_sample_v2(
            pipe.model, history, pipe.contracts, episode_id="e",
            decision_node_id="n", stage="POST_OB_PRE_TO",
            observed={"T_IB_A00": "2019-01-01T12:05:00+00:00"},
            count=3, seed=7, target_support=support,
            decision_time_utc="2019-01-01T12:00:00+00:00",
        )
    rows = ancestral_sample_v2(
        pipe.model, history, pipe.contracts, episode_id="e",
        decision_node_id="n", stage="POST_OB_PRE_TO",
        observed={"T_IB_A00": "2019-01-01T12:05:00+00:00", "D_OB": 15.0},
        count=3, seed=7, target_support=support,
        decision_time_utc="2019-01-01T12:00:00+00:00",
    )
    assert all(row.t_ib_observed and row.d_ob_observed for row in rows)
    assert all(row.d_ob_minutes == 15.0 for row in rows)
    assert all(row.d_ob_support == "SUPPORTED" for row in rows)


def test_network_uses_formal_d_ob_heads_and_m2_reads_formal_d_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    assert hasattr(pipe.model, "d_ob_heads")
    assert hasattr(pipe.model, "d_tx_heads")
    assert not hasattr(pipe.model, "delta_ob_head")
    assert not hasattr(pipe.model, "ob_head")
    scenario = M1V2Scenario(
        episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=1.0,
        operational_stage="POST_OB_PRE_TO",
        decision_time_utc="2019-01-01T12:00:00+00:00",
        t_ib_a00_utc="2019-01-01T12:10:00+00:00",
        d_ob_minutes=25, d_tx_minutes=3,
        t_ib_support="SUPPORTED", d_ob_support="SUPPORTED",
        d_tx_support="SUPPORTED", scenario_seed_key="seed",
    )
    dumped = scenario.model_dump()
    assert _scenario_value(dumped, "d_ob_minutes") == (25, SupportState.SUPPORTED)
    assert dumped["d_tx_minutes"] == 3
    assert dumped["d_to_minutes"] == 28


def test_aligned_scenario_rejects_independent_legacy_r_ob_input():
    with pytest.raises(Exception, match="Extra inputs"):
        AlignedScenario(
            episode_id="e", decision_node_id="n", scenario_id=0, scenario_weight=1,
            operational_stage="PRE_IB", r_ib_minutes=1, delta_ob_minutes=1, t_tx_minutes=1,
            scenario_seed_key="seed", r_ob_minutes=1,
        )
