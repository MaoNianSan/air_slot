"""Round 2.2 M1 contract-correction tests (spec section 10, tests A-X).

Covers:
- A-G  static/reference representation (no fake static duplicate; r_fast)
- H-L  FAST discrete-hazard risk-set semantics
- M-S  common calibration contract
- T-X  regressions (D_TX graph, D_TO identity, marginal, tail gate, T_IB)
"""

from datetime import datetime, timezone

import numpy as np
import pytest
import torch

from model.common.config import load_config_layers
from model.common.errors import ContractError
from model.M1.calibration import (
    COMMON_CALIBRATION_POLICY,
    M1CalibrationContract,
    common_calibration_policy,
    fit_hazard_temperature,
    fit_zero_mass_temperature,
    quantile_coverage_diagnostic,
    reject_multiclass_hazard_calibration,
    require_calibration_split,
    require_no_final_test,
)
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1StaticReferenceContext,
    M1V2Scenario,
    M1_V2_HAZARD_COORDINATE,
    M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE,
    cvar_support_status,
    require_cvar_support,
)
from model.M1.data import (
    FEATURE_NAMES_V2,
    V2_WEATHER_FIELDS,
    fast_features_from_sequence,
)
from model.M1.fast_path import (
    LightGBMDistributionalPredictor,
    M1FastPathStatus,
    _ConstantHazardSurrogate,
    _ConstantValuePredictor,
)
from model.M1.loss import hazard_interval_nll, hazard_pmf
from model.M1.network import M1V2GRU
from model.M1.pipeline import M1Pipeline
from model.M1.semantics import (
    M1_V2_HAZARD_COORDINATE_TARGET,
    remaining_hazard_coordinate_minutes,
    t_ib_a00_from_remaining_minutes,
)
from model.M1.summaries import scenario_marginal_summary

UTC = timezone.utc


def _hazard(max_finite=60, width=5):
    return HazardBinContract(bin_width_minutes=width, max_finite_minutes=max_finite)


def _d_ob():
    return HurdleQuantileContract(target_name="D_OB", bin_width_minutes=5,
                                  max_finite_minutes=60,
                                  quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
                                  upper_tail_policy="TEST_ONLY_LINEAR")


def _d_tx():
    return HurdleQuantileContract(target_name="D_TX", bin_width_minutes=5,
                                  max_finite_minutes=30,
                                  quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
                                  upper_tail_policy="TEST_ONLY_LINEAR")


def _scenario(*, scenario_id=0, weight=1.0, d_ob=None, d_tx=None, t_ib=None):
    return M1V2Scenario(
        episode_id="e", decision_node_id="n", scenario_id=scenario_id,
        scenario_weight=weight, operational_stage="PRE_IB",
        decision_time_utc="2019-01-01T12:00:00+00:00",
        t_ib_a00_utc=t_ib or "2019-01-01T12:30:00+00:00",
        d_ob_minutes=d_ob, d_tx_minutes=d_tx,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED" if d_ob is not None else "ABSTAIN",
        d_tx_support="SUPPORTED" if d_tx is not None else "ABSTAIN",
        scenario_seed_key=f"seed-{scenario_id}",
    )


# ---------------------------------------------------------------------------
# A. schedule countdown is NOT a fake static duplicate anymore
# ---------------------------------------------------------------------------

def test_a_schedule_countdown_not_duplicated_as_static():
    # The countdown is a DYNAMIC current-AR variable; it is not a
    # static/reference field in the typed contract.
    assert "schedule.signed_minutes_to_crs_departure" not in         M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE
    ctx = M1StaticReferenceContext()
    assert ctx.static_context_status == "STATIC_REFERENCE_CONTEXT_PENDING_PRE"
    # The recurrent model has no static branch at all.
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    assert not hasattr(model, "static_encoder")
    assert not hasattr(model, "static_input_size")
    # r_fast is the last causal row (the countdown enters exactly once, as a
    # dynamic row feature inside the current/AR block).
    values = torch.arange(8, dtype=torch.float32).reshape(1, 2, 4)
    fast = fast_features_from_sequence(values, torch.tensor([2]))
    assert torch.equal(fast, values[:, 1:2, :].squeeze(1))


# ---------------------------------------------------------------------------
# B. current/AR block independently forms r_fast
# ---------------------------------------------------------------------------

def test_b_current_ar_block_forms_r_fast():
    values = torch.tensor([[[0.0, 0.0, 0.0, 0.0],
                            [1.0, 2.0, 3.0, 4.0]]])
    fast = fast_features_from_sequence(values, torch.tensor([2]))
    assert fast.shape == (1, 4)
    assert torch.equal(fast, torch.tensor([[1.0, 2.0, 3.0, 4.0]]))
    # Deterministic: same input, same block.
    assert torch.equal(fast_features_from_sequence(values, torch.tensor([2])), fast)
    # Different last rows give different blocks.
    other = torch.tensor([[[0.0, 0.0, 0.0, 0.0],
                           [5.0, 6.0, 7.0, 8.0]]])
    assert not torch.equal(fast_features_from_sequence(other, torch.tensor([2])), fast)


# ---------------------------------------------------------------------------
# C. GRU history + r_fast both reach STATE_AWARE heads
# ---------------------------------------------------------------------------

def test_c_gru_history_plus_r_fast_reach_state_aware_heads():
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    history = model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    fast_a = torch.tensor([[0.0, 0.0, 0.0, 0.0]])
    fast_b = torch.tensor([[1.0, -1.0, 2.0, 0.5]])
    state_a = model.state_representation(history, fast_a)
    state_b = model.state_representation(history, fast_b)
    assert state_a.shape == (1, 2 * model.hidden_size)
    recurrent, fast = torch.split(state_a, model.hidden_size, dim=-1)
    assert torch.allclose(recurrent, history)  # recurrent block preserved
    assert not torch.allclose(fast, torch.zeros_like(fast))  # fast block active
    assert not torch.allclose(
        model.hazard_logits(state_a), model.hazard_logits(state_b))
    zero_a, _ = model.d_ob_heads(state_a, torch.tensor([0]))
    zero_b, _ = model.d_ob_heads(state_b, torch.tensor([0]))
    assert not torch.allclose(zero_a, zero_b)


# ---------------------------------------------------------------------------
# D. FAST never consumes the GRU recurrent hidden state
# ---------------------------------------------------------------------------

def test_d_fast_does_not_use_gru_hidden():
    pipe = M1Pipeline.smoke(input_size=4)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, 4))
    ib = np.abs(rng.normal(30.0, 15.0, size=64))
    d_ob = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=64)))
    d_tx = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=64)))
    predictor = LightGBMDistributionalPredictor(pipe.contracts)
    predictor.fit(X, {
        M1_V2_HAZARD_COORDINATE_TARGET: ib, "D_OB": d_ob, "D_TX": d_tx,
    }, seed=7, n_estimators=8, allow_test_only_surrogate=True)
    assert not hasattr(predictor, "gru")
    assert not hasattr(predictor, "encode_history")
    features = torch.tensor([[0.1, 0.2, 0.3, 0.4]])
    assert predictor.state_representation(features) is features


# ---------------------------------------------------------------------------
# E. static/reference absent is never fabricated
# ---------------------------------------------------------------------------

def test_e_static_reference_absent_not_fabricated():
    pipe = M1Pipeline.smoke(input_size=4)
    history = pipe.model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2]))
    state = pipe.model.state_representation(history)  # no fast block given
    assert torch.allclose(state[:, pipe.model.hidden_size:],
                          torch.zeros_like(history))
    # With a fast block, only current/AR features enter (no static).
    fast = torch.tensor([[0.5, 0.5, 0.5, 0.5]])
    state_with_fast = pipe.model.state_representation(history, fast)
    assert not torch.allclose(state_with_fast, state)


# ---------------------------------------------------------------------------
# F. available-but-not-published fields marked upstream-required
# ---------------------------------------------------------------------------

def test_f_available_but_not_published_marked_upstream_required():
    ctx = M1StaticReferenceContext()
    assert set(M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE) == {
        "route_context", "carrier_context", "aircraft_identity",
        "schedule_reference_context", "turnaround_reference", "taxi_reference",
    }
    # PRE already carries reference objects but has not published them to M1.
    for field in ("aircraft_identity", "schedule_reference_context",
                  "turnaround_reference", "taxi_reference"):
        assert ctx.pre_status(field) == "AVAILABLE_BUT_NOT_PUBLISHED_TO_M1"
        assert ctx.support(field) == "UPSTREAM_PRE_INTERFACE_REQUIRED"
    # Fields with no stable canonical path need a PRE reference binding.
    for field in ("route_context", "carrier_context"):
        assert ctx.pre_status(field) == "NEEDS_PRE_REFERENCE_BINDING"
    # M1 must not bypass PRE by reading raw files for any field.
    for field in M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE:
        field_obj = getattr(ctx, field)
        assert field_obj.provenance_reference_id is None
        assert field_obj.freeze_id is None


# ---------------------------------------------------------------------------
# G. trajectory still not a Data2 requirement
# ---------------------------------------------------------------------------

def test_g_trajectory_still_not_data2_requirement():
    assert not any("motion" in name for name in FEATURE_NAMES_V2)
    assert "ceiling_base_m" in V2_WEATHER_FIELDS


# ---------------------------------------------------------------------------
# H/I/J. FAST hazard per-bin risk sets
# ---------------------------------------------------------------------------

def test_h_each_hazard_bin_uses_its_risk_set():
    # rows: bin 0 events (2,3), bin 1 event (7), bin 2 event (11), tail (70)
    ib_values = [2.0, 3.0, 7.0, 11.0, 70.0, 40.0, 22.0, 55.0]
    hazard = _hazard(max_finite=60, width=5)
    contracts = {M1_V2_HAZARD_COORDINATE_TARGET: hazard,
                 "D_OB": _d_ob(), "D_TX": _d_tx()}
    predictor = LightGBMDistributionalPredictor(contracts)
    sizes = predictor.hazard_risk_set_sizes(ib_values)
    assert sizes[0] == 8                     # everyone is at risk at t=0
    assert sizes[1] == 6                     # 2,3 happened before bin 1
    assert sizes[2] == 5                     # 2,3,7 happened before bin 2
    assert sizes[3] == 4                     # 2,3,7,11 happened before bin 3
    assert sizes[hazard.finite_class_count - 1] == 2  # 55 and 70 at risk


def test_i_earlier_events_excluded_from_later_risk_sets():
    # Events in bin 0 (2,3), bin 1 (7), bin 2 (11): a later-bin model must
    # never see rows whose event already happened.
    hazard = _hazard(max_finite=60, width=5)
    contracts = {M1_V2_HAZARD_COORDINATE_TARGET: hazard,
                 "D_OB": _d_ob(), "D_TX": _d_tx()}
    predictor = LightGBMDistributionalPredictor(contracts)
    sizes = predictor.hazard_risk_set_sizes([2.0, 3.0, 7.0, 11.0])
    assert sizes[0] == 4                     # all rows at risk for bin 0
    assert sizes[1] == 2                     # bin-0 events excluded
    assert sizes[2] == 1                     # bins 0,1 events excluded
    assert sizes[3] == 0                     # only bin-2 event remains, gone
    assert all(sizes[k] <= sizes[k - 1] for k in range(1, len(sizes)))


def test_j_tail_observations_remain_at_risk_in_all_finite_sets():
    hazard = _hazard(max_finite=60, width=5)
    contracts = {M1_V2_HAZARD_COORDINATE_TARGET: hazard,
                 "D_OB": _d_ob(), "D_TX": _d_tx()}
    predictor = LightGBMDistributionalPredictor(contracts)
    values = np.asarray([2.0, 3.0, 7.0, 70.0])
    sizes = predictor.hazard_risk_set_sizes(values)
    # The 70-minute row (>= max_finite) is at risk in EVERY finite bin.
    assert all(size >= 1 for size in sizes)
    tail_row = np.where(values >= 60.0)[0][0]
    # It never contributes a finite-bin event (no event rows beyond max_finite).
    finite_events = 0
    for k in range(hazard.finite_class_count):
        start = k * hazard.bin_width_minutes
        event = (values >= start) & (values < start + hazard.bin_width_minutes)
        assert not bool(event[tail_row])
        finite_events += int(event.sum())
    assert finite_events == 3  # bins 0,1,2 events only


def test_k_fast_hazard_pmf_sums_to_one():
    hazard = _hazard(max_finite=60, width=5)
    contracts = {M1_V2_HAZARD_COORDINATE_TARGET: hazard,
                 "D_OB": _d_ob(), "D_TX": _d_tx()}
    rng = np.random.default_rng(1)
    X = rng.normal(size=(8, 4))
    ib = np.asarray([2.0, 3.0, 7.0, 11.0, 70.0, 40.0, 22.0, 55.0])
    d_ob = np.where(rng.random(8) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=8)))
    d_tx = np.where(rng.random(8) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=8)))
    predictor = LightGBMDistributionalPredictor(contracts)
    predictor.fit(X, {
        M1_V2_HAZARD_COORDINATE_TARGET: ib, "D_OB": d_ob, "D_TX": d_tx,
    }, seed=7, n_estimators=8, allow_test_only_surrogate=True)
    logits = predictor.hazard_logits(torch.tensor(X[:1], dtype=torch.float32))
    pmf = hazard_pmf(logits, hazard)
    assert torch.allclose(pmf.sum(dim=-1), torch.ones(1), atol=1e-5)
    assert pmf.shape == (1, hazard.class_count)


# ---------------------------------------------------------------------------
# L. hand-computed discrete-hazard example matches code
# ---------------------------------------------------------------------------

def test_l_hand_computed_discrete_hazard_matches_code():
    hazard = _hazard(max_finite=10, width=5)  # two finite bins + tail
    contracts = {M1_V2_HAZARD_COORDINATE_TARGET: hazard,
                 "D_OB": _d_ob(), "D_TX": _d_tx()}
    models = {
        M1_V2_HAZARD_COORDINATE_TARGET: {
            "hazard_models": [_ConstantHazardSurrogate(0.5),
                              _ConstantHazardSurrogate(0.25)],
            "risk_set_sizes": [2, 1],
            "test_only_surrogates": [],
        },
        "D_OB": {"zero": _ConstantHazardSurrogate(0.5),
                 "quantiles": [_ConstantValuePredictor(1.0)] * 5},
        "D_TX": {"zero": _ConstantHazardSurrogate(0.5),
                 "quantiles": [_ConstantValuePredictor(1.0)] * 5},
    }
    predictor = LightGBMDistributionalPredictor(contracts, models=models)
    state = torch.zeros(1, 4)
    logits = predictor.hazard_logits(state)
    pmf = hazard_pmf(logits, hazard)
    # h0=0.5, h1=0.25:
    #   pmf0 = 0.5
    #   pmf1 = 0.25 * (1-0.5) = 0.125
    #   tail = (1-0.5)*(1-0.25) = 0.375
    assert pmf[0, 0].item() == pytest.approx(0.5, abs=1e-6)
    assert pmf[0, 1].item() == pytest.approx(0.125, abs=1e-6)
    assert pmf[0, 2].item() == pytest.approx(0.375, abs=1e-6)
    assert pmf.sum(dim=-1).item() == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# M. old multiclass temperature calibration rejected for hazard
# ---------------------------------------------------------------------------

def test_m_multiclass_calibration_rejected_for_hazard():
    with pytest.raises(ContractError, match="M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN"):
        reject_multiclass_hazard_calibration()
    import model.M1.calibration as calibration_module
    assert not hasattr(calibration_module, "fit_temperature")


# ---------------------------------------------------------------------------
# N. hazard temperature uses the induced event-time likelihood
# ---------------------------------------------------------------------------

def test_n_hazard_temperature_uses_event_time_likelihood():
    hazard = _hazard(max_finite=60, width=5)
    rng = np.random.default_rng(3)
    logits = torch.tensor(rng.normal(size=(32, hazard.finite_class_count)),
                          dtype=torch.float32)
    remaining = np.abs(rng.normal(30.0, 15.0, size=32))
    labels = torch.tensor([min(int(v // 5), hazard.finite_class_count - 1)
                           for v in remaining], dtype=torch.long)
    active = torch.ones(32, dtype=torch.bool)
    temperature = fit_hazard_temperature(logits, labels, active, hazard)
    assert 0.05 <= temperature <= 20.0
    lower = torch.tensor([hazard.bin_start(int(b)) for b in labels],
                         dtype=torch.float32)
    upper = torch.tensor([hazard.bin_end(int(b)) for b in labels],
                         dtype=torch.float32)
    nll_before = hazard_interval_nll(logits, hazard, lower=lower, upper=upper,
                                     active=active)
    nll_after = hazard_interval_nll(
        logits / temperature, hazard, lower=lower, upper=upper, active=active)
    assert nll_after <= nll_before + 1e-6


# ---------------------------------------------------------------------------
# O/P. calibration split only; no test access
# ---------------------------------------------------------------------------

def test_o_calibration_limited_to_calibration_split():
    with pytest.raises(ContractError, match="M1_CALIBRATION_SPLIT_FORBIDDEN"):
        require_calibration_split("train")
    with pytest.raises(ContractError, match="M1_CALIBRATION_SPLIT_FORBIDDEN"):
        require_calibration_split("test")
    require_calibration_split("calibration")  # no raise
    hazard = _hazard()
    logits = torch.zeros(4, hazard.finite_class_count)
    labels = torch.zeros(4, dtype=torch.long)
    active = torch.ones(4, dtype=torch.bool)
    with pytest.raises(ContractError, match="M1_CALIBRATION_SPLIT_FORBIDDEN"):
        fit_hazard_temperature(logits, labels, active, hazard, split="test")


def test_p_no_final_test_access():
    require_no_final_test(0)
    with pytest.raises(ContractError,
                       match="M1_CALIBRATION_FINAL_TEST_ACCESS_FORBIDDEN"):
        require_no_final_test(1)
    assert COMMON_CALIBRATION_POLICY.final_test_access_count == 0


# ---------------------------------------------------------------------------
# Q. hurdle zero-mass calibration discipline exists
# ---------------------------------------------------------------------------

def test_q_hurdle_zero_mass_calibration_discipline_exists():
    contract = M1CalibrationContract()
    assert contract.successor_zero_mass_calibration ==         "HURDLE_ZERO_BINARY_CE_TEMPERATURE"
    logits = torch.tensor([0.5, -2.0, 3.0, 0.0], dtype=torch.float32)
    labels = torch.tensor([1.0, 0.0, 1.0, 0.0], dtype=torch.float32)
    active = torch.ones(4, dtype=torch.bool)
    temperature = fit_zero_mass_temperature(logits, labels, active)
    assert 0.05 <= temperature <= 20.0


# ---------------------------------------------------------------------------
# R. FAST and STATE_AWARE share the same calibration policy
# ---------------------------------------------------------------------------

def test_r_fast_and_state_aware_share_calibration_policy():
    pipe = M1Pipeline.smoke(input_size=4)
    policy = pipe.calibration_policy()
    assert policy is common_calibration_policy()
    assert policy.version == "M1_CALIBRATION_CONTRACT_V1"
    predictor = LightGBMDistributionalPredictor(pipe.contracts)
    assert predictor.contract().calibration_version == policy.version
    assert predictor.contract().target_semantics ==         "T_IB_A00_D_OB_D_TX_HAZARD_HURDLE_QUANTILE_CONTRACTS"
    scientific = load_config_layers(__import__("pathlib").Path("configs")).scientific
    param = scientific.parameters["m1_v2_calibration_contract"]
    assert param.value == policy.version
    assert param.provenance["split"] == "calibration"
    assert param.provenance["final_test_access_count"] == 0


# ---------------------------------------------------------------------------
# S. quantile calibration status explicit, not silently claimed
# ---------------------------------------------------------------------------

def test_s_quantile_calibration_status_explicit():
    policy = common_calibration_policy()
    assert policy.positive_quantile_calibration == "QUANTILE_CALIBRATION_NOT_APPLIED"
    predicted = torch.tensor([[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]])
    actual = torch.tensor([2.5, 0.5], dtype=torch.float32)
    active = torch.ones(2, dtype=torch.bool)
    coverage = quantile_coverage_diagnostic(
        predicted, actual, (0.1, 0.5, 0.9), active)
    assert set(coverage) == {"0.1", "0.5", "0.9"}
    with pytest.raises(ContractError, match="M1_CALIBRATION_SPLIT_FORBIDDEN"):
        quantile_coverage_diagnostic(predicted, actual, (0.5,), active,
                                     split="development")


# ---------------------------------------------------------------------------
# T. D_TX still conditions only on formal D_OB
# ---------------------------------------------------------------------------

def test_t_d_tx_conditions_only_on_formal_d_ob():
    pipe = M1Pipeline.smoke(input_size=4)
    model = pipe.model
    assert all("delta_ob" not in name.lower()
               for name, _ in model.named_parameters())
    state = model.state_representation(
        model.encode_history(torch.zeros(1, 2, 4), torch.tensor([2])))
    zero_a, quant_a = model.d_tx_heads(state, 0, 2)
    zero_b, quant_b = model.d_tx_heads(state, 0, 2)
    assert torch.equal(zero_a, zero_b)
    assert torch.equal(quant_a, quant_b)


# ---------------------------------------------------------------------------
# U. D_TO identity remains exact
# ---------------------------------------------------------------------------

def test_u_d_to_identity_remains_exact():
    row = _scenario(scenario_id=0, weight=1.0, d_ob=10.0, d_tx=5.0)
    assert row.d_to_minutes == pytest.approx(15.0, abs=1e-9)
    assert row.d_to_minutes == pytest.approx(
        row.d_ob_minutes + row.d_tx_minutes, abs=1e-9)


# ---------------------------------------------------------------------------
# V. scenario marginal remains empirical/scenario-derived
# ---------------------------------------------------------------------------

def test_v_scenario_marginal_stays_empirical():
    rows = (
        _scenario(scenario_id=0, weight=0.25, d_ob=10.0, d_tx=0.0),
        _scenario(scenario_id=1, weight=0.25, d_ob=20.0, d_tx=5.0),
        _scenario(scenario_id=2, weight=0.50, d_ob=40.0, d_tx=15.0),
    )
    summary = scenario_marginal_summary(rows, quantile_levels=(0.5,))
    assert summary["D_OB"]["summary_kind"] == "SCENARIO_MARGINAL_SUMMARY"
    assert summary["D_OB"]["support"] == "SUPPORTED"
    assert summary["D_OB"]["quantiles_minutes"]["0.5"] == pytest.approx(20.0)
    assert summary["D_TX"]["zero_probability"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# W. upper-tail unresolved still gates unsupported CVaR use
# ---------------------------------------------------------------------------

def test_w_upper_tail_unresolved_gates_cvar():
    contract = HurdleQuantileContract(
        target_name="D_OB", bin_width_minutes=5, max_finite_minutes=60,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
    )
    assert cvar_support_status(contract, 0.90) == "GATED"
    with pytest.raises(ContractError, match="M1_POSITIVE_TAIL_DECISION_REQUIRED"):
        require_cvar_support(contract, 0.90)


# ---------------------------------------------------------------------------
# X. public absolute T_IB preserved
# ---------------------------------------------------------------------------

def test_x_public_absolute_t_ib_preserved():
    decision = "2019-01-01T12:00:00+00:00"
    event = "2019-01-01T12:30:00+00:00"
    assert remaining_hazard_coordinate_minutes(event, decision) == 30.0
    assert t_ib_a00_from_remaining_minutes(decision, 30.0) == event
    scenario = _scenario(d_ob=0.0, d_tx=0.0, t_ib=event)
    assert scenario.t_ib_a00_utc == event
    assert scenario.r_ib_minutes == 30.0
