from __future__ import annotations

import numpy as np


def inverse_quantile_sample(
    qmat: np.ndarray,
    quantiles: np.ndarray,
    n_samples: int,
    seeds: np.ndarray,
) -> np.ndarray:
    """Sample each final quantile row using its frozen per-snapshot seed."""
    samples = np.empty((len(qmat), n_samples), dtype=np.float32)
    for index, seed in enumerate(seeds):
        rng = np.random.default_rng(int(seed))
        uniforms = rng.uniform(0.0, 1.0, size=n_samples)
        samples[index] = np.interp(
            uniforms,
            quantiles,
            qmat[index],
            left=float(qmat[index, 0]),
            right=float(qmat[index, -1]),
        ).astype(np.float32)
    return samples
