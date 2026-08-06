from __future__ import annotations

import torch

from overall_run.src.m1.adapter.feature_schema import M1FeatureSchema
from overall_run.src.m1.distribution import DiscreteBins
from overall_run.src.m1.model import SingleLightweightGRU
from overall_run.src.m1.runtime import M1UpdateService


def test_feature_schema() -> M1FeatureSchema:
    return M1FeatureSchema(
        schema_version="M1_FEATURE_SCHEMA_V1",
        value_features=("wind_speed",),
        mask_features=(),
        age_features=(),
        stale_features=(),
        fallback_features=(),
        stage_features=(),
        static_features=(),
        final_feature_order=("wind_speed",),
        schema_hash="fixture-schema-hash",
    )


def build_untrained_test_model() -> SingleLightweightGRU:
    torch.manual_seed(7)
    return SingleLightweightGRU(
        1,
        {target: 2 for target in ("R_IB", "R_OB", "T_TX")},
    )


def build_test_service(snapshot_provider=None) -> M1UpdateService:
    bins = {
        target: DiscreteBins((0.0, 5.0), (5.0, None))
        for target in ("R_IB", "R_OB", "T_TX")
    }
    return M1UpdateService(
        build_untrained_test_model(),
        test_feature_schema(),
        bins,
        {target: 1.0 for target in bins},
        model_version="test-model-untrained",
        model_artifact_hash="test-model-artifact",
        temperature_version="test-temperature-identity",
        temperature_artifact_hash="test-temperature-artifact",
        snapshot_provider=snapshot_provider,
    )
