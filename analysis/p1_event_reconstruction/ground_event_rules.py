from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class GroundEventRules:
    stationary_speed_mps: float
    movement_speed_mps: float
    takeoff_roll_speed_mps: float
    minimum_movement_seconds: float
    minimum_stationary_seconds: float
    runway_corridor_km: float
    airport_geofence_km: float
    maximum_state_gap_seconds: float
    maximum_position_age_seconds: float
    altitude_agl_limit_m: float
    vertical_rate_confirmation_mps: float
    hysteresis_exit_speed_mps: float
    fit_split: str = "DEVELOPMENT"
    rule_id: str = "GROUND_MULTI_SIGNAL_HYSTERESIS_DEV_FROZEN_V1"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def fit_development_rules(development_states: pd.DataFrame) -> GroundEventRules:
    ground = development_states.loc[
        development_states.onground.fillna(False)
        & development_states.velocity.notna()
        & development_states.position_age_seconds.le(30)
    ].copy()
    speeds = pd.to_numeric(ground.velocity, errors="coerce").dropna()
    if len(speeds) < 100:
        stationary, movement, takeoff = 1.5, 4.0, 35.0
    else:
        stationary = float(np.clip(speeds.quantile(.20), 0.8, 2.5))
        movement = float(np.clip(speeds.quantile(.45), stationary + 1.0, 8.0))
        takeoff = float(np.clip(speeds.quantile(.90), 25.0, 55.0))
    return GroundEventRules(
        stationary_speed_mps=stationary,
        movement_speed_mps=movement,
        takeoff_roll_speed_mps=takeoff,
        minimum_movement_seconds=30.0,
        minimum_stationary_seconds=60.0,
        runway_corridor_km=0.35,
        airport_geofence_km=15.0,
        maximum_state_gap_seconds=30.0,
        maximum_position_age_seconds=30.0,
        altitude_agl_limit_m=250.0,
        vertical_rate_confirmation_mps=0.3,
        hysteresis_exit_speed_mps=max(movement + 1.0, stationary + 2.0),
    )


def sustained_runs(mask: pd.Series, times: pd.Series, minimum_seconds: float, maximum_gap_seconds: float) -> list[tuple[int, int]]:
    values = mask.fillna(False).to_numpy(bool)
    stamps = pd.to_datetime(times, utc=True, errors="coerce").astype("int64").to_numpy() / 1e9
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        gap_ok = index == 0 or stamps[index] - stamps[index - 1] <= maximum_gap_seconds
        if value and gap_ok:
            start = index if start is None else start
        else:
            if start is not None and index - 1 > start and stamps[index - 1] - stamps[start] >= minimum_seconds:
                runs.append((start, index - 1))
            start = index if value else None
    if start is not None and len(values) - 1 > start and stamps[-1] - stamps[start] >= minimum_seconds:
        runs.append((start, len(values) - 1))
    return runs

