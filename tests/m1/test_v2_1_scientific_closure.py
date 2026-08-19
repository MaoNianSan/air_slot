"""Round 2.1 M1 scientific-closure tests (spec section 11, tests A-R).

Covers:
- A/B upper-tail contract and CVaR gate
- C/E marginal-summary correctness (single sigmoid, no mislabeling)
- D scenario-derived marginal summary
- F/G static + recurrent representation closure
- H/I/J T_IB public-vs-internal coordinate separation
- K/L formal D_OB parent and D_TO identity
- M/N/O/P FAST V2 executable boundary
- Q/R history and Final-Test gates
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import torch
from pydantic import ValidationError

from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1V2Scenario,
    M1V2StaticContext,
    M1V2TargetLabel,
    M1_V2_HAZARD_COORDINATE,
    cvar_support_status,
    require_cvar_support,
)
from model.M1.data import FEATURE_NAMES_V2, V2_WEATHER_FIELDS, encode_pre_sequence
from model.M1.fast_path import LightGBMDistributionalPredictor
from model.M1.loss import (
    hazard_pmf,
    monotone_positive_quantiles,
    quantile_value,
)
from model.M1.network import M1V2GRU
from model.M1.pipeline import M1Pipeline, conditional_head_summary
from model.M1.scenarios import ancestral_sample_v2
from model.M1.semantics import (
    M1_V2_HAZARD_COORDINATE_TARGET,
    remaining_hazard_coordinate_minutes,
    t_ib_a00_from_remaining_minutes,
)
from model.M1.summaries import scenario_marginal_summary

UTC = timezone.utc


def _scenario(*, scenario_id=0, weight=1.0, d_ob=None, d_tx=None, t_ib=None,
              decision="2019-01-01T12:00:00+00:00"):
    return M1V2Scenario(
        episode_id="e",
        decision_node_id="n",
        scenario_id=scenario_id,
        scenario_weight=weight,
        operational_stage="PRE_IB",
        decision_time_utc=decision,
        t_ib_a00_utc=t_ib or "2019-01-01T12:30:00+00:00",
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED" if d_ob is not None else "ABSTAIN",
        d_tx_support="SUPPORTED" if d_tx is not None else "ABSTAIN",
        scenario_seed_key=f"seed-{scenario_id}",
    )


def _hazard_label(*, active, exact_minutes, t_ib_a00_utc, decision_time_utc,
                  label_status="EXACT"):
    return M1V2TargetLabel(
        target_name=M1_V2_HAZARD_COORDINATE_TARGET,
        active=active,
        exact_minutes=exact_minutes,
        support="SUPPORTED",
        episode_id="e",
        decision_node_id="n",
        target_definition_id="T_IB_REMAINING_HAZARD_V2",
        target_definition_version="2.0.0",
        label_status=label_status,
        provenance=(),
        split="train",
        episode_date=datetime(2019, 1, 1),
        t_ib_a00_utc=t_ib_a00_utc,
        decision_time_utc=decision_time_utc,
    )


def _fitted_fast(*, n_estimators=8):
    pipeline = M1Pipeline.smoke(input_size=4)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, 12))
    ib = np.abs(rng.normal(30.0, 15.0, size=64))
    d_ob = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=64)))
    d_tx = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=64)))
    predictor = LightGBMDistributionalPredictor(
        pipeline.contracts, feature_window=3)
    predictor.fit(X, {
        "T_IB_REMAINING_HAZARD": ib,
        "D_OB": d_ob,
        "D_TX": d_tx,
    }, seed=7, n_estimators=n_estimators)
    return pipeline, predictor


# ---------------------------------------------------------------------------
# A. quantile_value above q_max cannot silently clamp in the principal path
# ---------------------------------------------------------------------------

def test_a_quantile_value_above_q_max_raises_in_principal_path():
    quantiles = torch.tensor([[5.0, 10.0, 15.0]])
    levels = (0.1, 0.5, 0.9)
    # u == q_max is still the declared quantile; u > q_max must not clamp.
    assert quantile_value(quantiles, levels, 0.9).item() == pytest.approx(15.0)
    for u in (0.95, torch.tensor([0.95]), torch.tensor([[0.5, 0.95]])):
        with pytest.raises(ContractError, match="M1_QUANTILE_UPPER_TAIL_UNRESOLVED"):
            quantile_value(quantiles, levels, u)
    # TEST_ONLY_LINEAR extrapolates strictly above Q(q_max) (fixture only).
    tail = quantile_value(quantiles, levels, 0.95,
                          upper_tail_policy="TEST_ONLY_LINEAR")
    assert tail.item() > 15.0
    with pytest.raises(ContractError, match="M1_QUANTILE_UPPER_TAIL_RULE_NOT_IMPLEMENTED"):
        quantile_value(quantiles, levels, 0.95,
                       upper_tail_policy="DECLARED_FROZEN",
                       upper_tail_policy_reference="x")


# ---------------------------------------------------------------------------
# B. unresolved upper tail gates CVaR-dependent use
# ---------------------------------------------------------------------------

def test_b_unresolved_upper_tail_gates_cvar_use():
    contract = HurdleQuantileContract(
        target_name="D_OB", bin_width_minutes=5, max_finite_minutes=60,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
    )
    assert contract.q_max == pytest.approx(0.90)
    # alpha == q_max with an unresolved tail: Q(0.9) must not represent the
    # whole 90-100% tail.
    assert cvar_support_status(contract, 0.90) == "GATED"
    assert cvar_support_status(contract, 0.80) == "GATED"
    assert cvar_support_status(contract, 0.95) == "GATED"
    with pytest.raises(ContractError, match="M1_POSITIVE_TAIL_DECISION_REQUIRED"):
        require_cvar_support(contract, 0.90)
    # An explicit rule opens the gate (test-only fixture semantics).
    resolved = contract.model_copy(update={"upper_tail_policy": "TEST_ONLY_LINEAR"})
    assert cvar_support_status(resolved, 0.90) == "SUPPORTED"
    require_cvar_support(resolved, 0.90)


# ---------------------------------------------------------------------------
# C. zero probability transformed exactly once
# ---------------------------------------------------------------------------

def test_c_zero_probability_transformed_exactly_once():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    dist = pipe.predict_distributions(values, lengths)
    history = pipe.model.encode_history(values, lengths)
    state = pipe.model.state_representation(history)
    hazard = pipe.contracts[M1_V2_HAZARD_COORDINATE]
    with torch.no_grad():
        pmf = hazard_pmf(pipe.model.hazard_logits(state), hazard)
        manual = torch.zeros(1)
        for b in range(hazard.class_count):
            zero_logit, _ = pipe.model.d_ob_heads(
                state, torch.full((1,), b, dtype=torch.long))
            manual = manual + pmf[:, b] * torch.sigmoid(zero_logit.squeeze(-1))
    assert torch.allclose(dist["D_OB"]["zero_probability"], manual, atol=1e-6)
    assert torch.all((dist["D_OB"]["zero_probability"] > 0)
                     & (dist["D_OB"]["zero_probability"] < 1))
    # A second sigmoid would change the value; the emitted probability is
    # the single (already-sigmoid) transformation and nothing more.
    single = manual
    assert torch.allclose(dist["D_OB"]["zero_probability"], single, atol=1e-6)
    double = torch.sigmoid(single)
    assert not torch.allclose(
        dist["D_OB"]["zero_probability"], double, atol=1e-6)


# ---------------------------------------------------------------------------
# D. scenario-derived marginal summary matches the empirical weighted data
# ---------------------------------------------------------------------------

def test_d_scenario_marginal_summary_matches_empirical_weighted_scenarios():
    rows = (
        _scenario(scenario_id=0, weight=0.25, d_ob=10.0, d_tx=0.0),
        _scenario(scenario_id=1, weight=0.25, d_ob=20.0, d_tx=5.0),
        _scenario(scenario_id=2, weight=0.50, d_ob=40.0, d_tx=15.0),
    )
    summary = scenario_marginal_summary(rows, quantile_levels=(0.5,))
    assert summary["D_TO"]["summary_kind"] == "SCENARIO_MARGINAL_SUMMARY"
    assert summary["D_TO"]["support"] == "SUPPORTED"
    # D_TO = [10, 25, 55] with weights [0.25, 0.25, 0.5]; weighted median 25.
    assert summary["D_TO"]["quantiles_minutes"]["0.5"] == pytest.approx(25.0)
    assert summary["D_TO"]["mean_minutes"] == pytest.approx(
        0.25 * 10 + 0.25 * 25 + 0.5 * 55)
    assert summary["D_TX"]["zero_probability"] == pytest.approx(0.25)
    assert summary["D_OB"]["zero_probability"] == pytest.approx(0.0)
    # Explicit abstention is never silently dropped.
    incomplete = rows + (_scenario(scenario_id=3, weight=0.5, d_ob=None, d_tx=None),)
    assert scenario_marginal_summary(incomplete)["D_OB"]["support"] == "ABSTAIN"


# ---------------------------------------------------------------------------
# E. conditional quantile mixture is not mislabeled as marginal
# ---------------------------------------------------------------------------

def _logits_for_quantiles(values):
    increments = np.clip(np.diff([0.0] + list(values)), 1e-6, None)
    return torch.tensor(np.log(np.expm1(increments)), dtype=torch.float32)


def test_e_conditional_quantile_mixture_not_mislabeled_marginal(monkeypatch):
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    hazard = pipe.contracts[M1_V2_HAZARD_COORDINATE]
    wide = [10.0, 25.0, 40.0, 60.0, 70.0]
    narrow = [20.0, 21.0, 22.0, 23.0, 24.0]

    def hazard_logits(state):
        logits = torch.full((state.shape[0], hazard.finite_class_count), -30.0)
        logits[:, 0] = 0.0   # P(bin 0) = 0.5
        logits[:, 1] = 20.0  # P(bin 1) ~= 0.5
        return logits

    def d_ob_heads(state, ib_index):
        b = int(torch.as_tensor(ib_index).reshape(-1)[0])
        values = wide if b == 0 else narrow
        zero_logit = torch.full((state.shape[0], 1), -100.0)
        quantile_logits = _logits_for_quantiles(values).expand(state.shape[0], -1)
        return zero_logit, quantile_logits

    monkeypatch.setattr(model, "hazard_logits", hazard_logits)
    monkeypatch.setattr(model, "d_ob_heads", d_ob_heads)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    dist = pipe.predict_distributions(values, lengths)
    assert dist["D_OB"]["summary_kind"] == "CONDITIONAL_HEAD_SUMMARY"
    assert dist["D_OB"]["quantile_kind"] == "CONDITIONAL_MIXTURE_NOT_MARGINAL"
    assert dist["D_TX"]["quantile_kind"] == "CONDITIONAL_AT_EXPECTED_D_OB_BIN_NOT_MARGINAL"
    mixture_median = float(dist["D_OB"]["positive_quantiles_minutes"][0, 2])
    assert mixture_median == pytest.approx(0.5 * wide[2] + 0.5 * narrow[2])  # 31.0

    # Genuine marginal median from aligned scenarios differs from the mixture:
    # half the mass is a wide curve on [10,70], half is a narrow spike near 22.
    history = model.encode_history(values, lengths)
    scenarios = ancestral_sample_v2(
        model, history, pipe.contracts,
        episode_id="e", decision_node_id="n", stage="PRE_IB",
        observed={}, count=3000, seed=3,
        target_support={name: "SUPPORTED"
                        for name in ("T_IB_A00", "D_OB", "D_TX")},
        decision_time_utc="2019-01-01T12:00:00+00:00",
    )
    marginal = scenario_marginal_summary(scenarios, quantile_levels=(0.5,))
    marginal_median = marginal["D_OB"]["quantiles_minutes"]["0.5"]
    assert marginal_median < 28.0  # analytic marginal median ~23.1, not 31
    assert abs(marginal_median - 23.1) < abs(marginal_median - mixture_median)


# ---------------------------------------------------------------------------
# F. recurrent + supported static context reaches the common representation
# ---------------------------------------------------------------------------

def test_f_supported_static_context_reaches_common_heads():
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    history = model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    state_a = model.state_representation(history, torch.tensor([[0.0]]))
    state_b = model.state_representation(history, torch.tensor([[5.0]]))
    assert state_a.shape == (1, model.state_width)
    assert state_a.shape[1] == 2 * model.hidden_size
    assert not torch.allclose(state_a, state_b)
    recurrent, static = torch.split(state_a, model.hidden_size, dim=-1)
    assert torch.allclose(recurrent, history)
    assert not torch.allclose(static, torch.zeros_like(static))
    assert not torch.allclose(
        model.hazard_logits(state_a), model.hazard_logits(state_b))
    zero_a, _ = model.d_ob_heads(state_a, torch.tensor([0]))
    zero_b, _ = model.d_ob_heads(state_b, torch.tensor([0]))
    assert not torch.allclose(zero_a, zero_b)
    ctx = M1V2StaticContext()
    assert ctx.support("schedule.signed_minutes_to_crs_departure") == "SUPPORTED"


# ---------------------------------------------------------------------------
# G. unsupported static context remains ABSTAIN
# ---------------------------------------------------------------------------

def test_g_unsupported_static_context_remains_abstain():
    ctx = M1V2StaticContext()
    for field in ("route", "aircraft_identity", "carrier",
                  "turnaround_reference", "taxi_reference"):
        assert ctx.support(field) == "SUPPORT_ABSTAIN"
    for forbidden in ("live_aircraft_availability", "gate", "crew", "slot",
                      "standby_aircraft"):
        with pytest.raises(ValueError, match="M1_STATIC_CONTEXT_FORBIDDEN"):
            ctx.support(forbidden)
    # Without supported static features the static block is an explicit zero
    # representation (nothing is fabricated).
    pipe = M1Pipeline.smoke(input_size=4)
    history = pipe.model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    state = pipe.model.state_representation(history)
    assert torch.allclose(state[:, pipe.model.hidden_size:],
                          torch.zeros_like(history))
    # A model without a static encoder cannot accept static features.
    bare = M1V2GRU(4, 16, pipe.contracts[M1_V2_HAZARD_COORDINATE],
                   pipe.contracts["D_OB"], pipe.contracts["D_TX"])
    with pytest.raises(ValueError, match="M1_STATIC_PROJECTION_UNAVAILABLE"):
        bare.state_representation(history, torch.tensor([[0.0]]))


# ---------------------------------------------------------------------------
# H. Data2 still has no trajectory dependency
# ---------------------------------------------------------------------------

def test_h_data2_encoder_has_no_trajectory_dependency():
    assert not any("motion" in name for name in FEATURE_NAMES_V2)
    assert "ceiling_base_m" in V2_WEATHER_FIELDS


# ---------------------------------------------------------------------------
# I. public absolute T_IB distinct from internal remaining-time coordinate
# ---------------------------------------------------------------------------

def test_i_public_t_ib_distinct_from_internal_hazard_coordinate():
    decision = "2019-01-01T12:00:00+00:00"
    event = "2019-01-01T12:30:00+00:00"
    assert remaining_hazard_coordinate_minutes(event, decision) == 30.0
    assert t_ib_a00_from_remaining_minutes(decision, 30.0) == event
    hazard = HazardBinContract(bin_width_minutes=5, max_finite_minutes=60)
    assert hazard.target_name == "T_IB_REMAINING_HAZARD"
    # The public name is no longer a valid internal training-target name.
    with pytest.raises(ValidationError):
        HazardBinContract(target_name="T_IB_A00", bin_width_minutes=5,
                          max_finite_minutes=60)
    scenario = _scenario(d_ob=5.0, d_tx=5.0, t_ib=event)
    assert scenario.t_ib_a00_utc == event
    assert scenario.r_ib_minutes == 30.0
    label = _hazard_label(active=True, exact_minutes=30.0,
                          t_ib_a00_utc=event, decision_time_utc=decision)
    assert label.target_name == "T_IB_REMAINING_HAZARD"
    assert label.t_ib_a00_utc == event


# ---------------------------------------------------------------------------
# J. two past T_IB times both yield R_IB=0 without losing event time
# ---------------------------------------------------------------------------

def test_j_past_events_with_zero_remaining_stay_distinguishable():
    decision = "2019-01-01T12:00:00+00:00"
    event_a = "2019-01-01T11:30:00+00:00"
    event_b = "2019-01-01T10:15:00+00:00"
    for event in (event_a, event_b):
        assert remaining_hazard_coordinate_minutes(event, decision) == 0.0
    scenario_a = _scenario(d_ob=0.0, d_tx=0.0, t_ib=event_a)
    scenario_b = _scenario(d_ob=0.0, d_tx=0.0, t_ib=event_b)
    assert scenario_a.r_ib_minutes == 0.0
    assert scenario_b.r_ib_minutes == 0.0
    assert scenario_a.t_ib_a00_utc != scenario_b.t_ib_a00_utc
    # Label-level identity: inactive (already realized) hazard labels retain
    # their distinct public absolute event times.
    label_a = _hazard_label(active=False, exact_minutes=None,
                            t_ib_a00_utc=event_a, decision_time_utc=decision,
                            label_status="INACTIVE")
    label_b = _hazard_label(active=False, exact_minutes=None,
                            t_ib_a00_utc=event_b, decision_time_utc=decision,
                            label_status="INACTIVE")
    assert label_a.t_ib_a00_utc != label_b.t_ib_a00_utc
    # An active hazard label must remain consistent with its public identity.
    with pytest.raises(ValidationError):
        _hazard_label(active=True, exact_minutes=5.0,
                      t_ib_a00_utc=event_a, decision_time_utc=decision)


# ---------------------------------------------------------------------------
# K. D_TX still uses only formal D_OB
# ---------------------------------------------------------------------------

def test_k_d_tx_uses_only_formal_d_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    assert all("delta_ob" not in name.lower() for name, _ in model.named_parameters())
    state = model.state_representation(
        model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2])))
    zero_a, quant_a = model.d_tx_heads(state, 0, 2)
    zero_b, quant_b = model.d_tx_heads(state, 0, 2)
    assert torch.equal(zero_a, zero_b)
    assert torch.equal(quant_a, quant_b)
    assert pipe.contracts["D_OB"].encode(10.0) == pipe.contracts["D_OB"].encode(10.0 + 1e-9)


# ---------------------------------------------------------------------------
# L. D_TO identity still exact
# ---------------------------------------------------------------------------

def test_l_d_to_identity_still_exact():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.zeros(1, 2, 4)
    lengths = torch.tensor([2])
    scenarios = pipe.sample_from_pre(
        _pre_state("data2_2019"), values, lengths,
        observed={}, count=8, seed=7,
    )
    assert all(row.d_to_minutes is None
               or row.d_to_minutes == pytest.approx(row.d_ob_minutes + row.d_tx_minutes, abs=1e-9)
               for row in scenarios)


# ---------------------------------------------------------------------------
# M/N. FAST synthetic hazard + hurdle paths executable
# ---------------------------------------------------------------------------

def test_m_fast_synthetic_hazard_path_executable():
    pipeline, predictor = _fitted_fast()
    features = predictor._arx_features(torch.zeros(1, 6, 4))
    logits = predictor.hazard_logits(torch.tensor(features, dtype=torch.float32))
    hazard = pipeline.contracts[M1_V2_HAZARD_COORDINATE]
    assert logits.shape == (1, hazard.finite_class_count)
    pmf = hazard_pmf(logits, hazard)
    assert torch.allclose(pmf.sum(dim=-1), torch.ones(1), atol=1e-5)


def test_n_fast_synthetic_hurdle_path_executable():
    pipeline, predictor = _fitted_fast()
    features = torch.tensor(predictor._arx_features(torch.zeros(1, 6, 4)),
                            dtype=torch.float32)
    zero, quantile_logits = predictor.d_ob_heads(features, torch.tensor([0]))
    quantiles = monotone_positive_quantiles(quantile_logits)
    assert quantiles.shape == (1, 5)
    assert torch.all(quantiles > 0)
    assert torch.all(torch.diff(quantiles, dim=-1) > 0)
    zero_tx, quantile_tx = predictor.d_tx_heads(
        features, torch.tensor([0]), torch.tensor([0]))
    quantiles_tx = monotone_positive_quantiles(quantile_tx)
    assert quantiles_tx.shape == (1, 5)
    assert torch.all(quantiles_tx > 0)


# ---------------------------------------------------------------------------
# O. FAST and STATE_AWARE share the formal schema
# ---------------------------------------------------------------------------

def test_o_fast_and_state_aware_share_formal_schema():
    pipeline, predictor = _fitted_fast()
    values = torch.zeros(1, 6, 4)
    lengths = torch.tensor([6])
    state_dist = pipeline.predict_distributions(values, lengths)
    fast_dist = predictor.predict_development(values, lengths)
    assert set(state_dist) == set(fast_dist) == {"T_IB_A00", "D_OB", "D_TX"}
    assert set(fast_dist["D_OB"]) >= {"zero_probability", "positive_quantiles_minutes"}
    assert set(fast_dist["D_TX"]) >= {"zero_probability", "positive_quantiles_minutes"}
    assert fast_dist["D_OB"]["summary_kind"] == "CONDITIONAL_HEAD_SUMMARY"


# ---------------------------------------------------------------------------
# P. FAST without a train-frozen artifact still ABSTAIN
# ---------------------------------------------------------------------------

def test_p_fast_without_frozen_artifact_still_abstains():
    _, predictor = _fitted_fast()
    assert predictor.contract().final_test_access_count == 0
    with pytest.raises(ContractError, match="M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED"):
        predictor.predict_distributions(torch.zeros(1, 6, 4))


# ---------------------------------------------------------------------------
# Q. full causal history unchanged
# ---------------------------------------------------------------------------

def test_q_full_causal_history_unchanged():
    scientific = load_config_layers(Path("configs")).scientific
    assert scientific.parameters["m1_state_estimator_v2"].provenance[
        "history"] == "FULL_ADAPTIVE_CAUSAL_PREFIX"


# ---------------------------------------------------------------------------
# R. Final Test access remains zero
# ---------------------------------------------------------------------------

def test_r_final_test_access_remains_zero():
    scientific = load_config_layers(Path("configs")).scientific
    tail = scientific.parameters["m1_v2_positive_tail_policy"]
    assert tail.freeze_state.value == "HUMAN_DECISION_REQUIRED"
    assert tail.value == "UNRESOLVED"
    assert tail.provenance["human_gate"] == "M1_POSITIVE_TAIL_DECISION_REQUIRED"
    assert tail.provenance["selection_state"] == "NOT_FROZEN"
    quantile_levels = scientific.parameters["m1_v2_quantile_levels"]
    assert quantile_levels.freeze_state.value == "DEVELOPMENT_ONLY"
    for name in ("m1_state_estimator_v2", "m1_v2_quantile_levels",
                 "m1_v2_positive_tail_policy", "m1_formal_output_contract"):
        provenance = scientific.parameters[name].provenance or {}
        if "final_test_access_count" in provenance:
            assert provenance["final_test_access_count"] == 0


def _pre_state(dataset: str):
    from model.PRE.foundation import PREBuildRequest, build_pre_state
    return build_pre_state(PREBuildRequest(
        episode_id="episode-z", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=UTC),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=UTC),
        config_hash="sha256:c", registry_hash="sha256:r",
        dataset_instance_id=dataset,
    )).pre_state
