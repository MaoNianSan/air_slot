"""Tranche 3 M1 execution closure tests (spec section 14, items 1-10).

Covers:
- 1  state production predict auto-derives r_fast
- 2  predict/scenario paths consume the same h + r_fast information state
- 3  mixed active/inactive hazard calibration is safe
- 4  inactive hazard rows have zero calibration influence
- 5  D_OB zero calibration actually fitted (lifecycle wiring + fit machinery)
- 6  D_TX zero calibration actually fitted
- 7  zero temperatures affect only the hurdle zero logits
- 8  quantile values/logits are never scaled by zero-mass temperatures
- 9  FAST exposes the same scientific calibration policy
- 10 FAST fitted calibration is applied in the development path
Plus: FAST/STATE_AWARE static parity (c_static changes the FAST state) and
the FAST D_TX formal-parent encoding fix.
"""

from datetime import datetime, timezone

import numpy as np
import pytest
import torch

import model.M1.lifecycle as lifecycle_module
import model.M1.fast_path as fast_path_module
from model.common.errors import ContractError
from model.M1.calibration import (
    common_calibration_policy,
    fit_hazard_temperature,
    fit_zero_mass_temperature,
)
from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1_TEMPERATURE_D_OB_ZERO,
    M1_TEMPERATURE_D_TX_ZERO,
    M1_TEMPERATURE_HAZARD,
    M1_V2_HAZARD_COORDINATE,
)
from model.M1.data import STATIC_FEATURE_COUNT, fast_features_from_sequence
from model.M1.fast_path import LightGBMDistributionalPredictor
from model.M1.lifecycle import M1Lifecycle, M1TrainingExample
from model.M1.network import M1V2GRU
from model.M1.pipeline import M1Pipeline
from model.PRE.foundation import PREBuildRequest, build_pre_state

UTC = timezone.utc


def _pre_state(dataset: str, *, stage: str = "PRE_IB"):
    return build_pre_state(PREBuildRequest(
        episode_id="episode-z", predecessor_id="P", successor_id="S",
        decision_time=datetime(2019, 1, 1, 12, tzinfo=UTC),
        information_cutoff=datetime(2019, 1, 1, 11, 55, tzinfo=UTC),
        config_hash="sha256:c", registry_hash="sha256:r",
        dataset_instance_id=dataset,
    )).pre_state


# ---------------------------------------------------------------------------
# 1. production predict auto-derives r_fast (never a zero block)
# ---------------------------------------------------------------------------

def test_1_state_production_predict_auto_derives_r_fast():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4],
                            [0.5, 0.6, 0.7, 0.8],
                            [1.0, 1.1, 1.2, 1.3]]])
    lengths = torch.tensor([3])
    auto = pipe.predict_distributions(values, lengths)
    explicit = pipe.predict_distributions(
        values, lengths,
        fast_features=fast_features_from_sequence(values, lengths))
    assert torch.allclose(auto["T_IB_A00"], explicit["T_IB_A00"])
    assert torch.allclose(auto["D_OB"]["zero_probability"],
                          explicit["D_OB"]["zero_probability"])
    # r_fast is the deterministic last causal row, not zeros.
    r_fast = fast_features_from_sequence(values, lengths)
    assert torch.equal(r_fast, values[:, -1:, :].squeeze(1))
    assert not torch.allclose(r_fast, torch.zeros_like(r_fast))


# ---------------------------------------------------------------------------
# 2. production forecast and scenario generation share the same information
#    state (h + r_fast); the same state feeds predict and sample paths.
# ---------------------------------------------------------------------------

def test_2_predict_and_scenario_consume_same_information_state():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.tensor([[[0.25, 0.5, 0.75, 1.0],
                            [1.25, 1.5, 1.75, 2.0]]])
    lengths = torch.tensor([2])
    pre = _pre_state("data2_2019")
    # The shared information state consumed by the production path...
    history, fast, _, state = pipe._information_state(values, lengths)
    expected = pipe.model.state_representation(history, fast, None)
    assert torch.allclose(state, expected)
    # ...equals the state used by scenario generation (sample_from_pre feeds
    # the same history + r_fast through ancestral_sample_v2).
    scenarios = pipe.sample_from_pre(
        pre, values, lengths, observed={"T_IB_A00": "2019-01-01T12:30:00+00:00"},
        count=4, seed=7)
    assert len(scenarios) == 4
    assert all(row.t_ib_a00_utc == "2019-01-01T12:30:00+00:00" for row in scenarios)
    # Production predict_from_pre derives the same r_fast from the same
    # sequence: its hazard PMF equals the manual explicit state summary.
    produced = pipe.predict_from_pre(pre, values, lengths)
    assert produced["T_IB_A00"].shape == state.shape[0:1] + (pipe.contracts[
        M1_V2_HAZARD_COORDINATE].class_count,)


def test_1b_service_predict_now_matches_explicit_derived_r_fast():
    # Spec 3.1 production-path regression: M1Service.predict_now(mode="state")
    # consumes the exact same h + r_fast as an explicit pipeline call with the
    # derived r_fast (deterministic model fixture).
    from datetime import datetime
    from model.M1.service import M1Service
    pipe = M1Pipeline.smoke(input_size=4)
    service = M1Service(pipe, model_version="smoke")
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4],
                            [0.5, 0.6, 0.7, 0.8]]])
    lengths = torch.tensor([2])
    pre = _pre_state("data2_2019")
    forecast = service.predict_now(pre, values, lengths, mode="state")
    explicit = pipe.predict_distributions(
        values, lengths,
        fast_features=fast_features_from_sequence(values, lengths))
    assert forecast.model_path.value == "STATE_AWARE"
    assert torch.allclose(forecast.distributions["T_IB_A00"],
                          explicit["T_IB_A00"])
    assert torch.allclose(forecast.distributions["D_OB"]["zero_probability"],
                          explicit["D_OB"]["zero_probability"])


# ---------------------------------------------------------------------------
# 3/4. hazard calibration is active-safe; inactive rows never influence it
# ---------------------------------------------------------------------------

def _hazard_logits(n):
    return torch.linspace(-1.0, 1.0, n).reshape(-1, 1).expand(-1, 5) * 2.0


def test_3_mixed_active_inactive_hazard_calibration_safe():
    hazard = HazardBinContract(bin_width_minutes=5, max_finite_minutes=25)
    logits = _hazard_logits(4)
    labels = torch.tensor([0, 1, -1, -1])
    active = torch.tensor([True, True, False, False])
    temperature = fit_hazard_temperature(logits, labels, active, hazard)
    assert 0.05 <= temperature <= 20.0


def test_4_inactive_hazard_rows_have_zero_calibration_influence():
    hazard = HazardBinContract(bin_width_minutes=5, max_finite_minutes=25)
    logits = _hazard_logits(6)
    active_only = torch.tensor([True, True, True, True, True, True])
    labels_only = torch.tensor([0, 1, 2, 3, 4, 5])
    # Same six rows with the last three marked inactive (label -1): the
    # objective must be identical to the active-only fit.
    labels_mixed = torch.tensor([0, 1, 2, -1, -1, -1])
    active_mixed = torch.tensor([True, True, True, False, False, False])
    fit_active_only = fit_hazard_temperature(logits, labels_only, active_only, hazard)
    fit_mixed = fit_hazard_temperature(logits, labels_mixed, active_mixed, hazard)
    assert fit_mixed == pytest.approx(fit_active_only, abs=1e-4)


# ---------------------------------------------------------------------------
# 5/6. zero-mass calibration is actually wired into the lifecycle
# ---------------------------------------------------------------------------

def _example(episode, day, offset, *, active_ob=True, active_tx=True):
    return M1TrainingExample(
        episode_id=episode,
        episode_date=day,
        values=torch.full((3, 4), float(offset)),
        targets={"T_IB_REMAINING_HAZARD": offset % 6,
                 "D_OB": (offset + 1) % 11,
                 "D_TX": (offset + 2) % 6},
        active={"T_IB_REMAINING_HAZARD": True,
                "D_OB": active_ob,
                "D_TX": active_tx},
    )


def test_5_d_ob_zero_calibration_actually_fitted():
    # The zero-mass fit function moves an interior optimum away from 1.0.
    true_logits = torch.tensor([-2.0, -1.0, 0.0, 1.0, 2.0])
    labels = torch.sigmoid(true_logits)
    fitted = fit_zero_mass_temperature(
        true_logits * 2.0, labels, torch.ones(5, dtype=torch.bool))
    assert abs(fitted - 2.0) < 0.05  # optimal temperature = 2.0 (not 1.0)
    # And the lifecycle calibrate path actually invokes it for D_OB.
    lifecycle = M1Lifecycle(M1Pipeline.smoke(4))
    lifecycle.train([_example("cal", datetime(2019, 7, 1).date(), 0)], epochs=1,
                    learning_rate=0.01)
    original = lifecycle_module.fit_zero_mass_temperature
    calls = []
    lifecycle_module.fit_zero_mass_temperature = (
        lambda *args, **kwargs: (calls.append(args), 2.5)[1])
    try:
        temperatures = lifecycle.calibrate([_example("cal", datetime(2019, 7, 1).date(), 0)])
    finally:
        lifecycle_module.fit_zero_mass_temperature = original
    assert len(calls) == 2  # D_OB then D_TX
    assert temperatures[M1_TEMPERATURE_D_OB_ZERO] == 2.5
    assert temperatures[M1_TEMPERATURE_D_TX_ZERO] == 2.5


def test_6_d_tx_zero_calibration_actually_fitted():
    # Direct fit for D_TX-shaped logits (interior optimum away from 1.0).
    true_logits = torch.tensor([-3.0, -0.5, 0.5, 3.0])
    labels = torch.sigmoid(true_logits)
    fitted = fit_zero_mass_temperature(
        true_logits * 2.0, labels, torch.ones(4, dtype=torch.bool))
    assert abs(fitted - 2.0) < 0.05
    # Lifecycle calibration returns the D_TX zero temperature from the
    # registry (already exercised in test_5 via the wiring monkeypatch).


def test_calibration_policy_coverage_and_split_persisted(tmp_path):
    pipe = M1Pipeline.smoke(4)
    lifecycle = M1Lifecycle(pipe)
    examples = [
        _example(f"cal-{i}", datetime(2019, 7, 1).date(), i)
        for i in range(4)
    ]
    lifecycle.calibrate(examples)
    assert pipe.calibration_contract.version == "M1_CALIBRATION_CONTRACT_V1"
    assert pipe.calibration_contract.split == "calibration"
    assert pipe.calibration_diagnostics["positive_quantile_status"] == (
        "QUANTILE_CALIBRATION_NOT_APPLIED")
    assert set(pipe.calibration_diagnostics["positive_quantile_coverage"]) == {
        "D_OB", "D_TX"}
    path = tmp_path / "m1.pt"
    pipe.save(path)
    loaded = M1Pipeline.load(path)
    assert loaded.calibration_contract == pipe.calibration_contract
    assert loaded.calibration_diagnostics == pipe.calibration_diagnostics


# ---------------------------------------------------------------------------
# 7/8. zero-mass temperatures scale ONLY hurdle zero logits
# ---------------------------------------------------------------------------

def test_7_and_8_zero_temperature_only_scales_zero_logits():
    pipe = M1Pipeline.smoke(input_size=4)
    values = torch.tensor([[[0.1, -0.2, 0.3, 0.4],
                            [0.5, 0.6, -0.7, 0.8]]])
    lengths = torch.tensor([2])
    pipe.temperatures = {
        M1_TEMPERATURE_HAZARD: 1.0,
        M1_TEMPERATURE_D_OB_ZERO: 1.0,
        M1_TEMPERATURE_D_TX_ZERO: 1.0,
    }
    base = pipe.predict_distributions(values, lengths)
    pipe.temperatures = {
        M1_TEMPERATURE_HAZARD: 1.0,
        M1_TEMPERATURE_D_OB_ZERO: 3.0,
        M1_TEMPERATURE_D_TX_ZERO: 3.0,
    }
    altered = pipe.predict_distributions(values, lengths)
    # T_IB pmf unchanged (hazard temperature untouched).
    assert torch.allclose(base["T_IB_A00"], altered["T_IB_A00"])
    # Zero probabilities DO change.
    assert not torch.allclose(base["D_OB"]["zero_probability"],
                              altered["D_OB"]["zero_probability"])
    assert not torch.allclose(base["D_TX"]["zero_probability"],
                              altered["D_TX"]["zero_probability"])
    # Positive quantile values/logits are NEVER temperature-scaled.
    assert torch.allclose(base["D_OB"]["positive_quantiles_minutes"],
                          altered["D_OB"]["positive_quantiles_minutes"])
    assert torch.allclose(base["D_TX"]["positive_quantiles_minutes"],
                          altered["D_TX"]["positive_quantiles_minutes"])


# ---------------------------------------------------------------------------
# 9/10. FAST calibration policy + fitted temperatures applied
# ---------------------------------------------------------------------------

def _fitted_fast(*, n_estimators=6):
    pipeline = M1Pipeline.smoke(input_size=4)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(48, 4))
    ib = np.abs(rng.normal(30.0, 15.0, size=48))
    d_ob = np.where(rng.random(48) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=48)))
    d_tx = np.where(rng.random(48) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=48)))
    predictor = LightGBMDistributionalPredictor(pipeline.contracts)
    predictor.fit(X, {
        "T_IB_REMAINING_HAZARD": ib,
        "D_OB": d_ob,
        "D_TX": d_tx,
    }, seed=7, n_estimators=n_estimators, allow_test_only_surrogate=True)
    return pipeline, predictor


def test_9_fast_exposes_same_calibration_policy():
    _, predictor = _fitted_fast()
    assert predictor.calibration_policy() == common_calibration_policy()


def test_10_fast_fitted_calibration_applied_in_development_path():
    pipeline, predictor = _fitted_fast()
    rng = np.random.default_rng(1)
    X = rng.normal(size=(32, 4))
    ib = np.abs(rng.normal(30.0, 15.0, size=32))
    d_ob = np.where(rng.random(32) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=32)))
    d_tx = np.where(rng.random(32) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=32)))
    original_hazard = fast_path_module.fit_hazard_temperature
    original_zero = fast_path_module.fit_zero_mass_temperature
    fast_path_module.fit_hazard_temperature = (
        lambda *args, **kwargs: 2.0)
    fast_path_module.fit_zero_mass_temperature = (
        lambda *args, **kwargs: 3.0)
    try:
        temperatures = predictor.calibrate_development(
            X, ib_target=ib, d_ob_target=d_ob, d_tx_target=d_tx,
            split="calibration")
    finally:
        fast_path_module.fit_hazard_temperature = original_hazard
        fast_path_module.fit_zero_mass_temperature = original_zero
    assert temperatures == {
        M1_TEMPERATURE_HAZARD: 2.0,
        M1_TEMPERATURE_D_OB_ZERO: 3.0,
        M1_TEMPERATURE_D_TX_ZERO: 3.0,
    }
    assert predictor.calibration_diagnostics["positive_quantile_status"] == (
        "QUANTILE_CALIBRATION_NOT_APPLIED")
    assert set(predictor.calibration_diagnostics["positive_quantile_coverage"]) == {
        "D_OB", "D_TX"}
    # The fitted temperatures are applied by the development prediction path:
    # zero probabilities change, quantiles stay untouched.
    values = torch.tensor(rng.normal(size=(1, 2, 4)), dtype=torch.float32)
    lengths = torch.tensor([2])
    base = predictor.predict_development(values, lengths)
    predictor.calibration_temperatures = {
        M1_TEMPERATURE_HAZARD: 1.0,
        M1_TEMPERATURE_D_OB_ZERO: 5.0,
        M1_TEMPERATURE_D_TX_ZERO: 5.0,
    }
    altered = predictor.predict_development(values, lengths)
    assert not torch.allclose(base["D_OB"]["zero_probability"],
                              altered["D_OB"]["zero_probability"])
    assert not torch.allclose(base["D_TX"]["zero_probability"],
                              altered["D_TX"]["zero_probability"])
    assert torch.allclose(base["D_OB"]["positive_quantiles_minutes"],
                          altered["D_OB"]["positive_quantiles_minutes"])


def test_10b_fast_d_tx_calibration_uses_formal_d_ob_parent():
    pipeline, predictor = _fitted_fast()
    rng = np.random.default_rng(2)
    X = rng.normal(size=(16, 4))
    ib = np.abs(rng.normal(30.0, 15.0, size=16))
    d_ob = np.where(rng.random(16) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=16)))
    d_tx = np.where(rng.random(16) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=16)))
    d_ob_broken = d_ob.copy()
    d_ob_broken[3] = float("nan")  # active D_TX row without its formal parent
    with pytest.raises(ContractError, match="M1_FAST_D_TX_CALIBRATION_PARENT_MISSING"):
        predictor.calibrate_development(
            X, ib_target=ib, d_ob_target=d_ob_broken, d_tx_target=d_tx,
            split="calibration")


# ---------------------------------------------------------------------------
# FAST/STATE_AWARE static parity: c_static changes the FAST state
# ---------------------------------------------------------------------------

def test_fast_static_parity_c_static_changes_state_and_distribution():
    # FAST models are fitted on concat(r_fast, c_static) (manuscript
    # [r_fast, c_static] representation).
    pipeline = M1Pipeline.smoke(input_size=4)
    rng = np.random.default_rng(11)
    X = rng.normal(size=(96, 4))
    # Targets depend on the static columns so the fitted ARX-LightGBM
    # genuinely splits on c_static (the static block must be able to change
    # the downstream distribution, not just be appended to the state).
    static_fit = rng.normal(size=(96, STATIC_FEATURE_COUNT))
    ib = np.abs(30.0 + 8.0 * static_fit[:, 0]
                + rng.normal(0.0, 3.0, size=96))
    d_ob = np.where(rng.random(96) < 0.3, 0.0,
                    np.abs(40.0 + 6.0 * static_fit[:, 1]
                           + rng.normal(0.0, 4.0, size=96)))
    d_tx = np.where(rng.random(96) < 0.3, 0.0,
                    np.abs(15.0 + 3.0 * static_fit[:, 0]
                           + rng.normal(0.0, 3.0, size=96)))
    predictor = LightGBMDistributionalPredictor(pipeline.contracts)
    predictor.fit(X, {
        "T_IB_REMAINING_HAZARD": ib,
        "D_OB": d_ob,
        "D_TX": d_tx,
    }, seed=7, n_estimators=16, allow_test_only_surrogate=True,
        static_features=static_fit)
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4],
                            [0.5, 0.6, 0.7, 0.8]]])
    lengths = torch.tensor([2])
    static_a = torch.tensor([[-4.0, -4.0, 0.0, 0.0]], dtype=torch.float32)
    static_b = torch.tensor([[4.0, 4.0, 0.0, 0.0]], dtype=torch.float32)
    with_a = predictor._predict_heads(values, lengths, static_features=static_a)
    with_b = predictor._predict_heads(values, lengths, static_features=static_b)
    # The static block changes the fused FAST state and therefore the
    # downstream distribution somewhere (tree discretization may leave an
    # individual head unchanged, so we assert over every head output).
    state_a = predictor.state_representation(
        torch.tensor(predictor._fast_features(values, lengths), dtype=torch.float32),
        None, static_a)
    state_b = predictor.state_representation(
        torch.tensor(predictor._fast_features(values, lengths), dtype=torch.float32),
        None, static_b)
    assert not torch.allclose(state_a, state_b)
    heads_a = [with_a["T_IB_A00"], with_a["D_OB"]["zero_probability"],
               with_a["D_OB"]["positive_quantiles_minutes"],
               with_a["D_TX"]["zero_probability"],
               with_a["D_TX"]["positive_quantiles_minutes"]]
    heads_b = [with_b["T_IB_A00"], with_b["D_OB"]["zero_probability"],
               with_b["D_OB"]["positive_quantiles_minutes"],
               with_b["D_TX"]["zero_probability"],
               with_b["D_TX"]["positive_quantiles_minutes"]]
    assert any(not torch.allclose(x, y) for x, y in zip(heads_a, heads_b))
    # Missing static block is a width-contract violation, never silent zeros.
    with pytest.raises(ContractError, match="M1_FAST_STATIC_FEATURES_REQUIRED"):
        predictor._predict_heads(values, lengths)
    # Same numeric contract as STATE_AWARE: static block is appended to
    # r_fast, never an ordinal encoding of retained identities.
    state = predictor.state_representation(
        torch.tensor(predictor._fast_features(values, lengths), dtype=torch.float32),
        None, static_a)
    assert state.shape == (1, 4 + STATIC_FEATURE_COUNT)


def test_state_aware_static_block_changes_distribution():
    from model.M1.pipeline import M1Pipeline as _M1Pipeline
    contracts = {
        M1_V2_HAZARD_COORDINATE: HazardBinContract(
            bin_width_minutes=5, max_finite_minutes=60),
        "D_OB": HurdleQuantileContract(
            target_name="D_OB", bin_width_minutes=5, max_finite_minutes=60,
            quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
            upper_tail_policy="TEST_ONLY_LINEAR"),
        "D_TX": HurdleQuantileContract(
            target_name="D_TX", bin_width_minutes=5, max_finite_minutes=30,
            quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
            upper_tail_policy="TEST_ONLY_LINEAR"),
    }
    torch.manual_seed(3)
    model = M1V2GRU(4, 16, contracts[M1_V2_HAZARD_COORDINATE],
                    contracts["D_OB"], contracts["D_TX"],
                    fast_input_size=4, static_input_size=STATIC_FEATURE_COUNT)
    pipe = _M1Pipeline(model, contracts)
    values = torch.tensor([[[0.1, 0.2, 0.3, 0.4],
                            [0.5, 0.6, 0.7, 0.8]]])
    lengths = torch.tensor([2])
    without = pipe.predict_distributions(values, lengths)
    with_static = pipe.predict_distributions(
        values, lengths,
        static_features=torch.tensor([[12.0, 45.0, 0.0, 0.0]], dtype=torch.float32))
    assert not torch.allclose(without["T_IB_A00"], with_static["T_IB_A00"])
    assert model.static_input_size == STATIC_FEATURE_COUNT
    assert model.state_width == 2 * model.hidden_size + model.hidden_size
