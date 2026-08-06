from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from .contracts import AirportPoint, EventProviderContext, EventTimeResult


E1_FIELDS = (
    "time", "icao24", "lat", "lon", "velocity", "heading", "vertrate",
    "onground", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact",
)


def haversine_km(lat: pd.Series, lon: pd.Series, point: AirportPoint) -> np.ndarray:
    lat1 = np.radians(pd.to_numeric(lat, errors="coerce"))
    lon1 = np.radians(pd.to_numeric(lon, errors="coerce"))
    lat0, lon0 = math.radians(point.latitude), math.radians(point.longitude)
    dlat, dlon = lat1 - lat0, lon1 - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * math.cos(lat0) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(1 - a, 0)))


def _empty(event_type: str, airport: str | None, flag: str) -> EventTimeResult:
    return EventTimeResult(
        event_time=None,
        event_type=event_type,
        evidence_tier="UNSUPPORTED",
        confidence=0.0,
        uncertainty_seconds=math.nan,
        airport=airport,
        quality_flags=(flag,),
        is_supported=False,
    )


class ADSBEventTimeProvider:
    """Infer event times from raw OpenSky state-vector sequences.

    Raw altitude and vertical-rate inputs follow the OpenSky sample contract:
    metres and metres/second. This prototype intentionally does not reuse the
    formal PRE unit conversion.
    """

    def __init__(self, context: EventProviderContext) -> None:
        self.context = context

    def _prepare(self, states: pd.DataFrame, airport: str | None) -> tuple[pd.DataFrame, AirportPoint | None]:
        if states.empty:
            return states.copy(), None
        frame = states.copy()
        frame["event_time"] = pd.to_datetime(frame["time"], unit="s", utc=True, errors="coerce")
        frame = frame.dropna(subset=["event_time"]).sort_values("event_time").drop_duplicates("event_time")
        for column in ["lat", "lon", "velocity", "vertrate", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact"]:
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame["onground"] = frame.get("onground", pd.Series(pd.NA, index=frame.index)).astype("boolean")
        frame["contact_age"] = frame.time - frame.lastcontact
        frame["position_age"] = frame.time - frame.lastposupdate
        point = self.context.airports.get(str(airport)) if airport else None
        frame["distance_km"] = haversine_km(frame.lat, frame.lon, point) if point else np.nan
        frame["height_agl_m"] = frame.baroaltitude - point.elevation_m if point else np.nan
        return frame.reset_index(drop=True), point

    @staticmethod
    def _sources(frame: pd.DataFrame) -> tuple[str, ...]:
        if "raw_source_file" not in frame:
            return ()
        return tuple(sorted(set(frame.raw_source_file.dropna().astype(str))))

    def infer_departure_event(
        self,
        states: pd.DataFrame,
        airport: str | None,
        fallback_time: pd.Timestamp | None,
    ) -> EventTimeResult:
        frame, point = self._prepare(states, airport)
        e1 = self._departure_e1(frame, point, airport)
        if e1.is_supported:
            return e1
        e2 = self._departure_e2(frame, point, airport)
        if e2.is_supported:
            return e2
        return self._e3("DEPARTURE", airport, fallback_time, frame, e1.quality_flags + e2.quality_flags)

    def infer_arrival_event(
        self,
        states: pd.DataFrame,
        airport: str | None,
        fallback_time: pd.Timestamp | None,
    ) -> EventTimeResult:
        frame, point = self._prepare(states, airport)
        e1 = self._arrival_e1(frame, point, airport)
        if e1.is_supported:
            return e1
        e2 = self._arrival_e2(frame, point, airport)
        if e2.is_supported:
            return e2
        return self._e3("ARRIVAL", airport, fallback_time, frame, e1.quality_flags + e2.quality_flags)

    def _departure_e1(self, frame: pd.DataFrame, point: AirportPoint | None, airport: str | None) -> EventTimeResult:
        if point is None:
            return _empty("DEPARTURE", airport, "AIRPORT_COORDINATES_MISSING")
        if len(frame) < 5 or frame.onground.notna().sum() < 2:
            return _empty("DEPARTURE", airport, "ONGROUND_SEQUENCE_INSUFFICIENT")
        ground = frame.onground.fillna(False).to_numpy(bool)
        candidates = np.flatnonzero(ground[:-1] & ~ground[1:]) + 1
        for index in candidates:
            before = frame.iloc[max(0, index - 60):index]
            after = frame.iloc[index:min(len(frame), index + 121)]
            transition_gap = (frame.event_time.iloc[index] - frame.event_time.iloc[index - 1]).total_seconds()
            sustained = int((after.onground == False).sum()) >= 3  # noqa: E712
            near = float(frame.distance_km.iloc[index]) <= 15 if pd.notna(frame.distance_km.iloc[index]) else False
            speed = float(after.velocity.median()) if after.velocity.notna().any() else math.nan
            climb = float(after.vertrate.median()) if after.vertrate.notna().any() else math.nan
            altitude_gain = float(after.baroaltitude.max() - before.baroaltitude.median()) if before.baroaltitude.notna().any() and after.baroaltitude.notna().any() else math.nan
            distance_gain = float(after.distance_km.max() - frame.distance_km.iloc[index]) if after.distance_km.notna().any() else math.nan
            fresh = float(frame.contact_age.iloc[index]) <= 15 and float(frame.position_age.iloc[index]) <= 30
            corroboration = sum([
                sustained,
                np.isfinite(speed) and speed >= 25,
                (np.isfinite(climb) and climb >= 0.3) or (np.isfinite(altitude_gain) and altitude_gain >= 45),
                np.isfinite(distance_gain) and distance_gain >= 1.0,
            ])
            if transition_gap <= 120 and near and fresh and corroboration >= 3:
                confidence = min(0.99, 0.78 + 0.05 * corroboration)
                return EventTimeResult(
                    event_time=frame.event_time.iloc[index], event_type="DEPARTURE",
                    evidence_tier="E1_ADSB_STATE_TRANSITION", confidence=confidence,
                    uncertainty_seconds=max(1.0, float(transition_gap)), airport=airport,
                    source_fields=E1_FIELDS, source_files=self._sources(frame),
                    rule_id="E1_DEP_GROUND_AIRBORNE_SUSTAINED_V1",
                    quality_flags=(), is_supported=True,
                )
        return _empty("DEPARTURE", airport, "NO_CORROBORATED_GROUND_TO_AIR_TRANSITION")

    def _arrival_e1(self, frame: pd.DataFrame, point: AirportPoint | None, airport: str | None) -> EventTimeResult:
        if point is None:
            return _empty("ARRIVAL", airport, "AIRPORT_COORDINATES_MISSING")
        if len(frame) < 5 or frame.onground.notna().sum() < 2:
            return _empty("ARRIVAL", airport, "ONGROUND_SEQUENCE_INSUFFICIENT")
        ground = frame.onground.fillna(False).to_numpy(bool)
        candidates = np.flatnonzero(~ground[:-1] & ground[1:]) + 1
        for index in candidates:
            before = frame.iloc[max(0, index - 121):index]
            after = frame.iloc[index:min(len(frame), index + 121)]
            transition_gap = (frame.event_time.iloc[index] - frame.event_time.iloc[index - 1]).total_seconds()
            sustained = int((after.onground == True).sum()) >= 3  # noqa: E712
            near = float(frame.distance_km.iloc[index]) <= 15 if pd.notna(frame.distance_km.iloc[index]) else False
            descent = float(before.vertrate.median()) if before.vertrate.notna().any() else math.nan
            speed_before = float(before.velocity.median()) if before.velocity.notna().any() else math.nan
            speed_after = float(after.velocity.median()) if after.velocity.notna().any() else math.nan
            height = float(frame.height_agl_m.iloc[index]) if pd.notna(frame.height_agl_m.iloc[index]) else math.nan
            fresh = float(frame.contact_age.iloc[index]) <= 15 and float(frame.position_age.iloc[index]) <= 30
            corroboration = sum([
                sustained,
                np.isfinite(descent) and descent <= -0.3,
                np.isfinite(speed_before) and np.isfinite(speed_after) and speed_after <= speed_before,
                np.isfinite(height) and height <= 300,
            ])
            if transition_gap <= 120 and near and fresh and corroboration >= 3:
                confidence = min(0.99, 0.78 + 0.05 * corroboration)
                return EventTimeResult(
                    event_time=frame.event_time.iloc[index], event_type="ARRIVAL",
                    evidence_tier="E1_ADSB_STATE_TRANSITION", confidence=confidence,
                    uncertainty_seconds=max(1.0, float(transition_gap)), airport=airport,
                    source_fields=E1_FIELDS, source_files=self._sources(frame),
                    rule_id="E1_ARR_AIRBORNE_GROUND_SUSTAINED_V1",
                    quality_flags=(), is_supported=True,
                )
        return _empty("ARRIVAL", airport, "NO_CORROBORATED_AIR_TO_GROUND_TRANSITION")

    def _departure_e2(self, frame: pd.DataFrame, point: AirportPoint | None, airport: str | None) -> EventTimeResult:
        if point is None or len(frame) < 5:
            return _empty("DEPARTURE", airport, "E2_INPUT_INSUFFICIENT")
        valid = frame[
            frame.distance_km.le(20)
            & frame.height_agl_m.le(900)
            & frame.velocity.ge(35)
            & (frame.vertrate.ge(0.5) | frame.height_agl_m.ge(120))
            & frame.contact_age.le(15)
            & frame.position_age.le(30)
        ]
        for index in valid.index:
            after = frame.iloc[index:min(len(frame), index + 181)]
            if len(after) < 3:
                continue
            distance_gain = float(after.distance_km.max() - frame.distance_km.iloc[index])
            altitude_gain = float(after.baroaltitude.max() - frame.baroaltitude.iloc[index])
            if distance_gain >= 2 and altitude_gain >= 60:
                return EventTimeResult(
                    event_time=frame.event_time.iloc[index], event_type="DEPARTURE",
                    evidence_tier="E2_TRAJECTORY_KINEMATIC", confidence=0.68,
                    uncertainty_seconds=120.0, airport=airport,
                    source_fields=("time", "lat", "lon", "velocity", "vertrate", "baroaltitude", "lastposupdate", "lastcontact"),
                    source_files=self._sources(frame), rule_id="E2_DEP_KINEMATIC_GEOFENCE_V1",
                    quality_flags=("ONGROUND_NOT_USED",), is_supported=True,
                )
        return _empty("DEPARTURE", airport, "NO_KINEMATIC_DEPARTURE_PATTERN")

    def _arrival_e2(self, frame: pd.DataFrame, point: AirportPoint | None, airport: str | None) -> EventTimeResult:
        if point is None or len(frame) < 5:
            return _empty("ARRIVAL", airport, "E2_INPUT_INSUFFICIENT")
        valid = frame[
            frame.distance_km.le(20)
            & frame.height_agl_m.le(900)
            & frame.vertrate.le(-0.3)
            & frame.contact_age.le(15)
            & frame.position_age.le(30)
        ]
        for index in reversed(valid.index.tolist()):
            before = frame.iloc[max(0, index - 181):index + 1]
            after = frame.iloc[index:min(len(frame), index + 181)]
            if len(before) < 3 or len(after) < 2:
                continue
            distance_drop = float(before.distance_km.max() - frame.distance_km.iloc[index])
            speed_drop = float(before.velocity.max() - after.velocity.min()) if before.velocity.notna().any() and after.velocity.notna().any() else math.nan
            if distance_drop >= 2 and np.isfinite(speed_drop) and speed_drop >= 20:
                return EventTimeResult(
                    event_time=frame.event_time.iloc[index], event_type="ARRIVAL",
                    evidence_tier="E2_TRAJECTORY_KINEMATIC", confidence=0.64,
                    uncertainty_seconds=180.0, airport=airport,
                    source_fields=("time", "lat", "lon", "velocity", "vertrate", "baroaltitude", "lastposupdate", "lastcontact"),
                    source_files=self._sources(frame), rule_id="E2_ARR_KINEMATIC_GEOFENCE_V1",
                    quality_flags=("ONGROUND_NOT_USED",), is_supported=True,
                )
        return _empty("ARRIVAL", airport, "NO_KINEMATIC_ARRIVAL_PATTERN")

    def _e3(
        self,
        event_type: str,
        airport: str | None,
        fallback_time: pd.Timestamp | None,
        frame: pd.DataFrame,
        flags: tuple[str, ...],
    ) -> EventTimeResult:
        value = pd.to_datetime(fallback_time, utc=True, errors="coerce")
        if pd.isna(value):
            return _empty(event_type, airport, "FLIGHTLIST_ENDPOINT_MISSING")
        return EventTimeResult(
            event_time=value, event_type=event_type,
            evidence_tier="E3_FLIGHTLIST_ENDPOINT", confidence=0.35,
            uncertainty_seconds=300.0, airport=airport,
            source_fields=("firstseen" if event_type == "DEPARTURE" else "lastseen",),
            source_files=self._sources(frame), rule_id=f"E3_{event_type}_FLIGHTLIST_ENDPOINT_V1",
            quality_flags=tuple(dict.fromkeys(flags + ("OBSERVATION_ENDPOINT_PROXY_ONLY",))),
            is_supported=True,
        )

