from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_distribution

from .m4_pnb_contract import AUDIT_SEED_NAMESPACE, CHANNELS
from .utils import stable_seed


def nonnull_triggered_rows(candidates: pd.DataFrame) -> pd.DataFrame:
    return candidates[
        candidates["trigger"].astype(bool) & candidates["action_id"].ne("A00")
    ].copy()


def manual_pnb_reconstruction(
    pre_costs_rmb: Mapping[str, np.ndarray],
    recovery_rates: Mapping[str, np.ndarray],
    implementation_costs_rmb: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    if set(pre_costs_rmb) != set(CHANNELS):
        raise ValueError("PNB_PRE_CHANNEL_SET_INVALID")
    if set(recovery_rates) != set(CHANNELS):
        raise ValueError("PNB_RECOVERY_CHANNEL_SET_INVALID")
    if set(implementation_costs_rmb) != set(CHANNELS):
        raise ValueError("PNB_IMPLEMENTATION_CHANNEL_SET_INVALID")
    lengths = {
        len(np.asarray(values))
        for mapping in (pre_costs_rmb, recovery_rates, implementation_costs_rmb)
        for values in mapping.values()
    }
    if len(lengths) != 1:
        raise ValueError("PNB_SAMPLE_SHAPE_MISMATCH")
    recovered_by_channel = {
        channel: np.asarray(recovery_rates[channel], dtype=float)
        * np.asarray(pre_costs_rmb[channel], dtype=float)
        for channel in CHANNELS
    }
    implementation_by_channel = {
        channel: np.asarray(implementation_costs_rmb[channel], dtype=float)
        for channel in CHANNELS
    }
    recovered_total = sum(recovered_by_channel.values())
    implementation_total = sum(implementation_by_channel.values())
    pre_total = sum(np.asarray(pre_costs_rmb[channel], dtype=float) for channel in CHANNELS)
    net_benefit = recovered_total - implementation_total
    post_action_total = pre_total - recovered_total + implementation_total
    expected_pre = float(pre_total.mean())
    expected_recovered = float(recovered_total.mean())
    expected_implementation = float(implementation_total.mean())
    recovery_ratio = expected_recovered / max(expected_pre, 1e-9)
    burden_ratio = (
        expected_implementation / expected_recovered
        if expected_recovered > 1e-9
        else np.inf
    )
    return {
        "pre_total": pre_total,
        "recovered_by_channel": recovered_by_channel,
        "recovered_total": recovered_total,
        "implementation_by_channel": implementation_by_channel,
        "implementation_total": implementation_total,
        "net_benefit": net_benefit,
        "post_action_total": post_action_total,
        "expected_pre_action_cost_rmb": expected_pre,
        "expected_recovered_cost_rmb": expected_recovered,
        "expected_implementation_cost_rmb": expected_implementation,
        "expected_net_benefit_rmb": float(net_benefit.mean()),
        "recovery_ratio": recovery_ratio,
        "burden_ratio": burden_ratio,
        "positive_net_benefit_probability": float((net_benefit > 0.0).mean()),
        "nonnegative_net_benefit_probability": float((net_benefit >= 0.0).mean()),
        "strict_vs_nonstrict_equal_draws": int((net_benefit == 0.0).sum()),
    }


def risk_score(values: np.ndarray, risk_aversion: float, cvar_alpha: float) -> float:
    values = np.asarray(values, dtype=float)
    threshold = float(np.quantile(values, cvar_alpha))
    tail = values[values >= threshold]
    cvar = float(tail.mean()) if len(tail) else threshold
    return float((1.0 - risk_aversion) * values.mean() + risk_aversion * cvar)


def generate_audit_m3_library(
    parameters: pd.DataFrame,
    n_samples: int,
    base_seed: int,
    replicate: int = 0,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    recovery: dict[str, np.ndarray] = {}
    implementation: dict[str, np.ndarray] = {}
    success_map: dict[str, np.ndarray] = {}
    for row in parameters.sort_values("action_id").itertuples(index=False):
        action_id = str(row.action_id)
        eta = np.zeros((n_samples, len(CHANNELS)), dtype=np.float32)
        costs = np.zeros_like(eta)
        if action_id == "A00":
            success = np.ones(n_samples, dtype=bool)
        else:
            prefix = (base_seed, AUDIT_SEED_NAMESPACE, replicate, action_id)
            success_rng = np.random.default_rng(stable_seed(*prefix, "success"))
            rank_rng = np.random.default_rng(stable_seed(*prefix, "recovery_rank"))
            cost_rng = np.random.default_rng(stable_seed(*prefix, "cost_shock"))
            success = success_rng.random(n_samples) >= float(row.failure_probability)
            ranks = np.clip(rank_rng.random(n_samples), 1e-12, 1.0 - 1e-12)
            concentration = float(row.recovery_concentration)
            for index, channel in enumerate(CHANNELS):
                mean = float(getattr(row, f"mu_{channel}"))
                if mean <= 0.0:
                    draws = np.zeros(n_samples)
                elif mean >= 1.0:
                    draws = np.ones(n_samples)
                else:
                    draws = beta_distribution.ppf(
                        ranks, mean * concentration, (1.0 - mean) * concentration
                    )
                eta[:, index] = np.where(success, draws, 0.0).astype(np.float32)
            cv = float(row.cost_cv)
            sigma2 = float(np.log1p(cv * cv))
            shocks = cost_rng.lognormal(
                mean=-0.5 * sigma2, sigma=float(np.sqrt(sigma2)), size=n_samples
            )
            for index, channel in enumerate(CHANNELS):
                costs[:, index] = (
                    float(getattr(row, f"kbar_rmb_{channel}")) * shocks
                ).astype(np.float32)
        recovery[action_id] = eta
        implementation[action_id] = costs
        success_map[action_id] = success
    return recovery, implementation, success_map


