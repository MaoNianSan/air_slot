"""Tie-aware ranking metrics for Exp2."""

from __future__ import annotations

from math import ceil, isfinite
from typing import Iterable, Sequence

import numpy as np
from scipy.stats import kendalltau, rankdata, spearmanr


def _finite_pair(
    left: Iterable[float], right: Iterable[float]
) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(tuple(left), dtype=float)
    y = np.asarray(tuple(right), dtype=float)
    if x.shape != y.shape:
        raise ValueError("EXP2_METRIC_LENGTH_MISMATCH")
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def has_rank_variation(values: Iterable[float]) -> bool:
    array = np.asarray(tuple(values), dtype=float)
    array = array[np.isfinite(array)]
    return len(array) >= 2 and len(np.unique(array)) >= 2


def kendall_tau_b(left: Iterable[float], right: Iterable[float]) -> float | None:
    x, y = _finite_pair(left, right)
    if not has_rank_variation(x) or not has_rank_variation(y):
        return None
    result = kendalltau(x, y, variant="b", nan_policy="omit")
    value = float(result.statistic)
    return value if isfinite(value) else None


def spearman_rho(left: Iterable[float], right: Iterable[float]) -> float | None:
    x, y = _finite_pair(left, right)
    if not has_rank_variation(x) or not has_rank_variation(y):
        return None
    value = float(spearmanr(x, y).statistic)
    return value if isfinite(value) else None


def midrank_percentiles(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if len(array) == 0 or not np.isfinite(array).all():
        raise ValueError("EXP2_MIDRANK_REQUIRES_FINITE_NONEMPTY_VALUES")
    return (rankdata(array, method="average") - 0.5) / len(array)


def top_k_ids(
    scores: Sequence[float], technical_ids: Sequence[str], fraction: float
) -> tuple[tuple[str, ...], int]:
    if len(scores) != len(technical_ids) or not scores:
        raise ValueError("EXP2_TOPK_INVALID_INPUT")
    if not 0 < fraction <= 1:
        raise ValueError("EXP2_TOPK_FRACTION_INVALID")
    rows = [
        (float(score), str(node_id)) for score, node_id in zip(scores, technical_ids)
    ]
    if any(not isfinite(score) for score, _ in rows):
        raise ValueError("EXP2_TOPK_REQUIRES_FINITE_SCORES")
    rows.sort(key=lambda item: (-item[0], item[1]))
    k = ceil(fraction * len(rows))
    cutoff = rows[k - 1][0]
    boundary_tie_count = sum(score == cutoff for score, _ in rows)
    return tuple(node_id for _, node_id in rows[:k]), boundary_tie_count


def priority_metrics(
    delay: Sequence[float],
    consequence: Sequence[float],
    technical_ids: Sequence[str],
    *,
    top_fraction: float = 0.10,
    material_gap: float = 0.30,
) -> dict[str, float | int | None]:
    if not (len(delay) == len(consequence) == len(technical_ids)) or not delay:
        raise ValueError("EXP2_PRIORITY_METRIC_INVALID_INPUT")
    delay_rank = midrank_percentiles(delay)
    consequence_rank = midrank_percentiles(consequence)
    displacement = np.abs(consequence_rank - delay_rank)
    signed = consequence_rank - delay_rank
    delay_top, delay_ties = top_k_ids(delay, technical_ids, top_fraction)
    consequence_top, consequence_ties = top_k_ids(
        consequence, technical_ids, top_fraction
    )
    k = len(delay_top)
    return {
        "n_nodes": len(delay),
        "kendall_tau_b": kendall_tau_b(delay, consequence),
        "median_rank_displacement": float(np.median(displacement)),
        "p90_rank_displacement": float(np.quantile(displacement, 0.90)),
        "share_rank_displacement_ge_030": float(np.mean(displacement >= material_gap)),
        "top_overlap": len(set(delay_top) & set(consequence_top)) / k,
        "spearman_rho": spearman_rho(delay, consequence),
        "share_signed_ge_030": float(np.mean(signed >= material_gap)),
        "share_signed_le_minus030": float(np.mean(signed <= -material_gap)),
        "delay_boundary_tie_count": delay_ties,
        "consequence_boundary_tie_count": consequence_ties,
    }
