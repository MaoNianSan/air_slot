from datetime import datetime, timezone

import pytest

from exp.common.result_schema import (
    ExperimentResult,
    MetricLevel,
    MetricObservation,
    SupportStatus,
)


@pytest.fixture
def common_result():
    metric = MetricObservation(
        metric_id="STATE_CRPS",
        level=MetricLevel.STATE,
        value=None,
        unit="minutes",
        support_status=SupportStatus.NOT_RUN,
        metadata={"reason": "INTERFACE_FIXTURE_ONLY"},
    )
    return ExperimentResult(
        experiment_id="EXP2",
        variant_id="EXP2_JOINT",
        dataset_id="data2_2019",
        seed=20260820,
        timestamp=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
        model_versions={"M1": "M1_V2"},
        artifact_versions={"M1_SCENARIOS": "M1_V2_FIXTURE"},
        scenario_hash="sha256:" + "a" * 64,
        config_hash="sha256:" + "b" * 64,
        metrics={metric.metric_id: metric},
        support_status=SupportStatus.NOT_RUN,
        provenance={"scope": "INTERFACE_TEST_ONLY", "paper_result": False},
    )

