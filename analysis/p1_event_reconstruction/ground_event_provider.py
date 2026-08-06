from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from .airport_spatial import best_runway
from .ground_event_rules import GroundEventRules, sustained_runs


@dataclass(frozen=True)
class GroundEventBundle:
    touchdown_time_proxy: pd.Timestamp | None
    runway_exit_time_proxy: pd.Timestamp | None
    taxi_in_end_time_proxy: pd.Timestamp | None
    parking_stop_time_proxy: pd.Timestamp | None
    taxi_out_start_time_proxy: pd.Timestamp | None
    runway_entry_time_proxy: pd.Timestamp | None
    liftoff_time_proxy: pd.Timestamp | None
    taxi_in_minutes: float | None
    service_or_stationary_minutes: float | None
    taxi_out_minutes: float | None
    landing_roll_minutes: float | None
    takeoff_roll_minutes: float | None
    total_ground_continuation_minutes: float | None
    event_evidence_tier: str
    event_confidence: float
    event_uncertainty_seconds: float
    coverage_status: str
    rule_id: str
    quality_flags: tuple[str, ...]


class GroundMovementEventProvider(Protocol):
    def infer_ground_events(self, states: pd.DataFrame, airport: str, touchdown: pd.Timestamp | None, liftoff: pd.Timestamp | None) -> GroundEventBundle: ...


class MultiSignalGroundEventProvider:
    def __init__(self, rules: GroundEventRules, runways: pd.DataFrame, parking_proxies: pd.DataFrame) -> None:
        self.rules = rules
        self.runways = runways
        self.parking_proxies = parking_proxies

    def infer_ground_events(self, states: pd.DataFrame, airport: str, touchdown: pd.Timestamp | None, liftoff: pd.Timestamp | None) -> GroundEventBundle:
        if states.empty or "event_time" not in states:
            return self._unsupported(touchdown, liftoff, "GROUND_PATH_INPUT_EMPTY")
        frame = states.sort_values("event_time").reset_index(drop=True).copy()
        if frame.empty or touchdown is None or liftoff is None:
            return self._unsupported(touchdown, liftoff, "RUNWAY_EVENTS_UNSUPPORTED")
        ground = frame.loc[frame.event_time.between(touchdown, liftoff)].copy().reset_index(drop=True)
        if ground.empty:
            return self._unsupported(touchdown, liftoff, "GROUND_INTERVAL_EMPTY")
        fresh = ground.position_age_seconds.le(self.rules.maximum_position_age_seconds) & ground.contact_age_seconds.le(self.rules.maximum_position_age_seconds)
        onground = ground.onground.astype("boolean").fillna(False)
        surface = onground & fresh & ground.distance_airport_km.le(self.rules.airport_geofence_km)
        surface_coverage = float(surface.mean())

        runway_set = self.runways.loc[self.runways.airport_ident.eq(airport)]
        arrival_probe = ground.iloc[: min(len(ground), 300)]
        departure_probe = ground.iloc[max(0, len(ground) - 300):]
        arrival_runway, arr_distance, arr_heading = best_runway(arrival_probe, runway_set)
        departure_runway, dep_distance, dep_heading = best_runway(departure_probe, runway_set)

        runway_exit = None
        runway_entry = None
        if arrival_runway is not None and len(arrival_probe):
            inside = (arr_distance <= self.rules.runway_corridor_km) & (arr_heading <= 35)
            for index in range(1, len(arrival_probe)):
                speed_low = pd.to_numeric(arrival_probe.velocity.iloc[index], errors="coerce") <= self.rules.movement_speed_mps * 3
                turned = arr_heading[index] > 35
                if inside[index - 1] and not inside[index] and surface.iloc[index] and (speed_low or turned):
                    runway_exit = arrival_probe.event_time.iloc[index]
                    break
        departure_inside = None
        if departure_runway is not None and len(departure_probe):
            departure_onground = departure_probe.onground.astype("boolean").fillna(False).to_numpy(dtype=bool)
            departure_inside = (dep_distance <= self.rules.runway_corridor_km) & (dep_heading <= 35) & departure_onground

        stationary_mask = (
            surface
            & ground.velocity.le(self.rules.stationary_speed_mps)
        )
        stationary_runs = sustained_runs(stationary_mask, ground.event_time, self.rules.minimum_stationary_seconds, self.rules.maximum_state_gap_seconds)
        eligible_runs = []
        proxies = self.parking_proxies.loc[self.parking_proxies.airport.eq(airport)]
        for start, end in stationary_runs:
            run = ground.iloc[start:end + 1]
            lat, lon = float(run.lat.median()), float(run.lon.median())
            near_proxy = False
            if not proxies.empty:
                dx = (proxies.longitude - lon) * 111 * np.cos(np.radians(lat))
                dy = (proxies.latitude - lat) * 111
                near_proxy = bool(np.sqrt(dx * dx + dy * dy).le(proxies.radius_km + .3).any())
            if near_proxy:
                eligible_runs.append((start, end, (ground.event_time.iloc[end] - ground.event_time.iloc[start]).total_seconds()))
        parking = max(eligible_runs, key=lambda value: value[2]) if eligible_runs else None
        taxi_in_end = ground.event_time.iloc[parking[0]] if parking else None
        taxi_out_start = None
        if parking:
            after = ground.iloc[parking[1] + 1:].copy()
            moving = surface.iloc[parking[1] + 1:] & after.velocity.ge(self.rules.hysteresis_exit_speed_mps)
            runs = sustained_runs(moving.reset_index(drop=True), after.event_time.reset_index(drop=True), self.rules.minimum_movement_seconds, self.rules.maximum_state_gap_seconds)
            if runs:
                taxi_out_start = after.event_time.iloc[runs[0][0]]

        if departure_inside is not None and departure_inside.any():
            eligible = np.flatnonzero(departure_inside)
            if taxi_out_start is not None:
                eligible = np.asarray([index for index in eligible if departure_probe.event_time.iloc[index] >= taxi_out_start], dtype=int)
            if len(eligible):
                segments = [int(eligible[0])]
                for previous, current in zip(eligible[:-1], eligible[1:]):
                    if current != previous + 1:
                        segments.append(int(current))
                runway_entry = departure_probe.event_time.iloc[segments[-1]]

        runway_supported = runway_exit is not None and runway_entry is not None
        arrival_supported = runway_exit is not None and taxi_in_end is not None
        departure_supported = taxi_out_start is not None and runway_entry is not None
        full = arrival_supported and departure_supported
        if full:
            coverage_status = "FULL_GROUND_PATH_SUPPORTED"
        elif arrival_supported:
            coverage_status = "ARRIVAL_GROUND_ONLY"
        elif departure_supported:
            coverage_status = "DEPARTURE_GROUND_ONLY"
        elif runway_supported:
            coverage_status = "RUNWAY_EVENTS_ONLY"
        elif touchdown is not None and liftoff is not None:
            coverage_status = "FLIGHTLIST_ENDPOINT_ONLY"
        else:
            coverage_status = "GROUND_COVERAGE_UNSUPPORTED"

        def minutes(end: pd.Timestamp | None, start: pd.Timestamp | None) -> float | None:
            return (end - start).total_seconds() / 60 if end is not None and start is not None and end >= start else None

        flags = []
        if surface_coverage < .5: flags.append("LOW_SURFACE_REPORT_COVERAGE")
        if arrival_runway is None or departure_runway is None: flags.append("RUNWAY_GEOMETRY_UNSUPPORTED")
        if parking is None: flags.append("FROZEN_PARKING_PROXY_NOT_REACHED")
        return GroundEventBundle(
            touchdown_time_proxy=touchdown, runway_exit_time_proxy=runway_exit,
            taxi_in_end_time_proxy=taxi_in_end, parking_stop_time_proxy=taxi_in_end,
            taxi_out_start_time_proxy=taxi_out_start, runway_entry_time_proxy=runway_entry,
            liftoff_time_proxy=liftoff,
            taxi_in_minutes=minutes(taxi_in_end, runway_exit),
            service_or_stationary_minutes=minutes(taxi_out_start, taxi_in_end),
            taxi_out_minutes=minutes(runway_entry, taxi_out_start),
            landing_roll_minutes=minutes(runway_exit, touchdown),
            takeoff_roll_minutes=minutes(liftoff, runway_entry),
            total_ground_continuation_minutes=minutes(liftoff, touchdown),
            event_evidence_tier="E1_GROUND_MULTI_SIGNAL" if runway_supported else "E1_RUNWAY_TRANSITIONS_ONLY",
            event_confidence=float(np.clip(.45 + .35 * surface_coverage + .1 * runway_supported + .1 * full, 0, .98)),
            event_uncertainty_seconds=max(30.0, self.rules.maximum_state_gap_seconds),
            coverage_status=coverage_status, rule_id=self.rules.rule_id,
            quality_flags=tuple(flags),
        )

    def _unsupported(self, touchdown: pd.Timestamp | None, liftoff: pd.Timestamp | None, flag: str) -> GroundEventBundle:
        return GroundEventBundle(touchdown, None, None, None, None, None, liftoff, None, None, None, None, None, None, "UNSUPPORTED", 0.0, float("nan"), "GROUND_COVERAGE_UNSUPPORTED", self.rules.rule_id, (flag,))
