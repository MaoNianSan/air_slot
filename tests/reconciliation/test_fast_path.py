"""FAST path closure tests — ARX-LightGBM shares the STATE_AWARE contract."""

import numpy as np
import pytest
import torch

from model.M1.fast_path import (
    LightGBMDistributionalPredictor,
    M1FastPathStatus,
)
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import aligned_sample
from model.common.errors import ContractError

lgb = pytest.importorskip("lightgbm")


def _fit_predictor(pipeline, seed=0):
    rng = np.random.default_rng(seed)
    batch, time, features = 24, 6, 4
    values = torch.tensor(rng.normal(size=(batch, time, features)), dtype=torch.float32)
    models = {}
    for target in ("R_IB", "DELTA_OB", "T_TX"):
        class_count = pipeline.bins[target].class_count
        labels = rng.integers(0, class_count, size=batch)
        # ARX features replicate the predictor's lag-matrix construction.
        lag = np.zeros((batch, time * features), dtype=np.float32)
        for index in range(batch):
            window = values[index].numpy()
            lag[index] = window.reshape(-1)
        model = lgb.LGBMClassifier(
            n_estimators=4, max_depth=2, num_leaves=4,
            objective="multiclass", num_class=class_count, verbose=-1,
        )
        model.fit(lag, labels)
        models[target] = model
    return LightGBMDistributionalPredictor(
        pipeline.bins, models=models, feature_window=time
    )


def test_fast_predictor_abstains_without_fitted_models():
    pipeline = M1Pipeline.smoke(input_size=4)
    predictor = LightGBMDistributionalPredictor(pipeline.bins)
    assert predictor.status is M1FastPathStatus.ABSTAIN
    with pytest.raises(ContractError, match="M1_FAST_PATH_ABSTAIN"):
        predictor.predict_distributions(torch.zeros(1, 2, 4))


def test_fast_distributions_share_state_aware_schema_and_scenarios():
    pipeline = M1Pipeline.smoke(input_size=4)
    predictor = _fit_predictor(pipeline)
    assert predictor.status is M1FastPathStatus.DEVELOPMENT_ONLY
    contract = predictor.contract()
    assert contract.feature_semantics == "CAUSAL_HISTORY_PREFIX_ONLY"
    assert contract.target_semantics == "R_IB_DELTA_OB_T_TX_BIN_CONTRACTS"
    assert contract.output_schema == "TARGET_KEYED_CLASS_PROBABILITIES"
    assert contract.scenario_schema == "ALIGNED_SCENARIO"
    assert contract.final_test_access_count == 0
    assert contract.paper_full_run is False

    values = torch.zeros(1, 6, 4)
    distributions = predictor.predict_distributions(values)
    assert set(distributions) == {"R_IB", "DELTA_OB", "T_TX"}
    for target in distributions:
        class_count = pipeline.bins[target].class_count
        assert distributions[target].shape == (1, class_count)
        assert torch.allclose(distributions[target].sum(dim=-1),
                              torch.ones(1), atol=1e-4)

    # Same aligned scenario contract as the GRU path.
    scenarios = aligned_sample(
        distributions, pipeline.bins,
        episode_id="e", decision_node_id="n", stage="PRE_IB",
        observed={}, count=8, seed=11,
        target_support={name: "SUPPORTED" for name in pipeline.bins},
        tx_reference_minutes=12.0,
        taxi_reference_id="reference", taxi_reference_hash="freeze",
        taxi_reference_support_state="SUPPORTED",
    )
    assert all(row.scenario_weight == 1 / 8 for row in scenarios)
    assert all(row.d_to_minutes is None or row.d_to_minutes >= 0 for row in scenarios)
    assert all(
        row.d_to_minutes is None
        or row.d_to_minutes == pytest.approx(row.d_ob_minutes + row.d_tx_minutes, abs=1e-9)
        for row in scenarios
    )


def test_fast_path_works_through_m1_service_callback_contract():
    from model.M1.service import M1Service

    pipeline = M1Pipeline.smoke(input_size=4)
    predictor = _fit_predictor(pipeline, seed=3)
    service = M1Service(pipeline, model_version="fixture", fast_predictor=predictor)
    values = torch.zeros(1, 6, 4)
    lengths = torch.tensor([6])
    from model.PRE.foundation import build_pre_state
    from tests.fixtures.pre.foundation_cases import build_request
    pre_state = build_pre_state(build_request()).pre_state
    with pytest.raises(ContractError, match="M1_FAST_PATH_NOT_CONFIGURED"):
        M1Service(pipeline, model_version="fixture").predict_now(
            pre_state, values, lengths, mode="fast")
    # Callback returns the shared distribution schema before M1Forecast wraps it.
    distributions = predictor.predict_distributions(values)
    assert set(distributions) == set(pipeline.bins)
