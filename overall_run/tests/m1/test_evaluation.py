from __future__ import annotations

import numpy as np

from overall_run.src.m1.evaluation.report import evaluate_distribution
from overall_run.src.m1.evaluation.update_metrics import update_metrics


def test_raw_and_calibrated_evaluation_contract() -> None:
    actual = np.array([0.0, 5.0, 10.0, 15.0])
    indices = np.array([0, 1, 2, 3])
    raw = np.full((4, 4), 0.25)
    calibrated = np.eye(4) * 0.9 + 0.1 / 4.0
    result = evaluate_distribution(
        actual, indices, raw, calibrated, np.array([0.0, 5.0, 10.0, 15.0])
    )
    assert set(result) == {"raw_metrics", "calibrated_metrics", "delta_metrics"}
    assert result["calibrated_metrics"]["nll"] < result["raw_metrics"]["nll"]
    assert "threshold_15_brier" in result["calibrated_metrics"]


def test_update_metrics_report_latency_and_idempotence() -> None:
    metrics = update_metrics(
        np.array([1.0]),
        np.array([1.0]),
        np.array([2.0]),
        np.array([2.0]),
        duplicate_updates=0,
        total_updates=2,
        temporal_order_violations=0,
        replay_count=1,
        state_reset_count=1,
        latency_ms=np.array([1.0, 2.0, 3.0]),
    )
    assert metrics["scheduled_direct_difference"] == 0.0
    assert metrics["duplicate_state_update_rate"] == 0.0
    assert metrics["latency_p99_ms"] >= metrics["latency_p95_ms"]
