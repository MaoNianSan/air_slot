import numpy as np

HORIZONS=(0,30,60,120,180,240,300,360,420,480)


def horizon_summaries(scenarios_by_horizon, *, thresholds=(15,30,60)):
    """Summarize distributions evaluated at frozen decision horizons."""
    unknown=set(scenarios_by_horizon)-set(HORIZONS)
    if unknown:raise ValueError(f"UNKNOWN_FORECAST_HORIZON:{sorted(unknown)}")
    rows=[]
    for horizon in HORIZONS:
        scenarios=scenarios_by_horizon.get(horizon,())
        for target,attribute in (("R_IB","r_ib_minutes"),("R_OB","r_ob_minutes"),("T_TX","t_tx_minutes")):
            values=[getattr(row,attribute) for row in scenarios if getattr(row,attribute) is not None]
            rows.append({"target_name":target,"horizon_minutes":horizon,"count":len(values),
                "mean_minutes":float(np.mean(values)) if values else None,
                "delay_probability":{str(t):float(np.mean([value>=t for value in values])) if values else None for t in thresholds}})
    return tuple(rows)
