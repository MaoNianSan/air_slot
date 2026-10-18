"""FAST path closure tests — executable ARX-LightGBM V2 baseline.

The FAST predictor shares the V2 schema and the V2 scenario sampler with the
STATE_AWARE path; the principal ``predict_distributions`` stays ABSTAIN until
a train-frozen V2 artifact is registered.  Round 2.1 adds an executable
architecture (hazard models + zero classifiers + positive quantile
regressors), exercised here through synthetic fitting and
``predict_development`` (never a paper result).
"""

import numpy as np
import pytest
import torch

from model.M1.fast_path import (
    LightGBMDistributionalPredictor,
    M1FastPathStatus,
    fast_v2_distribution_schema,
)
from model.M1.pipeline import M1Pipeline
from model.M1.scenario_layer.sampler import ancestral_sample_v2
from model.common.errors import ContractError


def _fitted_predictor(*, n_estimators=8):
    pipeline = M1Pipeline.smoke(input_size=4)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, 4))
    ib = np.abs(rng.normal(30.0, 15.0, size=64))
    d_ob = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(40.0, 25.0, size=64)))
    d_tx = np.where(rng.random(64) < 0.3, 0.0,
                    np.abs(rng.normal(15.0, 10.0, size=64)))
    predictor = LightGBMDistributionalPredictor(pipeline.contracts)
    predictor.fit(X, {
        "T_IB_REMAINING_HAZARD": ib,
        "D_OB": d_ob,
        "D_TX": d_tx,
    }, seed=7, n_estimators=n_estimators, allow_test_only_surrogate=True)
    return pipeline, predictor


def test_fast_predictor_abstains_without_fitted_models():
    pipeline = M1Pipeline.smoke(input_size=4)
    predictor = LightGBMDistributionalPredictor(pipeline.contracts)
    assert predictor.status is M1FastPathStatus.ABSTAIN
    with pytest.raises(ContractError, match="M1_FAST_PATH_ABSTAIN"):
        predictor.predict_distributions(torch.zeros(1, 2, 4))
    with pytest.raises(ContractError, match="M1_FAST_PATH_ABSTAIN"):
        predictor.predict_development(torch.zeros(1, 2, 4))


def test_fast_distributions_share_state_aware_schema_and_scenarios():
    pipeline, predictor = _fitted_predictor()
    assert predictor.status is M1FastPathStatus.DEVELOPMENT_ONLY
    contract = predictor.contract()
    assert contract.feature_semantics == "R_FAST_CURRENT_AR_BLOCK_DETERMINISTIC"
    assert contract.hazard_semantics == "DISCRETE_HAZARD_RISK_SET"
    assert contract.target_semantics == "T_IB_A00_D_OB_D_TX_HAZARD_HURDLE_QUANTILE_CONTRACTS"
    assert contract.output_schema == "V2_TARGET_KEYED_DISTRIBUTION_SUMMARY"
    assert contract.scenario_schema == "M1V2_SCENARIO"
    assert contract.final_test_access_count == 0
    assert contract.paper_full_run is False

    # Fitted-but-unfrozen models still abstain on the principal path; the
    # executable architecture is exercised through predict_development only.
    with pytest.raises(ContractError, match="M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED"):
        predictor.predict_distributions(torch.zeros(1, 6, 4))

    values = torch.zeros(1, 6, 4)
    lengths = torch.tensor([6])
    dist = predictor.predict_development(values, lengths)
    assert set(dist) == {"T_IB_A00", "D_OB", "D_TX"}
    assert dist["T_IB_A00"].shape == (
        1, pipeline.contracts["T_IB_REMAINING_HAZARD"].class_count)
    assert dist["D_OB"]["zero_probability"].shape == (1,)
    assert dist["D_OB"]["positive_quantiles_minutes"].shape == (1, 5)
    assert dist["D_OB"]["summary_kind"] == "CONDITIONAL_HEAD_SUMMARY"

    # FAST and STATE_AWARE declare the same formal distribution schema.
    assert set(fast_v2_distribution_schema()) == {"T_IB_A00", "D_OB", "D_TX"}
    assert fast_v2_distribution_schema()["D_OB"] == {
        "zero_probability": "scalar", "positive_quantiles_minutes": "vector"}
    assert set(pipeline.predict_distributions(values, lengths)) == {
        "T_IB_A00", "D_OB", "D_TX"}

    # Both paths consume the same V2 scenario schema through the FAST heads.
    features = predictor._fast_features(values)
    scenarios = predictor.sample(
        features=torch.tensor(features, dtype=torch.float32),
        episode_id="e", decision_node_id="n", stage="PRE_IB",
        observed={}, count=8, seed=11,
        target_support={name: "SUPPORTED"
                        for name in ("T_IB_A00", "D_OB", "D_TX")},
        decision_time_utc="2019-01-01T12:00:00+00:00",
    )
    assert all(row.scenario_weight == 1 / 8 for row in scenarios)
    assert all(row.d_to_minutes is None or row.d_to_minutes >= 0 for row in scenarios)
    assert all(
        row.d_to_minutes is None
        or row.d_to_minutes == pytest.approx(row.d_ob_minutes + row.d_tx_minutes, abs=1e-9)
        for row in scenarios
    )
    # The STATE_AWARE sampler consumes the identical scenario schema.
    state_aware_history = pipeline.model.encode_history(values, lengths)
    reference = ancestral_sample_v2(
        pipeline.model, state_aware_history, pipeline.contracts,
        episode_id="e", decision_node_id="n", stage="PRE_IB",
        observed={}, count=8, seed=11,
        target_support={name: "SUPPORTED"
                        for name in ("T_IB_A00", "D_OB", "D_TX")},
        decision_time_utc="2019-01-01T12:00:00+00:00",
    )
    assert {row.scenario_seed_key for row in scenarios} == {
        row.scenario_seed_key for row in reference}


def test_fast_path_works_through_m1_service_callback_contract():
    from model.M1.service import M1Service

    pipeline = M1Pipeline.smoke(input_size=4)
    _, predictor = _fitted_predictor()
    service = M1Service(pipeline, model_version="fixture", fast_predictor=predictor)
    values = torch.zeros(1, 6, 4)
    lengths = torch.tensor([6])
    from model.PRE.foundation import build_pre_state
    from tests.fixtures.pre.foundation_cases import build_request
    pre_state = build_pre_state(build_request()).pre_state
    with pytest.raises(ContractError, match="M1_FAST_PATH_NOT_CONFIGURED"):
        M1Service(pipeline, model_version="fixture").predict_now(
            pre_state, values, lengths, mode="fast")
    # The callback abstains until a train-frozen V2 FAST artifact is
    # registered; it never fabricates distributional outputs.
    with pytest.raises(ContractError, match="M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED"):
        predictor(pre_state, values, lengths)
