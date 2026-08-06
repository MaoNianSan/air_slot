from __future__ import annotations

import hashlib

import numpy as np

from .bins import DiscreteBins


def fixed_uniform(
    episode_id: str,
    sample_id: int,
    target_name: str,
    base_seed: int,
) -> float:
    payload = f"{episode_id}|{sample_id}|{target_name}|{base_seed}".encode("utf-8")
    integer = int(hashlib.sha256(payload).hexdigest()[:13], 16)
    return (integer + 0.5) / float(16**13)


def fixed_uniform_purpose(
    episode_id: str,
    sample_id: int,
    target_name: str,
    base_seed: int,
    purpose: str,
) -> float:
    payload = f"{episode_id}|{sample_id}|{target_name}|{base_seed}|{purpose}".encode("utf-8")
    integer = int(hashlib.sha256(payload).hexdigest()[:13], 16)
    return (integer + 0.5) / float(16**13)


def sample_overflow(
    lower_bound: float,
    tail_values: tuple[float, ...],
    *,
    episode_id: str,
    sample_id: int,
    target_name: str,
    base_seed: int,
) -> tuple[float, str]:
    if not tail_values:
        return float("nan"), "TAIL_UNRESOLVED"
    uniform = fixed_uniform_purpose(episode_id, sample_id, target_name, base_seed, "OVERFLOW_TAIL")
    index = min(int(uniform * len(tail_values)), len(tail_values) - 1)
    return max(float(lower_bound), float(tail_values[index])), "RESOLVED"


def sample_discrete(
    probabilities: np.ndarray,
    bins: DiscreteBins,
    uniform: float,
    *,
    within_uniform: float | None = None,
    overflow_tail_values: tuple[float, ...] = (),
    episode_id: str = "",
    sample_id: int = 0,
    target_name: str = "",
    base_seed: int = 0,
) -> tuple[float, bool]:
    probs = np.asarray(probabilities, dtype=float)
    if probs.ndim != 1 or len(probs) != bins.count:
        raise ValueError("M1_SAMPLING_SHAPE_INVALID")
    if not np.isfinite(probs).all() or (probs < 0).any() or probs.sum() <= 0:
        raise ValueError("M1_SAMPLING_PROBABILITY_INVALID")
    if not 0.0 < uniform < 1.0:
        raise ValueError("M1_SAMPLING_UNIFORM_INVALID")
    probs = probs / probs.sum()
    index = int(np.searchsorted(np.cumsum(probs), uniform, side="right"))
    index = min(index, len(probs) - 1)
    lower = float(bins.lower_minutes[index])
    upper = bins.upper_minutes[index]
    if upper is None:
        value, status = sample_overflow(
            lower, overflow_tail_values, episode_id=episode_id,
            sample_id=sample_id, target_name=target_name, base_seed=base_seed,
        )
        if status == "TAIL_UNRESOLVED":
            return value, True
        return value, True
    draw = within_uniform if within_uniform is not None else fixed_uniform_purpose(
        episode_id, sample_id, target_name, base_seed, "WITHIN_BIN"
    )
    value = lower + float(draw) * (float(upper) - lower)
    return min(value, np.nextafter(float(upper), lower)), False
