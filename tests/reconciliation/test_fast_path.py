"""FAST path closure tests — V2 schema is shared with STATE_AWARE M1.

The FAST predictor abstains (``ABSTAIN``) and raises until a train-frozen V2
artifact is registered; the formal contract and the V2 scenario schema
(``M1V2_SCENARIO``) are identical to the state-aware path.
"""

import pytest
import torch

from model.M1.fast_path import (
    LightGBMDistributionalPredictor,
    M1FastPathStatus,
    fast_v2_distribution_schema,
)
from model.M1.pipeline import M1Pipeline
from model.M1.scenarios import ancestral_sample_v2
from model.common.errors import ContractError


def test_fast_predictor_abstains_without_fitted_models():
    pipeline = M1Pipeline.smoke(input_size=4)
    predictor = LightGBMDistributionalPredictor(pipeline.contracts)
    assert predictor.status is M1FastPathStatus.ABSTAIN
    with pytest.raises(ContractError, match="M1_FAST_PATH_ABSTAIN"):
        predictor.predict_distributions(torch.zeros(1, 2, 4))


def test_fast_distributions_share_state_aware_schema_and_scenarios():
    pipeline = M1Pipeline.smoke(input_size=4)
    # Even a fitted model cannot emit V2 distributions until a train-frozen
    # V2 artifact is registered (no fabricated development outputs).
    predictor = LightGBMDistributionalPredictor(
        pipeline.contracts, models={name: object() for name in pipeline.contracts})
    assert predictor.status is M1FastPathStatus.DEVELOPMENT_ONLY
    contract = predictor.contract()
    assert contract.feature_semantics == "CAUSAL_HISTORY_PREFIX_ONLY"
    assert contract.target_semantics == "T_IB_A00_D_OB_D_TX_HAZARD_HURDLE_QUANTILE_CONTRACTS"
    assert contract.output_schema == "V2_TARGET_KEYED_DISTRIBUTION_SUMMARY"
    assert contract.scenario_schema == "M1V2_SCENARIO"
    assert contract.final_test_access_count == 0
    assert contract.paper_full_run is False
    with pytest.raises(ContractError, match="M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED"):
        predictor.predict_distributions(torch.zeros(1, 6, 4))

    # FAST and STATE_AWARE declare the same formal distribution schema.
    assert set(fast_v2_distribution_schema()) == {"T_IB_A00", "D_OB", "D_TX"}
    assert fast_v2_distribution_schema()["D_OB"] == {
        "zero_probability": "scalar", "positive_quantiles_minutes": "vector"}
    assert set(pipeline.predict_distributions(
        torch.zeros(1, 6, 4), torch.ones(1, dtype=torch.long))) == {
        "T_IB_A00", "D_OB", "D_TX"}

    # Both paths consume the same V2 scenario schema.
    history = pipeline.model.encode_history(
        torch.zeros(1, 6, 4), torch.ones(1, dtype=torch.long))
    scenarios = ancestral_sample_v2(
        pipeline.model, history, pipeline.contracts,
        episode_id="e", decision_node_id="n", stage="PRE_IB",
        observed={}, count=8, seed=11,
        target_support={name: "SUPPORTED" for name in pipeline.contracts},
        decision_time_utc="2019-01-01T12:00:00+00:00",
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
    predictor = LightGBMDistributionalPredictor(
        pipeline.contracts, models={name: object() for name in pipeline.contracts})
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
