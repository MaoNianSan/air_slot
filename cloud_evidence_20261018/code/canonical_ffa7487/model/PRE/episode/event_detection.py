from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import asin, cos, radians, sin, sqrt
from typing import Any

from model.common.enums import SupportState

RULE_ID = "TRAJECTORY_OPERATIONAL_EVENT_TRANSITION"
RULE_VERSION = "1.0.0"


class MotionState(str, Enum):
    OFF = "S_OFF"
    STATIC = "S_STATIC"
    TAXI = "S_TAXI"
    AIR = "S_AIR"


@dataclass(frozen=True)
class TrajectoryDetectorConfig:
    eps_position_deg: float = 0.001
    v_static_mps: float = 1.0
    eps_altitude_m: float = 15.0
    v_taxi_min_mps: float = 5.0
    v_air_mps: float = 60.0
    gap_off_minutes: float = 10.0
    r_airport_km: float = 20.0
    w_seconds: float = 60.0

    def parameters(self) -> tuple[str, ...]:
        return (
            "eps_position_deg=0.001",
            "v_static_mps=1.0",
            "eps_altitude_m=15.0",
            "v_taxi_min_mps=5.0",
            "v_air_mps=60.0",
            "gap_off_minutes=10.0",
            "r_airport_km=20.0",
            "w_seconds=60.0",
        )


@dataclass(frozen=True)
class TrajectoryEventRecord:
    event_type: str
    event_time: datetime
    aircraft_id: str
    prev_time: datetime
    cur_time: datetime
    prev_state: MotionState
    cur_state: MotionState
    support_state: SupportState
    quality_flags: tuple[str, ...]
    detector_parameters: tuple[str, ...]
    rule_id: str = RULE_ID
    rule_version: str = RULE_VERSION
    reason_code: str | None = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _position_drift_deg(prev: dict[str, Any], cur: dict[str, Any]) -> float | None:
    if (
        prev.get("latitude_deg") is None
        or cur.get("latitude_deg") is None
        or prev.get("longitude_deg") is None
        or cur.get("longitude_deg") is None
    ):
        return None
    return max(
        abs(float(cur["latitude_deg"]) - float(prev["latitude_deg"])),
        abs(float(cur["longitude_deg"]) - float(prev["longitude_deg"])),
    )


def _altitude_drift_m(prev: dict[str, Any], cur: dict[str, Any]) -> float | None:
    prev_alt = prev.get("baro_altitude_m")
    if prev_alt is None:
        prev_alt = prev.get("geo_altitude_m")
    cur_alt = cur.get("baro_altitude_m")
    if cur_alt is None:
        cur_alt = cur.get("geo_altitude_m")
    if prev_alt is None or cur_alt is None:
        return None
    return abs(float(cur_alt) - float(prev_alt))


def _drift_per_window(
    value: float | None, seconds: float, window: float
) -> float | None:
    if value is None or seconds <= 0:
        return None
    return value * (window / seconds)


def classify_motion_state(
    prev: dict[str, Any],
    cur: dict[str, Any],
    config: TrajectoryDetectorConfig,
    next_within_window: dict[str, Any] | None = None,
) -> tuple[MotionState, tuple[str, ...]]:
    seconds = (cur["event_time"] - prev["event_time"]).total_seconds()
    if seconds > config.gap_off_minutes * 60:
        return MotionState.OFF, ()
    flags: list[str] = []
    on_ground = cur.get("on_ground")
    velocity = cur.get("velocity_mps")
    altitude = cur.get("baro_altitude_m")
    if altitude is None:
        altitude = cur.get("geo_altitude_m")
    drift_deg = _position_drift_deg(prev, cur)
    drift_60 = _drift_per_window(drift_deg, seconds, config.w_seconds)
    alt_drift_m = _altitude_drift_m(prev, cur)
    alt_drift_60 = _drift_per_window(alt_drift_m, seconds, config.w_seconds)
    if on_ground is True:
        if velocity is not None and float(velocity) < config.v_static_mps:
            return MotionState.STATIC, ()
        if velocity is not None and float(velocity) >= config.v_taxi_min_mps:
            return MotionState.TAXI, ()
        if drift_60 is not None and drift_60 < config.eps_position_deg:
            return MotionState.STATIC, ()
        return MotionState.TAXI, ()
    if on_ground is False:
        if altitude is not None and float(altitude) >= config.eps_altitude_m:
            return MotionState.AIR, ()
        if velocity is not None and float(velocity) >= config.v_air_mps:
            return MotionState.AIR, ()
        if velocity is not None and float(velocity) >= config.v_taxi_min_mps:
            return MotionState.TAXI, ()
        if (
            next_within_window is not None
            and next_within_window.get("on_ground") is False
        ):
            return MotionState.AIR, ("AIR_CONFIRMED_BY_FOLLOW_UP",)
        return MotionState.TAXI, ()
    if altitude is not None and float(altitude) >= config.eps_altitude_m:
        return MotionState.AIR, ("ONGROUND_MISSING_INFERRED",)
    if velocity is not None and float(velocity) >= config.v_air_mps:
        return MotionState.AIR, ("ONGROUND_MISSING_INFERRED",)
    if velocity is not None and float(velocity) < config.v_static_mps:
        return MotionState.STATIC, ("ONGROUND_MISSING_INFERRED",)
    return MotionState.TAXI, ("ONGROUND_MISSING_INFERRED",)


def _near_airport(
    lat: float | None,
    lon: float | None,
    airport_reference: tuple[tuple[float, float], ...] | None,
    radius_km: float,
) -> bool:
    if lat is None or lon is None or not airport_reference:
        return False
    return any(
        _haversine_km(lat, lon, a_lat, a_lon) <= radius_km
        for a_lat, a_lon in airport_reference
    )


def detect_operational_events(
    observations: list[dict[str, Any]],
    *,
    config: TrajectoryDetectorConfig | None = None,
    airport_reference: tuple[tuple[float, float], ...] | None = None,
) -> tuple[TrajectoryEventRecord, ...]:
    config = config or TrajectoryDetectorConfig()
    if len(observations) < 2:
        return ()
    ordered = sorted(
        observations,
        key=lambda row: (
            row["aircraft_id"],
            row["event_time"],
            str(row.get("_seq", "")),
        ),
    )
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in ordered:
        groups.setdefault(row["aircraft_id"], []).append(row)
    events: list[TrajectoryEventRecord] = []
    for aircraft_id, rows in groups.items():
        for index in range(len(rows) - 1):
            prev, cur = rows[index], rows[index + 1]
            nxt = rows[index + 2] if index + 2 < len(rows) else None
            seconds = (cur["event_time"] - prev["event_time"]).total_seconds()
            if seconds > config.gap_off_minutes * 60:
                power_off_near = _near_airport(
                    prev.get("latitude_deg"),
                    prev.get("longitude_deg"),
                    airport_reference,
                    config.r_airport_km,
                )
                power_on_near = _near_airport(
                    cur.get("latitude_deg"),
                    cur.get("longitude_deg"),
                    airport_reference,
                    config.r_airport_km,
                )
                if power_off_near:
                    events.append(
                        TrajectoryEventRecord(
                            event_type="POWER_OFF",
                            event_time=prev["event_time"],
                            aircraft_id=aircraft_id,
                            prev_time=prev["event_time"],
                            cur_time=cur["event_time"],
                            prev_state=MotionState.OFF,
                            cur_state=MotionState.OFF,
                            support_state=SupportState.SUPPORTED,
                            quality_flags=(),
                            detector_parameters=config.parameters(),
                        )
                    )
                else:
                    events.append(
                        TrajectoryEventRecord(
                            event_type="POWER_OFF",
                            event_time=prev["event_time"],
                            aircraft_id=aircraft_id,
                            prev_time=prev["event_time"],
                            cur_time=cur["event_time"],
                            prev_state=MotionState.OFF,
                            cur_state=MotionState.OFF,
                            support_state=SupportState.ABSTAIN,
                            quality_flags=("AIRPORT_RADIUS_OUT_OF_SCOPE",),
                            detector_parameters=config.parameters(),
                            reason_code="POWER_EVENT_AIRPORT_REFERENCE_REQUIRED",
                        )
                    )
                if power_on_near:
                    events.append(
                        TrajectoryEventRecord(
                            event_type="POWER_ON",
                            event_time=cur["event_time"],
                            aircraft_id=aircraft_id,
                            prev_time=prev["event_time"],
                            cur_time=cur["event_time"],
                            prev_state=MotionState.OFF,
                            cur_state=MotionState.OFF,
                            support_state=SupportState.SUPPORTED,
                            quality_flags=(),
                            detector_parameters=config.parameters(),
                        )
                    )
                else:
                    events.append(
                        TrajectoryEventRecord(
                            event_type="POWER_ON",
                            event_time=cur["event_time"],
                            aircraft_id=aircraft_id,
                            prev_time=prev["event_time"],
                            cur_time=cur["event_time"],
                            prev_state=MotionState.OFF,
                            cur_state=MotionState.OFF,
                            support_state=SupportState.ABSTAIN,
                            quality_flags=("AIRPORT_RADIUS_OUT_OF_SCOPE",),
                            detector_parameters=config.parameters(),
                            reason_code="POWER_EVENT_AIRPORT_REFERENCE_REQUIRED",
                        )
                    )
                continue
            prev_state, prev_flags = (
                classify_motion_state(
                    rows[index - 1] if index > 0 else prev, prev, config
                )
                if index > 0
                else (MotionState.STATIC, ())
            )
            cur_state, cur_flags = classify_motion_state(
                prev, cur, config, next_within_window=nxt
            )
            prev_on_ground = prev.get("on_ground")
            cur_on_ground = cur.get("on_ground")
            primary = None
            if (
                prev_on_ground is not None
                and cur_on_ground is not None
                and prev_on_ground != cur_on_ground
            ):
                primary = (
                    "TAKEOFF"
                    if (prev_on_ground is True and cur_on_ground is False)
                    else "LANDING"
                )
                mismatch = not (
                    (
                        primary == "TAKEOFF"
                        and prev_state in (MotionState.TAXI, MotionState.STATIC)
                        and cur_state is MotionState.AIR
                    )
                    or (
                        primary == "LANDING"
                        and prev_state is MotionState.AIR
                        and cur_state in (MotionState.TAXI, MotionState.STATIC)
                    )
                )
                flags = prev_flags + cur_flags
                if mismatch:
                    flags = flags + ("STATE_MACHINE_CROSSCHECK_MISMATCH",)
                events.append(
                    TrajectoryEventRecord(
                        event_type=primary,
                        event_time=cur["event_time"],
                        aircraft_id=aircraft_id,
                        prev_time=prev["event_time"],
                        cur_time=cur["event_time"],
                        prev_state=prev_state,
                        cur_state=cur_state,
                        support_state=(
                            SupportState.DEGRADED
                            if mismatch
                            else SupportState.SUPPORTED
                        ),
                        quality_flags=tuple(sorted(set(flags))),
                        detector_parameters=config.parameters(),
                        reason_code=(
                            "STATE_MACHINE_CROSSCHECK_MISMATCH" if mismatch else None
                        ),
                    )
                )
                continue
            if prev_on_ground is None or cur_on_ground is None:
                inferred = None
                if prev_state is MotionState.TAXI and cur_state is MotionState.AIR:
                    inferred = "TAKEOFF"
                elif prev_state is MotionState.AIR and cur_state is MotionState.TAXI:
                    inferred = "LANDING"
                if inferred is not None:
                    events.append(
                        TrajectoryEventRecord(
                            event_type=inferred,
                            event_time=cur["event_time"],
                            aircraft_id=aircraft_id,
                            prev_time=prev["event_time"],
                            cur_time=cur["event_time"],
                            prev_state=prev_state,
                            cur_state=cur_state,
                            support_state=SupportState.DEGRADED,
                            quality_flags=tuple(
                                sorted(
                                    set(
                                        prev_flags
                                        + cur_flags
                                        + ("ONGROUND_MISSING_INFERRED",)
                                    )
                                )
                            ),
                            detector_parameters=config.parameters(),
                            reason_code="ONGROUND_MISSING_STATE_MACHINE_INFERENCE",
                        )
                    )
                    continue
            if prev_state is MotionState.STATIC and cur_state is MotionState.TAXI:
                events.append(
                    TrajectoryEventRecord(
                        event_type="OUT_BLOCK_PROXY",
                        event_time=cur["event_time"],
                        aircraft_id=aircraft_id,
                        prev_time=prev["event_time"],
                        cur_time=cur["event_time"],
                        prev_state=prev_state,
                        cur_state=cur_state,
                        support_state=SupportState.SUPPORTED,
                        quality_flags=tuple(sorted(set(prev_flags + cur_flags))),
                        detector_parameters=config.parameters(),
                    )
                )
            elif prev_state is MotionState.TAXI and cur_state is MotionState.STATIC:
                events.append(
                    TrajectoryEventRecord(
                        event_type="IN_BLOCK_PROXY",
                        event_time=cur["event_time"],
                        aircraft_id=aircraft_id,
                        prev_time=prev["event_time"],
                        cur_time=cur["event_time"],
                        prev_state=prev_state,
                        cur_state=cur_state,
                        support_state=SupportState.SUPPORTED,
                        quality_flags=tuple(sorted(set(prev_flags + cur_flags))),
                        detector_parameters=config.parameters(),
                    )
                )
    return tuple(events)
