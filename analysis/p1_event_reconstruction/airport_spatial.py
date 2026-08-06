from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a1, a2 = math.radians(lat1), math.radians(lat2)
    delta = math.radians(lon2 - lon1)
    x = math.sin(delta) * math.cos(a2)
    y = math.cos(a1) * math.sin(a2) - math.sin(a1) * math.cos(a2) * math.cos(delta)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def build_runway_geometries(root: Path, airports: list[str]) -> pd.DataFrame:
    path = root / "data/raw/ourairports/snapshot=2021-12-31/runways.csv"
    frame = pd.read_csv(path, low_memory=False)
    frame = frame.loc[frame.airport_ident.isin(airports) & frame.closed.fillna(0).eq(0)].copy()
    required = ["le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg"]
    frame = frame.dropna(subset=required)
    frame["runway_heading_deg"] = frame.apply(
        lambda row: bearing_degrees(row.le_latitude_deg, row.le_longitude_deg, row.he_latitude_deg, row.he_longitude_deg), axis=1
    )
    frame["runway_length_m"] = pd.to_numeric(frame.length_ft, errors="coerce") * 0.3048
    frame["geometry_support"] = "ENDPOINTS_AND_HEADING"
    columns = [
        "airport_ident", "le_ident", "he_ident", *required, "runway_heading_deg",
        "runway_length_m", "width_ft", "surface", "lighted", "geometry_support",
    ]
    return frame[columns].sort_values(["airport_ident", "le_ident", "he_ident"]).reset_index(drop=True)


def _local_xy(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> tuple[np.ndarray, np.ndarray]:
    x = (lon - lon0) * 111.0 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 111.0
    return x, y


def point_to_runway_km(lat: pd.Series, lon: pd.Series, runway: pd.Series) -> np.ndarray:
    lat0 = (float(runway.le_latitude_deg) + float(runway.he_latitude_deg)) / 2
    lon0 = (float(runway.le_longitude_deg) + float(runway.he_longitude_deg)) / 2
    px, py = _local_xy(pd.to_numeric(lat, errors="coerce").to_numpy(float), pd.to_numeric(lon, errors="coerce").to_numpy(float), lat0, lon0)
    ax, ay = _local_xy(np.array([float(runway.le_latitude_deg)]), np.array([float(runway.le_longitude_deg)]), lat0, lon0)
    bx, by = _local_xy(np.array([float(runway.he_latitude_deg)]), np.array([float(runway.he_longitude_deg)]), lat0, lon0)
    vx, vy = bx[0] - ax[0], by[0] - ay[0]
    denominator = vx * vx + vy * vy
    t = np.clip(((px - ax[0]) * vx + (py - ay[0]) * vy) / denominator, 0, 1) if denominator else np.zeros_like(px)
    dx, dy = px - (ax[0] + t * vx), py - (ay[0] + t * vy)
    return np.sqrt(dx * dx + dy * dy)


def heading_difference(track: pd.Series, runway_heading: float) -> np.ndarray:
    values = pd.to_numeric(track, errors="coerce").to_numpy(float)
    forward = np.abs((values - runway_heading + 180) % 360 - 180)
    reverse = np.abs((values - ((runway_heading + 180) % 360) + 180) % 360 - 180)
    return np.minimum(forward, reverse)


def best_runway(states: pd.DataFrame, runways: pd.DataFrame) -> tuple[pd.Series | None, np.ndarray, np.ndarray]:
    if states.empty or runways.empty:
        return None, np.full(len(states), np.nan), np.full(len(states), np.nan)
    candidates = []
    for _, runway in runways.iterrows():
        distance = point_to_runway_km(states.lat, states.lon, runway)
        heading = heading_difference(states.heading, float(runway.runway_heading_deg))
        score = float(np.nanmedian(distance)) + float(np.nanmedian(heading)) / 180
        candidates.append((score, runway, distance, heading))
    _, runway, distance, heading = min(candidates, key=lambda item: item[0])
    return runway, distance, heading

