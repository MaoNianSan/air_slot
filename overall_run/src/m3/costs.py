from __future__ import annotations

import numpy as np

from ..utils import stable_seed
from .contracts import COST_CHANNELS, ActionCostSpec


def generate_implementation_costs(
    spec: ActionCostSpec,
    *,
    n_draws: int,
    base_seed: int,
    action_library_version: str,
    random_parameter_version: str,
) -> np.ndarray:
    if spec.action_id == "A00":
        return np.zeros((n_draws, len(COST_CHANNELS)), dtype=np.float64)
    if spec.cost_cv is None or any(spec.fixed_mean_rmb[channel] is None for channel in COST_CHANNELS):
        raise RuntimeError(f"M3_PARAMETER_NOT_FROZEN:{spec.action_id}:cost")
    if spec.cost_cv < 0.0 or any(float(spec.fixed_mean_rmb[channel]) < 0.0 for channel in COST_CHANNELS):
        raise ValueError(f"M3_COST_PARAMETER_INVALID:{spec.action_id}")
    rng = np.random.default_rng(stable_seed(
        base_seed,
        action_library_version,
        random_parameter_version,
        spec.action_id,
        "cost_shock",
    ))
    sigma2 = float(np.log1p(float(spec.cost_cv) ** 2))
    shock = rng.lognormal(mean=-0.5 * sigma2, sigma=np.sqrt(sigma2), size=n_draws)
    means = np.asarray([spec.fixed_mean_rmb[channel] for channel in COST_CHANNELS], dtype=float)
    return shock[:, None] * means[None, :]
