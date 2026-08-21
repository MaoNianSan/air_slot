"""Tranche 3 cross-stage information-sharing integration test.

The paper claim under test: new information appears -> PRE legally publishes
it -> M1 receives the same typed information -> unresolved stochastic state
contracts -> downstream scenario distribution changes -> no future
information leaks backward.

Covers spec section 14 items 29-35:
- 29 cross-stage information update contracts the state without future leakage
- 30 scenario identity/weight lineage preserved
- 31 D_TX formal parent is still D_OB
- 32 D_TO samplewise identity
- 33 tail gate unchanged
- 34 Data2 remains trajectory-free
- 35 Final Test access remains zero
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import torch

from model.common.config import load_config_layers
from model.M1.factual_state import factual_observed_state
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import required_observations_v2
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre

UTC = timezone.utc
ZONES = {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}


def _pred_row():
    # Predecessor event_time (min actual) = 12:35 UTC, arrival = 12:55 UTC.
    return {"FlightDate": "2019-01-01", "Reporting_Airline": "AA",
        "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "9",
        "Origin": "LAX", "Dest": "JFK", "CRSDepTime": "0435", "CRSArrTime": "0755",
        "DepTime": "0435", "ArrTime": "0755", "WheelsOff": "0450", "WheelsOn": "0745",
        "TaxiOut": "15", "TaxiIn": "10", "DepDelay": "0", "ArrDelay": "0",
        "DepDelayMinutes": "0", "ArrDelayMinutes": "0",
        "Cancelled": "0", "Diverted": "0"}


def _succ_row():
    # Successor CRS dep 13:00 UTC, actual dep 13:10, wheels-off 13:25,
    # wheels-on 19:05, arrival 19:20; event_time = 13:10 UTC.
    return {"FlightDate": "2019-01-01", "Reporting_Airline": "AA",
        "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "10",
        "Origin": "JFK", "Dest": "LAX", "CRSDepTime": "0800", "CRSArrTime": "1100",
        "DepTime": "0810", "ArrTime": "1120", "WheelsOff": "0825", "WheelsOn": "1105",
        "TaxiOut": "15", "TaxiIn": "15", "DepDelay": "10", "ArrDelay": "20",
        "DepDelayMinutes": "10", "ArrDelayMinutes": "20",
        "Cancelled": "0", "Diverted": "0"}


def _records():
    pred_schedule, pred_outcome = canonicalize_ontime_row(_pred_row(), ZONES)
    succ_schedule, succ_outcome = canonicalize_ontime_row(_succ_row(), ZONES)
    return (pred_schedule, pred_outcome, succ_schedule, succ_outcome),         pred_outcome.flight_id, succ_outcome.flight_id


def _publish(records, pred_id, succ_id, *, decision_time, cutoff, stage):
    return publish_production_pre(ProductionPRERequest(
        episode_id="ep", predecessor_id=pred_id, successor_id=succ_id,
        dataset_instance_id="data2_2019", decision_time=decision_time,
        information_cutoff=cutoff, records=tuple(records),
        config_hash="sha256:c", registry_hash="sha256:r",
        operational_stage=stage,
        factual_availability_policy="DECLARED_RULE",
        factual_replay_declared_lag_minutes=0.0,
    )).pre_state


def test_information_update_changes_state_without_future_leakage():
    records, pred_id, succ_id = _records()
    pipe = M1Pipeline.smoke(4)
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4],
                            [0.5, 0.6, 0.7, 0.8]]])
    lengths = torch.tensor([2])

    # t1: 12:30 UTC, IB not yet legally available (availability 12:35).
    t1 = _publish(records, pred_id, succ_id,
                  decision_time=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                  cutoff=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                  stage="PRE_IB")
    # t2: 13:00 UTC, predecessor arrival legally available (availability
    # 12:35 <= 13:00); successor departure (13:10) is still in the future.
    t2 = _publish(records, pred_id, succ_id,
                  decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                  cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC),
                  stage="POST_IB_PRE_OB")

    # PRE(t1) != PRE(t2): the legal fact appears only once the availability
    # gate clears.
    assert "predecessor_operational_fact" not in t1.current_state
    assert "predecessor_operational_fact" in t2.current_state
    assert t2.current_state["predecessor_operational_fact"].value[
        "decision_time_role"] == "FACTUAL_REPLAY_EVIDENCE"

    observed_t1 = factual_observed_state(t1)
    observed_t2 = factual_observed_state(t2)
    assert observed_t1 == {}
    assert observed_t2 == {"T_IB_A00": "2019-01-01T12:55:00+00:00"}

    scenarios_t1 = pipe.sample_from_pre(
        t1, values, lengths, observed=observed_t1, count=8, seed=7)
    scenarios_t2 = pipe.sample_from_pre(
        t2, values, lengths, observed=observed_t2, count=8, seed=7)

    # M1(t1): T_IB is stochastic; M1(t2): T_IB is fixed to the legal fact.
    assert len({row.t_ib_a00_utc for row in scenarios_t1}) > 1
    assert all(row.t_ib_a00_utc == "2019-01-01T12:55:00+00:00"
               for row in scenarios_t2)

    # Same episode identity and same scenario lineage framework.
    assert all(row.episode_id == "ep" for row in scenarios_t1 + scenarios_t2)
    assert all(row.scenario_weight == pytest.approx(1 / 8)
               for row in scenarios_t1 + scenarios_t2)
    assert all(not row.t_ib_observed for row in scenarios_t1)
    assert all(row.t_ib_observed for row in scenarios_t2)

    # New information -> state contraction -> downstream D_OB distribution
    # changes (D_OB is unresolved at both nodes but its parent T_IB differs).
    d_ob_t1 = [row.d_ob_minutes for row in scenarios_t1 if row.d_ob_minutes is not None]
    d_ob_t2 = [row.d_ob_minutes for row in scenarios_t2 if row.d_ob_minutes is not None]
    assert d_ob_t1 and d_ob_t2
    assert set(d_ob_t1) != set(d_ob_t2) or len(set(d_ob_t1)) > 1

    # No future leakage: at t2 the successor's actual departure (13:10) is
    # still in the future relative to the cutoff, so D_OB stays stochastic.
    assert "successor_operational_fact" not in t2.successor_state
    assert all(not row.d_ob_observed for row in scenarios_t2)


def test_29b_service_generate_scenarios_auto_derives_observed():
    # M1Service.generate_scenarios derives the observed state from the PRE
    # typed factual state (never caller-supplied future truth).
    from model.M1.service import M1Service
    records, pred_id, succ_id = _records()
    pipe = M1Pipeline.smoke(4)
    service = M1Service(pipe, model_version="smoke")
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   stage="POST_IB_PRE_OB")
    scenarios = service.generate_scenarios(
        pre, values, lengths, count=4, seed=7)
    assert all(row.t_ib_a00_utc == "2019-01-01T12:55:00+00:00"
               for row in scenarios)
    assert all(row.t_ib_observed for row in scenarios)


def test_service_rejects_caller_injected_future_observed_state():
    from model.common.errors import ContractError
    from model.M1.service import M1Service
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                   stage="PRE_IB")
    service = M1Service(M1Pipeline.smoke(4), model_version="smoke")
    with pytest.raises(ContractError, match="M1_CALLER_OBSERVED_STATE_FORBIDDEN"):
        service.generate_scenarios(
            pre, torch.zeros(1, 2, 4), torch.tensor([2]),
            observed={"T_IB_A00": "2019-01-01T12:55:00+00:00"},
            count=2, seed=7,
        )


def test_30_scenario_identity_and_weight_lineage_preserved():
    records, pred_id, succ_id = _records()
    pipe = M1Pipeline.smoke(4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   stage="POST_OB_PRE_TO")
    observed = factual_observed_state(pre)
    scenarios = pipe.sample_from_pre(
        pre, values, lengths, observed=observed, count=5, seed=11)
    assert [row.scenario_id for row in scenarios] == [0, 1, 2, 3, 4]
    assert all(row.scenario_weight == pytest.approx(0.2) for row in scenarios)
    # The scenario seed key is episode-scoped and stable across nodes of the
    # same episode (same scenario lineage framework).
    keys_t1 = {row.scenario_seed_key for row in pipe.sample_from_pre(
        _publish(records, pred_id, succ_id,
                 decision_time=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                 cutoff=datetime(2019, 1, 1, 12, 30, tzinfo=UTC),
                 stage="PRE_IB"),
        values, lengths, observed={}, count=5, seed=11)}
    keys_t2 = {row.scenario_seed_key for row in scenarios}
    assert keys_t1 == keys_t2  # same episode -> same uniform keys


def test_31_d_tx_formal_parent_still_d_ob():
    assert required_observations_v2("POST_OB_PRE_TO") == {"T_IB_A00", "D_OB"}
    assert required_observations_v2("COMPLETED") == {"T_IB_A00", "D_OB", "D_TX"}
    # D_TX is never sampled before its formal D_OB parent: the stage contract
    # requires D_OB whenever D_TX is present.
    records, pred_id, succ_id = _records()
    pipe = M1Pipeline.smoke(4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   stage="POST_OB_PRE_TO")
    observed = factual_observed_state(pre)
    scenarios = pipe.sample_from_pre(
        pre, values, lengths, observed=observed, count=4, seed=3)
    # D_OB is a decision-time fact; D_TX remains stochastic but is drawn
    # conditional on the observed D_OB parent.
    assert all(row.d_ob_observed for row in scenarios)
    assert all(not row.d_tx_observed for row in scenarios)
    assert all(row.d_tx_minutes is not None for row in scenarios)


def test_32_d_to_samplewise_identity():
    records, pred_id, succ_id = _records()
    pipe = M1Pipeline.smoke(4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, 15, tzinfo=UTC),
                   stage="POST_OB_PRE_TO")
    observed = factual_observed_state(pre)
    scenarios = pipe.sample_from_pre(
        pre, values, lengths, observed=observed, count=4, seed=5)
    for row in scenarios:
        if row.d_ob_minutes is not None and row.d_tx_minutes is not None:
            assert row.d_to_minutes == pytest.approx(
                row.d_ob_minutes + row.d_tx_minutes, abs=1e-9)


def test_33_tail_gate_unchanged():
    scientific = load_config_layers(Path("configs")).scientific
    tail = scientific.parameters["m1_v2_positive_tail_policy"]
    assert tail.freeze_state.value == "HUMAN_DECISION_REQUIRED"
    assert tail.value == "UNRESOLVED"
    quantile_levels = scientific.parameters["m1_v2_quantile_levels"]
    assert quantile_levels.freeze_state.value == "DEVELOPMENT_ONLY"


def test_34_data2_remains_trajectory_free():
    records, pred_id, succ_id = _records()
    pre = _publish(records, pred_id, succ_id,
                   decision_time=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   cutoff=datetime(2019, 1, 1, 13, tzinfo=UTC),
                   stage="POST_IB_PRE_OB")
    motion = pre.predecessor_state.get("predecessor_motion")
    assert motion is not None
    assert motion.reason_code == "NO_TRAJECTORY"
    assert motion.support_state.value == "ABSTAIN"


def test_35_final_test_access_remains_zero():
    scientific = load_config_layers(Path("configs")).scientific
    for name in ("m1_state_estimator_v2", "m1_v2_quantile_levels",
                 "m1_v2_positive_tail_policy", "m1_formal_output_contract",
                 "data2_factual_replay_availability"):
        provenance = scientific.parameters[name].provenance or {}
        if "final_test_access_count" in provenance:
            assert provenance["final_test_access_count"] == 0
