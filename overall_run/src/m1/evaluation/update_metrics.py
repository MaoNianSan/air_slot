from __future__ import annotations

import numpy as np


def update_metrics(
    scheduled: np.ndarray,
    direct: np.ndarray,
    repeated_first: np.ndarray,
    repeated_second: np.ndarray,
    *,
    duplicate_updates: int,
    total_updates: int,
    temporal_order_violations: int,
    replay_count: int,
    state_reset_count: int,
    latency_ms: np.ndarray,
) -> dict[str, float]:
    latency = np.asarray(latency_ms, dtype=float)
    return {
        "scheduled_direct_difference": float(np.max(np.abs(scheduled - direct))),
        "repeated_query_difference": float(np.max(np.abs(repeated_first - repeated_second))),
        "duplicate_state_update_rate": duplicate_updates / max(total_updates, 1),
        "temporal_order_violation_rate": temporal_order_violations / max(total_updates, 1),
        "replay_count": float(replay_count),
        "state_reset_count": float(state_reset_count),
        "latency_p50_ms": float(np.quantile(latency, 0.50)) if latency.size else float("nan"),
        "latency_p95_ms": float(np.quantile(latency, 0.95)) if latency.size else float("nan"),
        "latency_p99_ms": float(np.quantile(latency, 0.99)) if latency.size else float("nan"),
    }
