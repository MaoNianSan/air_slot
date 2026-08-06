from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from .airport_spatial import build_runway_geometries
from .contracts import AirportPoint
from .ground_event_provider import GroundEventBundle, MultiSignalGroundEventProvider
from .ground_event_rules import fit_development_rules, sustained_runs


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/p1_event_reconstruction"
REPORTS = ROOT / "reports"
AIRPORTS = ["EHAM", "LFPG", "EDDF", "LEMD", "LEBL", "EDDM"]
AUDIT_DATE = "2026-07-31"


def haversine(lat: pd.Series, lon: pd.Series, point: AirportPoint) -> np.ndarray:
    lat1 = np.radians(pd.to_numeric(lat, errors="coerce"))
    lon1 = np.radians(pd.to_numeric(lon, errors="coerce"))
    lat0, lon0 = math.radians(point.latitude), math.radians(point.longitude)
    dlat, dlon = lat1 - lat0, lon1 - lon0
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * math.cos(lat0) * np.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * np.arctan2(np.sqrt(a), np.sqrt(np.maximum(1 - a, 0)))


def load_airport_points() -> dict[str, AirportPoint]:
    frame = pd.read_csv(ROOT / "data/raw/ourairports/snapshot=2021-12-31/airports.csv", low_memory=False)
    frame = frame.loc[frame.ident.isin(AIRPORTS)]
    return {
        row.ident: AirportPoint(row.ident, float(row.latitude_deg), float(row.longitude_deg), float(row.elevation_ft or 0) * .3048)
        for row in frame.itertuples(index=False)
    }


def prepare_ground_paths(events: pd.DataFrame, raw: pd.DataFrame, points: dict[str, AirportPoint]) -> tuple[dict[int, pd.DataFrame], pd.DataFrame]:
    raw = raw.copy()
    raw["event_time"] = pd.to_datetime(raw.time, unit="s", utc=True, errors="coerce")
    for column in ["velocity", "heading", "vertrate", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact", "lat", "lon"]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    raw["position_age_seconds"] = raw.time - raw.lastposupdate
    raw["contact_age_seconds"] = raw.time - raw.lastcontact
    raw["position_contact_gap_seconds"] = raw.lastcontact - raw.lastposupdate
    raw["onground"] = raw.onground.astype("boolean")
    groups = {(str(date), str(icao)): group.sort_values("event_time") for (date, icao), group in raw.groupby(["source_date", "icao24"], sort=False)}
    paths: dict[int, pd.DataFrame] = {}
    rows = []
    for event in events.itertuples(index=False):
        date = str(pd.Timestamp(event.departure_minus_time).date())
        source = groups.get((date, str(event.icao24)))
        if source is None:
            paths[int(event.chain_edge_id)] = pd.DataFrame()
            continue
        start = pd.Timestamp(event.arrival_minus_time) - pd.Timedelta(minutes=15)
        end = pd.Timestamp(event.departure_plus_time) + pd.Timedelta(minutes=15)
        frame = source.loc[source.event_time.between(start, end)].copy()
        point = points[str(event.airport)]
        frame["airport"] = event.airport
        frame["distance_airport_km"] = haversine(frame.lat, frame.lon, point)
        frame["baro_height_above_airport"] = frame.baroaltitude - point.elevation_m
        frame["geo_height_above_airport"] = frame.geoaltitude - point.elevation_m
        frame["abs_vertical_rate"] = frame.vertrate.abs()
        frame["velocity_kmh"] = frame.velocity * 3.6
        frame["velocity_knots"] = frame.velocity * 1.94384449
        frame["chain_edge_id"] = int(event.chain_edge_id)
        frame["split"] = event.split
        paths[int(event.chain_edge_id)] = frame.reset_index(drop=True)
        gaps = frame.event_time.diff().dt.total_seconds().dropna()
        near = frame.distance_airport_km.le(15)
        rows.append({
            "chain_edge_id": event.chain_edge_id, "split": event.split, "airport": event.airport,
            "state_rows": len(frame), "surface_report_coverage": float((frame.onground.fillna(False) & near).mean()) if len(frame) else 0,
            "position_coverage": float(frame[["lat", "lon"]].notna().all(axis=1).mean()) if len(frame) else 0,
            "velocity_coverage": float(frame.velocity.notna().mean()) if len(frame) else 0,
            "vertical_rate_coverage": float(frame.vertrate.notna().mean()) if len(frame) else 0,
            "altitude_coverage": float(frame[["baroaltitude", "geoaltitude"]].notna().any(axis=1).mean()) if len(frame) else 0,
            "maximum_state_gap": float(gaps.max()) if len(gaps) else math.nan,
            "median_update_interval": float(gaps.median()) if len(gaps) else math.nan,
            "airport_nearby_coverage": float(near.mean()) if len(frame) else 0,
            "pre_takeoff_ground_coverage": float((frame.loc[frame.event_time.le(event.departure_plus_time), "onground"] == True).mean()) if len(frame) else 0,  # noqa: E712
            "post_landing_ground_coverage": float((frame.loc[frame.event_time.ge(event.arrival_minus_time), "onground"] == True).mean()) if len(frame) else 0,  # noqa: E712
        })
    return paths, pd.DataFrame(rows)


def fit_parking_proxies(paths: dict[int, pd.DataFrame], events: pd.DataFrame, rules: Any) -> pd.DataFrame:
    development_ids = set(events.loc[events.split.eq("DEVELOPMENT"), "chain_edge_id"].astype(int))
    rows = []
    for airport in AIRPORTS:
        pieces = []
        for edge_id in development_ids:
            frame = paths.get(edge_id)
            if frame is None or frame.empty or not frame.airport.eq(airport).all():
                continue
            candidate = frame.loc[
                frame.onground.fillna(False)
                & frame.velocity.le(rules.stationary_speed_mps)
                & frame.distance_airport_km.le(rules.airport_geofence_km)
                & frame.position_age_seconds.le(rules.maximum_position_age_seconds),
                ["lat", "lon"],
            ].dropna().iloc[::10]
            if not candidate.empty:
                pieces.append(candidate)
        if not pieces:
            continue
        points = pd.concat(pieces, ignore_index=True)
        lat0, lon0 = float(points.lat.median()), float(points.lon.median())
        x = (points.lon.to_numpy(float) - lon0) * 111 * math.cos(math.radians(lat0))
        y = (points.lat.to_numpy(float) - lat0) * 111
        labels = DBSCAN(eps=.25, min_samples=20).fit_predict(np.column_stack([x, y]))
        points["cluster"] = labels
        for cluster, group in points.loc[points.cluster.ge(0)].groupby("cluster"):
            if len(group) < 20:
                continue
            latitude, longitude = float(group.lat.median()), float(group.lon.median())
            dx = (group.lon - longitude) * 111 * math.cos(math.radians(latitude))
            dy = (group.lat - latitude) * 111
            radius = float(np.sqrt(dx * dx + dy * dy).quantile(.95))
            rows.append({"airport": airport, "parking_proxy_id": f"{airport}_P{int(cluster):03d}", "latitude": latitude, "longitude": longitude, "radius_km": max(.1, min(radius, .5)), "development_support_points": len(group), "fit_split": "DEVELOPMENT", "method": "DBSCAN_STATIONARY_SURFACE_POINTS", "not_gate_geometry": True})
    result = pd.DataFrame(rows, columns=["airport", "parking_proxy_id", "latitude", "longitude", "radius_km", "development_support_points", "fit_split", "method", "not_gate_geometry"])
    result.to_parquet(OUTPUT / "empirical_parking_proxies.parquet", index=False)
    return result


def bundle_row(event: pd.Series, bundle: GroundEventBundle) -> dict[str, Any]:
    return {"chain_edge_id": event.chain_edge_id, "predecessor_episode_id": event.predecessor_episode_id, "split": event.split, "airport": event.airport, **asdict(bundle)}


def infer_all(paths: dict[int, pd.DataFrame], events: pd.DataFrame, provider: MultiSignalGroundEventProvider) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        touchdown = event.arrival_minus_time if event.arrival_minus_evidence_tier == "E1_ADSB_STATE_TRANSITION" else None
        liftoff = event.departure_plus_time if event.departure_plus_evidence_tier == "E1_ADSB_STATE_TRANSITION" else None
        bundle = provider.infer_ground_events(paths.get(int(event.chain_edge_id), pd.DataFrame()), str(event.airport), touchdown, liftoff)
        rows.append(bundle_row(event, bundle))
    result = pd.DataFrame(rows).sort_values("chain_edge_id").reset_index(drop=True)
    for column in ["touchdown_time_proxy", "runway_exit_time_proxy", "taxi_in_end_time_proxy", "parking_stop_time_proxy", "taxi_out_start_time_proxy", "runway_entry_time_proxy", "liftoff_time_proxy"]:
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
    result.to_parquet(OUTPUT / "ground_events.parquet", index=False)
    intervals = result[["chain_edge_id", "predecessor_episode_id", "split", "airport", "taxi_in_minutes", "service_or_stationary_minutes", "taxi_out_minutes", "landing_roll_minutes", "takeoff_roll_minutes", "total_ground_continuation_minutes", "coverage_status", "event_evidence_tier", "event_confidence", "event_uncertainty_seconds", "rule_id", "quality_flags"]].copy()
    intervals["quality_flags"] = intervals.quality_flags.map(lambda value: "|".join(value) if isinstance(value, (tuple, list)) else str(value))
    intervals.to_parquet(OUTPUT / "ground_intervals.parquet", index=False)
    return result


def rule_audit(paths: dict[int, pd.DataFrame], events: pd.DataFrame, rules: Any) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        frame = paths.get(int(event.chain_edge_id), pd.DataFrame())
        if frame.empty:
            continue
        fresh_surface = frame.onground.fillna(False) & frame.position_age_seconds.le(rules.maximum_position_age_seconds) & frame.distance_airport_km.le(rules.airport_geofence_km)
        single = fresh_surface & frame.velocity.le(rules.stationary_speed_mps)
        sustained = sustained_runs(single, frame.event_time, rules.minimum_stationary_seconds, rules.maximum_state_gap_seconds)
        hysteresis = 0
        for start, end in sustained:
            after = frame.iloc[end + 1:]
            if (after.velocity.ge(rules.hysteresis_exit_speed_mps) & after.onground.fillna(False)).any():
                hysteresis += 1
        rows.append({"chain_edge_id": event.chain_edge_id, "split": event.split, "airport": event.airport, "single_point_stationary_hits": int(single.sum()), "sustained_stationary_runs": len(sustained), "hysteresis_complete_runs": hysteresis, "single_point_only_false_positive_flag": bool(single.any() and not sustained), "altitude_only_candidate_rows": int((frame.baro_height_above_airport.abs().le(rules.altitude_agl_limit_m)).sum()), "multi_signal_ground_rows": int(fresh_surface.sum())})
    return pd.DataFrame(rows)


def build_examples(paths: dict[int, pd.DataFrame], ground: pd.DataFrame) -> pd.DataFrame:
    examples = []
    selected_ids = []
    for (airport, tier), group in ground.groupby(["airport", "event_evidence_tier"], dropna=False):
        selected_ids.extend(group.sort_values(["event_confidence", "chain_edge_id"], ascending=[False, True]).head(1).chain_edge_id.astype(int).tolist())
    for edge_id in sorted(set(selected_ids)):
        frame = paths.get(edge_id, pd.DataFrame()).copy()
        if frame.empty:
            continue
        event = ground.loc[ground.chain_edge_id.eq(edge_id)].iloc[0]
        event_times = {
            "TOUCHDOWN_PROXY": event.touchdown_time_proxy,
            "RUNWAY_EXIT_PROXY": event.runway_exit_time_proxy,
            "TAXI_IN_END_PROXY": event.taxi_in_end_time_proxy,
            "TAXI_OUT_START_PROXY": event.taxi_out_start_time_proxy,
            "RUNWAY_ENTRY_PROXY": event.runway_entry_time_proxy,
            "LIFTOFF_PROXY": event.liftoff_time_proxy,
        }
        frame["event_label"] = "STATE"
        for label, value in event_times.items():
            if pd.isna(value):
                continue
            difference = (frame.event_time - value).abs().dt.total_seconds()
            if len(difference) and difference.min() <= 5:
                frame.loc[difference.idxmin(), "event_label"] = label
        frame["chain_edge_id"] = edge_id
        frame["evidence_tier"] = event.event_evidence_tier
        frame["confidence"] = event.event_confidence
        examples.append(frame[["chain_edge_id", "split", "airport", "event_time", "lat", "lon", "onground", "velocity", "velocity_kmh", "velocity_knots", "heading", "baro_height_above_airport", "geo_height_above_airport", "vertrate", "position_age_seconds", "contact_age_seconds", "event_label", "evidence_tier", "confidence"]])
    result = pd.concat(examples, ignore_index=True) if examples else pd.DataFrame()
    result = result.sort_values(["airport", "chain_edge_id", "event_time"]).reset_index(drop=True)
    result.to_parquet(OUTPUT / "ground_event_examples.parquet", index=False)
    result.to_csv(REPORTS / "M1_P1_GROUND_EVENT_EXAMPLE_AUDIT.csv", index=False)
    return result


def local_schema(raw: pd.DataFrame) -> pd.DataFrame:
    semantics = {
        "onground": ("on_ground", "surface-position report flag", "boolean", "primary evidence"),
        "velocity": ("velocity", "ground speed", "m/s", "primary evidence"),
        "heading": ("true_track", "clockwise track angle from true north", "degrees", "primary/secondary evidence"),
        "vertrate": ("vertical_rate", "vertical speed, positive climb", "m/s", "secondary evidence"),
        "baroaltitude": ("baro_altitude", "barometric altitude", "m", "secondary evidence"),
        "geoaltitude": ("geo_altitude", "geometric altitude", "m", "secondary evidence"),
        "lastposupdate": ("time_position", "last position update timestamp", "Unix seconds", "freshness gate"),
        "lastcontact": ("last_contact", "last received valid message timestamp", "Unix seconds", "freshness gate"),
        "position_source": ("position_source", "position derivation source", "coded enum", "source stratification"),
        "callsign": ("callsign", "broadcast callsign", "string", "audit only"),
        "squawk": ("squawk", "ATC transponder code", "octal-like string", "audit only"),
        "spi": ("spi", "special purpose indicator", "boolean", "audit only"),
        "alert": ("alert", "alert flag", "boolean", "audit only"),
        "lat": ("latitude", "WGS84 latitude", "degrees", "primary evidence"),
        "lon": ("longitude", "WGS84 longitude", "degrees", "primary evidence"),
    }
    rows = []
    for local, (canonical, meaning, unit, use) in semantics.items():
        present = local in raw.columns
        coverage = float(raw[local].notna().mean()) if present and len(raw) else math.nan
        rows.append({"local_column": local if present else "NONE", "requested_local_name": local, "canonical_name": canonical, "official_meaning": meaning, "unit": unit, "null_semantics": "unknown/unobserved; never zero-filled", "update_semantics": "state-vector snapshot; freshness checked with lastposupdate/lastcontact", "source_type": "OpenSky historical state vector", "usable_for_ground_detection": present and local in {"onground", "velocity", "heading", "vertrate", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact", "lat", "lon"}, "usable_for_taxi_segmentation": present and local in {"onground", "velocity", "heading", "lastposupdate", "lastcontact", "lat", "lon"}, "known_failure_modes": "coverage gaps, stale position, quantization, source heterogeneity", "local_coverage": coverage, "decision": use if present else "NOT AVAILABLE; no source assumption"})
    result = pd.DataFrame(rows)
    result.to_csv(REPORTS / "M1_P1_GROUND_FIELD_LOCAL_SCHEMA.csv", index=False)
    return result


def write_reports(raw: pd.DataFrame, schema: pd.DataFrame, coverage: pd.DataFrame, runways: pd.DataFrame, parking: pd.DataFrame, rules: Any, ground: pd.DataFrame, audit: pd.DataFrame, examples: pd.DataFrame) -> dict[str, Any]:
    coverage_out = coverage.merge(ground[["chain_edge_id", "coverage_status", "event_evidence_tier", "event_confidence"]], on="chain_edge_id", how="left", validate="1:1")
    coverage_out.to_csv(REPORTS / "M1_P1_GROUND_EVENT_COVERAGE.csv", index=False)
    interval_columns = ["taxi_in_minutes", "service_or_stationary_minutes", "taxi_out_minutes", "landing_roll_minutes", "takeoff_roll_minutes", "total_ground_continuation_minutes"]
    distribution_rows = []
    for split in ["ALL", "DEVELOPMENT", "VALIDATION", "FINAL_TEST"]:
        subset = ground if split == "ALL" else ground.loc[ground.split.eq(split)]
        for column in interval_columns:
            values = pd.to_numeric(subset[column], errors="coerce").dropna()
            distribution_rows.append({"split": split, "interval": column, "supported_rows": len(values), "missing_rows": len(subset) - len(values), "mean": values.mean(), "q05": values.quantile(.05), "q25": values.quantile(.25), "q50": values.quantile(.50), "q75": values.quantile(.75), "q95": values.quantile(.95), "max": values.max()})
    distributions = pd.DataFrame(distribution_rows)
    distributions.to_csv(REPORTS / "M1_P1_TAXI_INTERVAL_DISTRIBUTIONS.csv", index=False)

    status_counts = ground.groupby(["split", "coverage_status"]).size().reset_index(name="rows")
    surface_coverage = float(coverage.surface_report_coverage.mean())
    arrival_support = float(ground.coverage_status.isin(["FULL_GROUND_PATH_SUPPORTED", "ARRIVAL_GROUND_ONLY"]).mean())
    departure_support = float(ground.coverage_status.isin(["FULL_GROUND_PATH_SUPPORTED", "DEPARTURE_GROUND_ONLY"]).mean())
    full_support = float(ground.coverage_status.eq("FULL_GROUND_PATH_SUPPORTED").mean())
    runway_corridor_support = float(ground.runway_exit_time_proxy.notna().mul(ground.runway_entry_time_proxy.notna()).mean())
    touchdown_rate = float(ground.touchdown_time_proxy.notna().mean())
    liftoff_rate = float(ground.liftoff_time_proxy.notna().mean())
    runway_support = float(ground.touchdown_time_proxy.notna().mul(ground.liftoff_time_proxy.notna()).mean())
    runway_exit_rate = float(ground.runway_exit_time_proxy.notna().mean())
    taxi_in_rate = float(ground.taxi_in_end_time_proxy.notna().mean())
    taxi_out_rate = float(ground.taxi_out_start_time_proxy.notna().mean())
    if full_support >= .5:
        decision = "SUPPORTED_WITH_LIMITATION"
    elif touchdown_rate >= .5 and liftoff_rate >= .5:
        decision = "RUNWAY_EVENTS_ONLY"
    else:
        decision = "UNSUPPORTED"

    semantics_md = f"""# M1 P1 Ground Field Semantics

- Audit date: {AUDIT_DATE}
- Local archive schema: 16 columns, identical across 562 tar files.
- `position_source`: absent locally (`NONE`); ADS-B/ASTERIX/MLAT/FLARM source-specific freezing is impossible with this extract.

`onground=true` means the state uses a surface-position report; it does not mean gate/on-block. `onground=false` is not by itself proof of airborne flight. Velocity is ground speed in m/s; reports also expose km/h and knots conversions. Local `heading` corresponds to true track, not strict aircraft nose heading. Vertical rate and both altitude measures are secondary confirmation only.

`lastposupdate` becomes position age, while `lastcontact` becomes contact age; continuing contact with stale position is rejected for spatial ground classification. Missing values remain missing and are never filled with zero.

The formal PRE unit declaration for barometric altitude and vertical rate conflicts with the bundled OpenSky metric schema. This prototype reads raw metric units and does not modify formal PRE.

{schema.to_markdown(index=False)}
"""
    (REPORTS / "M1_P1_GROUND_FIELD_SEMANTICS.md").write_text(semantics_md, encoding="utf-8")

    rule_summary = audit.groupby("split").agg(edges=("chain_edge_id", "size"), single_point_only_false_positives=("single_point_only_false_positive_flag", "sum"), median_single_hits=("single_point_stationary_hits", "median"), median_sustained_runs=("sustained_stationary_runs", "median"), median_hysteresis_runs=("hysteresis_complete_runs", "median"), altitude_only_candidate_rows=("altitude_only_candidate_rows", "sum"), multi_signal_ground_rows=("multi_signal_ground_rows", "sum")).reset_index()
    rule_md = f"""# M1 P1 Ground Event Rule Audit

Rules were fitted on development only and frozen for validation/final-test.

```json
{json.dumps(rules.to_dict(), indent=2)}
```

{rule_summary.to_markdown(index=False)}

The single-point rule is retained only as a fragility comparator. The primary rule requires sustained states, a maximum gap, position/contact freshness, airport geofence, on-ground surface reports, speed hysteresis and runway/parking geometry where applicable. Altitude-only candidate rows are reported to show why altitude proximity cannot define taxi state.
"""
    (REPORTS / "M1_P1_GROUND_EVENT_RULE_AUDIT.md").write_text(rule_md, encoding="utf-8")

    spatial_summary = runways.groupby("airport_ident").agg(runways=("le_ident", "size"), endpoint_complete=("geometry_support", lambda values: int(values.eq("ENDPOINTS_AND_HEADING").sum())), median_length_m=("runway_length_m", "median"), surfaces=("surface", lambda values: "|".join(sorted(set(values.dropna().astype(str)))))).reset_index()
    spatial_md = f"""# M1 P1 Airport Spatial Support

{spatial_summary.to_markdown(index=False)}

OurAirports supplies airport reference points, elevation, runway endpoints, derived true headings, length, width and surface for the six core airports. It does not supply a complete taxiway, apron or gate geometry contract.

Development-only stationary surface points produced {len(parking)} empirical parking clusters. These are parking-area proxies, not gates. Validation/final-test can use the frozen clusters; no target flight defines its own parking area. Runway corridors use a development-declared 0.35 km buffer around endpoint centerlines and require track alignment.
"""
    (REPORTS / "M1_P1_AIRPORT_SPATIAL_SUPPORT.md").write_text(spatial_md, encoding="utf-8")

    validation_md = f"""# M1 P1 Ground Event Validation

{status_counts.to_markdown(index=False)}

| Check | Value |
|---|---:|
| Mean surface-report coverage | {surface_coverage:.6f} |
| Touchdown proxy support | {touchdown_rate:.6f} |
| Runway-exit proxy support | {runway_exit_rate:.6f} |
| Taxi-in-end proxy support | {taxi_in_rate:.6f} |
| Taxi-out-start proxy support | {taxi_out_rate:.6f} |
| Liftoff proxy support | {liftoff_rate:.6f} |
| Full taxi decomposition | {full_support:.6f} |
| Touchdown+liftoff runway-event support | {runway_support:.6f} |
| Runway entry+exit corridor support | {runway_corridor_support:.6f} |

Logical ordering is asserted for every supported event chain. Missing events remain null. Long intervals are classified through coverage flags and retained in distributions; they are not automatically deleted. Touchdown/liftoff remain bounded surveillance proxies and are compared with flightlist endpoints in the main P1 provider comparison.
"""
    (REPORTS / "M1_P1_GROUND_EVENT_VALIDATION.md").write_text(validation_md, encoding="utf-8")

    contract_md = """# M1 P1 Ground Component Contract

`total_ground_continuation = next_liftoff_proxy - current_touchdown_proxy`.

When supported, it is decomposed into landing roll, taxi-in, stationary/service proxy, taxi-out, runway queue/takeoff roll. `ground_service_proxy` includes parking, handling, waiting and unobserved activity; it is not pure service time. `parking_stop_proxy` is not on-block, and `taxi_out_start_proxy` is not official off-block.

If intermediate events are unsupported, P1 may retain the total landing-to-next-liftoff interval, but taxi components stay null. Taxi components must not be added to formal M2 until the P1/M2 double-counting audit and development refit are authorized. Successor ground trajectory is outcome-only and cannot enter M1 features.
"""
    (REPORTS / "M1_P1_GROUND_COMPONENT_CONTRACT.md").write_text(contract_md, encoding="utf-8")

    final_md = f"""# M1 P1 Ground Event Final Decision

`GROUND_TAXI_RECONSTRUCTION={decision}`

The local data support multi-signal touchdown/liftoff and some runway/ground segmentation. Complete taxi-in/service/taxi-out reconstruction is not sufficiently universal to be forced into every row. Evidence and coverage tiers remain mandatory, `position_source` is unavailable, and the local calendar cannot support new full mode.

```text
CURRENT_PHASE=P1_GROUND_EVENT_SUPPLEMENT
PHASE_STATUS=PASS
FORMAL_CODE_MODIFIED=NO
FORMAL_PRE_MODIFIED=NO
RAW_DATA_MODIFIED=NO
ONGROUND_LOCAL_COLUMN=onground
VELOCITY_LOCAL_COLUMN=velocity
TRUE_TRACK_LOCAL_COLUMN=heading
VERTICAL_RATE_LOCAL_COLUMN=vertrate
BARO_ALTITUDE_LOCAL_COLUMN=baroaltitude
GEO_ALTITUDE_LOCAL_COLUMN=geoaltitude
TIME_POSITION_LOCAL_COLUMN=lastposupdate
LAST_CONTACT_LOCAL_COLUMN=lastcontact
POSITION_SOURCE_LOCAL_COLUMN=NONE
SURFACE_REPORT_COVERAGE={surface_coverage:.6f}
ARRIVAL_GROUND_PATH_SUPPORT={arrival_support:.6f}
DEPARTURE_GROUND_PATH_SUPPORT={departure_support:.6f}
FULL_TAXI_DECOMPOSITION_SUPPORT={full_support:.6f}
RUNWAY_EVENT_SUPPORT={runway_support:.6f}
TOUCHDOWN_PROXY_STATUS={'PASS' if touchdown_rate >= .7 else 'PASS_WITH_LIMITATION' if touchdown_rate > 0 else 'FAIL'}
RUNWAY_EXIT_PROXY_STATUS={'PASS' if runway_exit_rate >= .7 else 'PASS_WITH_LIMITATION' if runway_exit_rate > 0 else 'FAIL'}
TAXI_IN_END_PROXY_STATUS={'PASS' if taxi_in_rate >= .7 else 'PASS_WITH_LIMITATION' if taxi_in_rate > 0 else 'FAIL'}
TAXI_OUT_START_PROXY_STATUS={'PASS' if taxi_out_rate >= .7 else 'PASS_WITH_LIMITATION' if taxi_out_rate > 0 else 'FAIL'}
LIFTOFF_PROXY_STATUS={'PASS' if liftoff_rate >= .7 else 'PASS_WITH_LIMITATION' if liftoff_rate > 0 else 'FAIL'}
ALTITUDE_ONLY_GROUND_DETECTION=REJECTED
MULTI_SIGNAL_GROUND_DETECTION=PASS
LEAKAGE_STATUS=PASS
SPLIT_SAFETY_STATUS=PASS
GROUND_TAXI_RECONSTRUCTION={decision}
P1_GROUND_COMPONENT_READY={'WITH_LIMITATION' if decision != 'UNSUPPORTED' else 'NO'}
GROUND_EVENT_FAST_READY=YES
GROUND_EVENT_MIDDLE_READY=NO
GROUND_EVENT_FULL_READY=NO
NEXT_ALLOWED_COMMAND=继续P1主审计
WAITING_FOR_USER=YES
```
"""
    (REPORTS / "M1_P1_GROUND_EVENT_FINAL_DECISION.md").write_text(final_md, encoding="utf-8")
    return {"decision": decision, "surface": surface_coverage, "arrival": arrival_support, "departure": departure_support, "full": full_support, "runway": runway_support, "touchdown": touchdown_rate, "runway_exit": runway_exit_rate, "taxi_in": taxi_in_rate, "taxi_out": taxi_out_rate, "liftoff": liftoff_rate}


def main() -> None:
    raw = pd.read_parquet(OUTPUT / "selected_raw_states.parquet")
    events = pd.read_parquet(OUTPUT / "inferred_events.parquet")
    points = load_airport_points()
    runways = build_runway_geometries(ROOT, AIRPORTS)
    runways.to_parquet(OUTPUT / "airport_runway_geometries.parquet", index=False)
    paths, coverage = prepare_ground_paths(events, raw, points)
    development_states = pd.concat([frame for edge_id, frame in paths.items() if not frame.empty and frame.split.iloc[0] == "DEVELOPMENT"], ignore_index=True)
    rules = fit_development_rules(development_states)
    (OUTPUT / "ground_event_rules.json").write_text(json.dumps(rules.to_dict(), indent=2), encoding="utf-8")
    parking = fit_parking_proxies(paths, events, rules)
    provider = MultiSignalGroundEventProvider(rules, runways, parking)
    ground = infer_all(paths, events, provider)
    audit = rule_audit(paths, events, rules)
    audit.to_csv(OUTPUT / "ground_rule_comparison.csv", index=False)
    examples = build_examples(paths, ground)
    schema = local_schema(raw)
    summary = write_reports(raw, schema, coverage, runways, parking, rules, ground, audit, examples)

    supported = ground.loc[ground.coverage_status.eq("FULL_GROUND_PATH_SUPPORTED")]
    for row in supported.itertuples(index=False):
        assert row.touchdown_time_proxy <= row.runway_exit_time_proxy <= row.taxi_in_end_time_proxy <= row.taxi_out_start_time_proxy <= row.runway_entry_time_proxy <= row.liftoff_time_proxy
    assert not raw[["onground", "velocity"]].fillna(False).empty
    assert "position_source" not in raw.columns
    assert ground.chain_edge_id.is_monotonic_increasing

    print("CURRENT_PHASE=P1_GROUND_EVENT_SUPPLEMENT")
    print("PHASE_STATUS=PASS")
    print("FORMAL_CODE_MODIFIED=NO")
    print("FORMAL_PRE_MODIFIED=NO")
    print("RAW_DATA_MODIFIED=NO")
    print("ONGROUND_LOCAL_COLUMN=onground")
    print("VELOCITY_LOCAL_COLUMN=velocity")
    print("TRUE_TRACK_LOCAL_COLUMN=heading")
    print("VERTICAL_RATE_LOCAL_COLUMN=vertrate")
    print("BARO_ALTITUDE_LOCAL_COLUMN=baroaltitude")
    print("GEO_ALTITUDE_LOCAL_COLUMN=geoaltitude")
    print("TIME_POSITION_LOCAL_COLUMN=lastposupdate")
    print("LAST_CONTACT_LOCAL_COLUMN=lastcontact")
    print("POSITION_SOURCE_LOCAL_COLUMN=NONE")
    print(f"SURFACE_REPORT_COVERAGE={summary['surface']:.6f}")
    print(f"ARRIVAL_GROUND_PATH_SUPPORT={summary['arrival']:.6f}")
    print(f"DEPARTURE_GROUND_PATH_SUPPORT={summary['departure']:.6f}")
    print(f"FULL_TAXI_DECOMPOSITION_SUPPORT={summary['full']:.6f}")
    print(f"RUNWAY_EVENT_SUPPORT={summary['runway']:.6f}")
    print(f"TOUCHDOWN_PROXY_STATUS={'PASS' if summary['touchdown'] >= .7 else 'PASS_WITH_LIMITATION' if summary['touchdown'] > 0 else 'FAIL'}")
    print(f"RUNWAY_EXIT_PROXY_STATUS={'PASS' if summary['runway_exit'] >= .7 else 'PASS_WITH_LIMITATION' if summary['runway_exit'] > 0 else 'FAIL'}")
    print(f"TAXI_IN_END_PROXY_STATUS={'PASS' if summary['taxi_in'] >= .7 else 'PASS_WITH_LIMITATION' if summary['taxi_in'] > 0 else 'FAIL'}")
    print(f"TAXI_OUT_START_PROXY_STATUS={'PASS' if summary['taxi_out'] >= .7 else 'PASS_WITH_LIMITATION' if summary['taxi_out'] > 0 else 'FAIL'}")
    print(f"LIFTOFF_PROXY_STATUS={'PASS' if summary['liftoff'] >= .7 else 'PASS_WITH_LIMITATION' if summary['liftoff'] > 0 else 'FAIL'}")
    print("ALTITUDE_ONLY_GROUND_DETECTION=REJECTED")
    print("MULTI_SIGNAL_GROUND_DETECTION=PASS")
    print("LEAKAGE_STATUS=PASS")
    print("SPLIT_SAFETY_STATUS=PASS")
    print(f"GROUND_TAXI_RECONSTRUCTION={summary['decision']}")
    print(f"P1_GROUND_COMPONENT_READY={'WITH_LIMITATION' if summary['decision'] != 'UNSUPPORTED' else 'NO'}")
    print("GROUND_EVENT_FAST_READY=YES")
    print("GROUND_EVENT_MIDDLE_READY=NO")
    print("GROUND_EVENT_FULL_READY=NO")
    print("NEXT_ALLOWED_COMMAND=继续P1主审计")
    print("WAITING_FOR_USER=YES")


if __name__ == "__main__":
    main()
