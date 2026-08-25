import numpy as np

from .semantics import (
    DELAY_THRESHOLDS_MINUTES,
    EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES,
    FORMAL_FORECAST_HORIZONS_MINUTES,
)

HORIZONS = FORMAL_FORECAST_HORIZONS_MINUTES

MARGINAL_SUMMARY_TARGETS = ("R_IB", "D_OB", "D_TX", "D_TO")


def _weighted_empirical_quantile(values, weights, level: float) -> float:
    """Linear-interpolated weighted empirical quantile of a 1-D sample."""
    order = np.argsort(values)
    sorted_v = np.asarray(values, dtype=float)[order]
    sorted_w = np.asarray(weights, dtype=float)[order]
    total = float(sorted_w.sum())
    if total <= 0:
        raise ValueError("weighted empirical distribution has no mass")
    target = float(level) * total
    cdf = np.cumsum(sorted_w)
    index = int(np.searchsorted(cdf, target, side="left"))
    index = min(index, len(sorted_v) - 1)
    if index == 0:
        return float(sorted_v[0])
    cdf_lo = float(cdf[index - 1])
    cdf_hi = float(cdf[index])
    if cdf_hi <= cdf_lo:
        return float(sorted_v[index])
    fraction = (target - cdf_lo) / (cdf_hi - cdf_lo)
    return float(
        sorted_v[index - 1] + fraction * (sorted_v[index] - sorted_v[index - 1])
    )


def scenario_marginal_summary(
    scenarios,
    *,
    quantile_levels: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7, 0.9),
    targets: tuple[str, ...] = MARGINAL_SUMMARY_TARGETS,
):
    """Genuine marginal summaries from aligned V2 scenarios.

    The marginal distribution of each formal target is the EMPIRICAL WEIGHTED
    distribution of the aligned ancestral scenarios (manuscript scenario-state
    logic).  Quantiles are weighted empirical quantiles, the zero probability
    is the weighted frequency of exact zeros, and no weighted mean of
    CONDITIONAL quantile curves is ever labeled ``marginal`` here.

    A target abstains when no scenario carries a value for it; mixed
    abstention is NOT silently dropped (matching ``warning_probability``).
    """
    rows = tuple(scenarios)
    if not rows:
        return {
            name: _marginal_abstain(name, "NO_ALIGNED_SCENARIOS") for name in targets
        }
    attribute = {
        "R_IB": "r_ib_minutes",
        "D_OB": "d_ob_minutes",
        "D_TX": "d_tx_minutes",
        "D_TO": "d_to_minutes",
    }
    output = {}
    for name in targets:
        attr = attribute.get(name)
        if attr is None:
            raise ValueError(f"UNKNOWN_MARGINAL_TARGET:{name}")
        pairs = [
            (float(getattr(row, attr)), float(row.scenario_weight))
            for row in rows
            if getattr(row, attr) is not None
        ]
        if not pairs or len(pairs) != len(rows):
            output[name] = _marginal_abstain(name, "M1_V2_TARGET_UNAVAILABLE")
            continue
        values = np.asarray([item[0] for item in pairs], dtype=float)
        weights = np.asarray([item[1] for item in pairs], dtype=float)
        weight_sum = float(weights.sum())
        zero_probability = (
            float(weights[values == 0.0].sum() / weight_sum)
            if (values == 0.0).any()
            else 0.0
        )
        output[name] = {
            "target_name": name,
            "summary_kind": "SCENARIO_MARGINAL_SUMMARY",
            "support": "SUPPORTED",
            "weight_sum": weight_sum,
            "scenario_count": len(pairs),
            "quantiles_minutes": {
                str(level): _weighted_empirical_quantile(values, weights, level)
                for level in quantile_levels
            },
            "zero_probability": zero_probability,
            "mean_minutes": float((values * weights).sum() / weight_sum),
        }
    return output


def _marginal_abstain(name: str, reason: str) -> dict[str, object]:
    return {
        "target_name": name,
        "summary_kind": "SCENARIO_MARGINAL_SUMMARY",
        "support": "ABSTAIN",
        "reason_code": reason,
        "weight_sum": 0.0,
        "scenario_count": 0,
        "quantiles_minutes": None,
        "zero_probability": None,
        "mean_minutes": None,
    }


def horizon_summaries(
    scenarios_by_horizon,
    *,
    thresholds=DELAY_THRESHOLDS_MINUTES,
    horizons=FORMAL_FORECAST_HORIZONS_MINUTES,
):
    """Summarize formal horizons over V2 aligned scenarios.

    Consumes only V2 formal scenario quantities (T_IB_A00 / D_OB / D_TX /
    derived D_TO via ``M1V2Scenario``); legacy grids require explicit evaluation
    opt-in.  The horizon layer itself stays gated
    (``HORIZON_SEMANTICS_DECISION_REQUIRED``) until manuscript Eq. (18) semantics
    are uniquely resolved.
    """
    horizons = tuple(horizons)
    allowed = set(FORMAL_FORECAST_HORIZONS_MINUTES) | set(
        EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES
    )
    if not set(horizons) <= allowed:
        raise ValueError(f"UNKNOWN_FORECAST_HORIZON:{sorted(set(horizons) - allowed)}")
    unknown = set(scenarios_by_horizon) - set(horizons)
    if unknown:
        raise ValueError(f"UNKNOWN_FORECAST_HORIZON:{sorted(unknown)}")
    rows = []
    for horizon in horizons:
        scenarios = scenarios_by_horizon.get(horizon, ())
        for target, attribute in (
            ("R_IB", "r_ib_minutes"),
            ("D_OB", "d_ob_minutes"),
            ("D_TX", "d_tx_minutes"),
            ("D_TO", "d_to_minutes"),
        ):
            values = [
                getattr(row, attribute)
                for row in scenarios
                if getattr(row, attribute) is not None
            ]
            rows.append(
                {
                    "target_name": target,
                    "horizon_minutes": horizon,
                    "count": len(values),
                    "mean_minutes": float(np.mean(values)) if values else None,
                    "delay_probability": {
                        str(t): (
                            float(np.mean([value >= t for value in values]))
                            if values
                            else None
                        )
                        for t in thresholds
                    },
                }
            )
    return tuple(rows)
