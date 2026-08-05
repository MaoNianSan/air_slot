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


def sample_discrete(probabilities: np.ndarray, bins: DiscreteBins, uniform: float) -> tuple[float, bool]:
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
    return float(bins.lower_minutes[index]), bins.upper_minutes[index] is None
