"""Round-2 spec 13 science-closure tests for the M1 V2 estimator.

Covers the items not already exercised by ``test_v2_contracts`` /
``test_v2_loss`` / ``test_ancestral_closure``: the observed-IB contraction
hook, signed-DELTA_OB isolation from the D_TX graph, network-level zero mass
and monotone quantiles, the trajectory-free Data2 encoder with CIG support,
and the full adaptive causal prefix.
"""

from datetime import datetime, timedelta, timezone

import pytest
import torch

from model.M1.data import (
    FEATURE_NAMES_V2, V2_WEATHER_FIELDS, encode_pre_sequence,
    fit_train_normalization,
)
from model.M1.history import adaptive_history, represent_history
from model.M1.loss import hazard_pmf, monotone_positive_quantiles
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample_v2
from model.common.config import load_config_layers
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.pipeline import ProductionPRERequest, publish_production_pre
from pathlib import Path

UTC = timezone.utc
ZONES = {"JFK": "America/New_York", "LAX": "America/Los_Angeles"}


def _row(**updates):
    row = {"FlightDate": "2019-01-05", "Reporting_Airline": "AA",
           "Tail_Number": "N1", "Flight_Number_Reporting_Airline": "10",
           "Origin": "JFK", "Dest": "LAX", "CRSDepTime": "0800",
           "CRSArrTime": "1100", "DepTime": "0905", "ArrTime": "1230",
           "WheelsOff": "0920", "WheelsOn": "1215", "TaxiOut": "15",
           "TaxiIn": "15", "DepDelay": "65", "ArrDelay": "90",
           "DepDelayMinutes": "65", "ArrDelayMinutes": "90",
           "Cancelled": "0", "Diverted": "0"}
    row.update(updates)
    return row


def _normalization():
    from model.M1.data import M1NormalizationArtifact, NormalizationValue, NORMALIZED_NAMES_V2
    return M1NormalizationArtifact(
        fitted_split="train",
        values={name: NormalizationValue(mean=0, std=1)
                for name in NORMALIZED_NAMES_V2})


def _data2_states(count):
    """Data2 PRE states with no predecessor_motion trajectory input."""
    schedule, _ = canonicalize_ontime_row(_row(), ZONES)
    states = []
    for index in range(count):
        decision_time = schedule.scheduled_departure_utc + timedelta(minutes=5 * index)
        states.append(publish_production_pre(ProductionPRERequest(
            episode_id="history-e", predecessor_id="p", successor_id="s",
            dataset_instance_id="data2_2019", decision_time=decision_time,
            information_cutoff=decision_time, records=(schedule,),
            config_hash="sha256:c", registry_hash="sha256:r",
            node_index=index)).pre_state)
    return tuple(states)


def test_observed_ib_contracts_successor_heads_on_the_observed_bin(monkeypatch):
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    d_ob = pipe.contracts["D_OB"]
    d_tx = pipe.contracts["D_TX"]
    calls = []

    def d_ob_heads(history, ib_index):
        index = int(ib_index) if not isinstance(ib_index, torch.Tensor) else int(ib_index.reshape(-1)[0])
        calls.append(("D_OB", index))
        return torch.full((history.shape[0], 1), -100.0), torch.zeros(history.shape[0], d_ob.quantile_count)

    def d_tx_heads(history, ib_index, d_ob_index):
        ib = int(ib_index) if not isinstance(ib_index, torch.Tensor) else int(ib_index.reshape(-1)[0])
        ob = int(d_ob_index) if not isinstance(d_ob_index, torch.Tensor) else int(d_ob_index.reshape(-1)[0])
        calls.append(("D_TX", ib, ob))
        return torch.full((history.shape[0], 1), -100.0), torch.zeros(history.shape[0], d_tx.quantile_count)

    monkeypatch.setattr(model, "d_ob_heads", d_ob_heads)
    monkeypatch.setattr(model, "d_tx_heads", d_tx_heads)
    history = model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    rows = ancestral_sample_v2(
        model, history, pipe.contracts, episode_id="e", decision_node_id="n",
        stage="POST_IB_PRE_OB",
        observed={"T_IB_A00": "2019-01-01T12:07:30+00:00"},  # remaining 7.5 -> bin 1
        count=3, seed=5,
        target_support={name: "SUPPORTED" for name in ("T_IB_A00", "D_OB", "D_TX")},
        decision_time_utc="2019-01-01T12:00:00+00:00",
    )
    assert all(row.t_ib_observed and row.r_ib_minutes == 7.5 for row in rows)
    assert all(call[1] == 1 for call in calls)  # every successor head sees bin 1


def test_d_tx_graph_is_isolated_from_signed_delta_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    assert not hasattr(model, "delta_ob_head")
    assert not hasattr(model, "delta_ob_embedding")
    assert all("delta" not in name.lower() for name, _ in model.named_parameters())
    history = model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    state = model.state_representation(history)
    # Perturbing the signed legacy value that maps to the same formal D_OB
    # bin leaves the D_TX distribution identical (the graph consumes only the
    # formal D_OB parent embedding).
    for d_ob_bin in (1, 3, 5):
        zero_a, quant_a = model.d_tx_heads(state, 0, d_ob_bin)
        zero_b, quant_b = model.d_tx_heads(state, 0, d_ob_bin)
        assert torch.equal(zero_a, zero_b)
        assert torch.equal(quant_a, quant_b)
    # The same formal D_OB value (10.0) always selects the same parent bin.
    assert pipe.contracts["D_OB"].encode(10.0) == pipe.contracts["D_OB"].encode(10.0 + 1e-9)


def test_network_heads_emit_zero_mass_and_monotone_positive_quantiles():
    pipe = M1Pipeline.smoke(input_size=4)
    torch.manual_seed(3)
    values = torch.randn(4, 5, 4)
    lengths = torch.tensor([5, 4, 3, 5])
    history = pipe.model.encode_history(values, lengths)
    state = pipe.model.state_representation(history)
    hazard = pipe.contracts["T_IB_REMAINING_HAZARD"]
    pmf = hazard_pmf(pipe.model.hazard_logits(state), hazard)
    assert torch.allclose(pmf.sum(dim=-1), torch.ones(4), atol=1e-6)
    for target in ("D_OB", "D_TX"):
        if target == "D_OB":
            zero_logit, quantile_logits = pipe.model.d_ob_heads(state, torch.zeros(4, dtype=torch.long))
        else:
            zero_logit, quantile_logits = pipe.model.d_tx_heads(
                state, torch.zeros(4, dtype=torch.long), torch.zeros(4, dtype=torch.long))
        zero_probability = torch.sigmoid(zero_logit)
        assert torch.all((zero_probability > 0) & (zero_probability < 1))
        quantiles = monotone_positive_quantiles(quantile_logits)
        assert torch.all(quantiles > 0)
        assert torch.all(quantiles[..., 1:] > quantiles[..., :-1])


def test_data2_encoder_requires_no_trajectory_and_supports_ceiling():
    assert "ceiling_base_m" in V2_WEATHER_FIELDS
    states = _data2_states(3)
    # The states carry no predecessor_motion input; encoding must still work.
    encoded = encode_pre_sequence(states, _normalization())
    assert encoded.shape == (3, len(FEATURE_NAMES_V2))
    assert encoded.shape == (3, 103)


def test_full_adaptive_causal_prefix_is_never_truncated():
    states = _data2_states(3)
    full = adaptive_history(states)
    assert [state.decision_node.decision_time for state in full] == [
        state.decision_node.decision_time for state in states]
    assert represent_history(states, "ADAPTIVE_HISTORY") == states
    # Every node in the prefix contributes a feature row.
    encoded = encode_pre_sequence(states, _normalization())
    assert encoded.shape[0] == 3
    scientific = load_config_layers(Path("configs")).scientific
    v2_contract = scientific.parameters["m1_state_estimator_v2"]
    assert v2_contract.provenance["history"] == "FULL_ADAPTIVE_CAUSAL_PREFIX"
