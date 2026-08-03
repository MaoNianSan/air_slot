from __future__ import annotations

import pandas as pd

from analysis.p1_event_reconstruction.contracts import AirportPoint, EventProviderContext
from analysis.p1_event_reconstruction.inference import ADSBEventTimeProvider


def provider() -> ADSBEventTimeProvider:
    return ADSBEventTimeProvider(EventProviderContext({"TEST": AirportPoint("TEST", 50.0, 8.0, 100.0)}))


def states(landing: bool = False) -> pd.DataFrame:
    base = 1_650_000_000
    if not landing:
        return pd.DataFrame({
            "time": [base + i * 10 for i in range(8)], "icao24": "abc123",
            "lat": [50.0, 50.0, 50.0, 50.001, 50.01, 50.03, 50.05, 50.08],
            "lon": [8.0] * 8, "velocity": [5, 8, 12, 35, 55, 75, 90, 105],
            "heading": 0.0, "vertrate": [0, 0, 0, .8, 1.5, 2, 3, 3],
            "callsign": "TEST1", "onground": [True, True, True, False, False, False, False, False],
            "alert": False, "spi": False, "squawk": "1234",
            "baroaltitude": [100, 100, 105, 120, 180, 260, 400, 600],
            "geoaltitude": [100, 100, 105, 120, 180, 260, 400, 600],
            "lastposupdate": [base + i * 10 for i in range(8)],
            "lastcontact": [base + i * 10 for i in range(8)],
        })
    return pd.DataFrame({
        "time": [base + i * 10 for i in range(8)], "icao24": "abc123",
        "lat": [50.08, 50.05, 50.03, 50.01, 50.002, 50.0, 50.0, 50.0],
        "lon": [8.0] * 8, "velocity": [105, 90, 75, 55, 35, 15, 8, 5],
        "heading": 180.0, "vertrate": [-3, -3, -2, -1.5, -.8, 0, 0, 0],
        "callsign": "TEST1", "onground": [False, False, False, False, False, True, True, True],
        "alert": False, "spi": False, "squawk": "1234",
        "baroaltitude": [600, 400, 260, 180, 120, 105, 100, 100],
        "geoaltitude": [600, 400, 260, 180, 120, 105, 100, 100],
        "lastposupdate": [base + i * 10 for i in range(8)],
        "lastcontact": [base + i * 10 for i in range(8)],
    })


def test_e1_departure_transition() -> None:
    result = provider().infer_departure_event(states(), "TEST", pd.Timestamp("2022-01-01", tz="UTC"))
    assert result.evidence_tier == "E1_ADSB_STATE_TRANSITION"
    assert result.is_supported


def test_e1_arrival_transition() -> None:
    result = provider().infer_arrival_event(states(landing=True), "TEST", pd.Timestamp("2022-01-01", tz="UTC"))
    assert result.evidence_tier == "E1_ADSB_STATE_TRANSITION"
    assert result.is_supported


def test_e3_fallback_is_explicit() -> None:
    result = provider().infer_departure_event(pd.DataFrame(), "TEST", pd.Timestamp("2022-01-01", tz="UTC"))
    assert result.evidence_tier == "E3_FLIGHTLIST_ENDPOINT"
    assert "OBSERVATION_ENDPOINT_PROXY_ONLY" in result.quality_flags

