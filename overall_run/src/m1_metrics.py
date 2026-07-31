from __future__ import annotations

import numpy as np


def pinball_loss(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    """Return row-level quantile loss for residual Y-Q."""
    residual = y - q
    return np.maximum(tau * residual, (tau - 1.0) * residual)


def approximate_crps(
    y: np.ndarray,
    qmat: np.ndarray,
    quantiles: np.ndarray,
) -> np.ndarray:
    """Integrate pinball loss over the configured nonuniform quantile grid."""
    losses = np.column_stack(
        [pinball_loss(y, qmat[:, index], float(tau)) for index, tau in enumerate(quantiles)]
    )
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    return 2.0 * integrate(losses, quantiles, axis=1)


def exceedance_probability_from_quantiles(
    qmat: np.ndarray,
    quantiles: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """Interpolate P(Y>threshold) from final monotone quantiles."""
    out = np.empty(len(qmat), dtype=float)
    for index, values in enumerate(qmat):
        values = np.asarray(values, dtype=float)
        unique_values, inverse = np.unique(values, return_inverse=True)
        probabilities = np.zeros(len(unique_values), dtype=float)
        for value_index in range(len(unique_values)):
            probabilities[value_index] = float(
                np.max(quantiles[inverse == value_index])
            )
        cdf = float(
            np.interp(threshold, unique_values, probabilities, left=0.0, right=1.0)
        )
        out[index] = 1.0 - cdf
    return np.clip(out, 0.0, 1.0)
