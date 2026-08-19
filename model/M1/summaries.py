import numpy as np

from .semantics import (
    DELAY_THRESHOLDS_MINUTES,
    EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES,
    FORMAL_FORECAST_HORIZONS_MINUTES,
)

HORIZONS = FORMAL_FORECAST_HORIZONS_MINUTES


def horizon_summaries(scenarios_by_horizon, *, thresholds=DELAY_THRESHOLDS_MINUTES,
                      horizons=FORMAL_FORECAST_HORIZONS_MINUTES):
    """Summarize formal horizons; legacy grids require explicit evaluation opt-in."""
    horizons = tuple(horizons)
    allowed = set(FORMAL_FORECAST_HORIZONS_MINUTES) | set(EVALUATION_ONLY_FORECAST_HORIZONS_MINUTES)
    if not set(horizons) <= allowed:
        raise ValueError(f"UNKNOWN_FORECAST_HORIZON:{sorted(set(horizons) - allowed)}")
    unknown=set(scenarios_by_horizon)-set(horizons)
    if unknown:raise ValueError(f"UNKNOWN_FORECAST_HORIZON:{sorted(unknown)}")
    rows=[]
    for horizon in horizons:
        scenarios=scenarios_by_horizon.get(horizon,())
        for target,attribute in (
            ("R_IB","r_ib_minutes"),
            ("D_OB","d_ob_minutes"),
            ("D_TX","d_tx_minutes"),
            ("D_TO","d_to_minutes"),
        ):
            values=[getattr(row,attribute) for row in scenarios if getattr(row,attribute) is not None]
            rows.append({"target_name":target,"horizon_minutes":horizon,"count":len(values),
                "mean_minutes":float(np.mean(values)) if values else None,
                "delay_probability":{str(t):float(np.mean([value>=t for value in values])) if values else None for t in thresholds}})
    return tuple(rows)
