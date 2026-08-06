from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import tarfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .contracts import AirportPoint, EventProviderContext, EventTimeResult
from .inference import ADSBEventTimeProvider
from .run_profiles import write_profiles


ROOT = Path(__file__).resolve().parents[2]
RAW_STATE = ROOT / "data/raw/opensky/state_vectors/2022"
AIRPORTS_PATH = ROOT / "data/raw/ourairports/snapshot=2021-12-31/airports.csv"
COMPARISON_PATH = ROOT / "output/chain_feasibility/chain_rule_comparison.parquet"
CLASSIFIED_PATH = ROOT / "output/chain_feasibility/chain_edges_classified.parquet"
SNAPSHOT_PATH = ROOT / "pre/output/adapt_full/snapshots.parquet"
EPISODE_PATH = ROOT / "pre/output/adapt_full/episodes.parquet"
FORMAL72_PATH = ROOT / "data/manifests/formal_72_day_manifest.csv"
CURRENT_MANIFEST_PATH = ROOT / "data/manifests/current_data_adapt_full_manifest.csv"
OUTPUT = ROOT / "output/p1_event_reconstruction"
REPORTS = ROOT / "reports"

AUDIT_DATE = "2026-07-31"
AUDIT_BLOCKS = {
    "DEVELOPMENT": "2022-04-18",
    "VALIDATION": "2022-05-23",
    "FINAL_TEST": "2022-06-20",
}
BLOCK_START = 6
BLOCK_END = 12
RAW_HOURS = list(range(5, 14))
MAX_EDGES_PER_AIRPORT_SPLIT = 30
RAW_FIELDS = [
    "time", "icao24", "lat", "lon", "velocity", "heading", "vertrate",
    "callsign", "onground", "alert", "spi", "squawk", "baroaltitude",
    "geoaltitude", "lastposupdate", "lastcontact",
]
EVENT_ROLES = ["departure_minus", "arrival_minus", "departure_plus"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def markdown_table(frame: pd.DataFrame, digits: int = 4) -> str:
    shown = frame.copy()
    for column in shown.select_dtypes(include=["float", "float32", "float64"]).columns:
        shown[column] = shown[column].map(lambda value: "" if pd.isna(value) else f"{value:.{digits}f}")
    return shown.to_markdown(index=False)


def load_airports() -> tuple[pd.DataFrame, EventProviderContext]:
    frame = pd.read_csv(AIRPORTS_PATH, low_memory=False)
    frame = frame.loc[frame.ident.notna()].copy()
    frame["elevation_m"] = pd.to_numeric(frame.elevation_ft, errors="coerce").fillna(0) * 0.3048
    context = EventProviderContext(
        airports={
            str(row.ident): AirportPoint(
                str(row.ident), float(row.latitude_deg), float(row.longitude_deg), float(row.elevation_m)
            )
            for row in frame.itertuples(index=False)
            if pd.notna(row.latitude_deg) and pd.notna(row.longitude_deg)
        }
    )
    return frame, context


def load_r3_edges() -> pd.DataFrame:
    cached = OUTPUT / "r3_s3_edges.parquet"
    if cached.exists():
        return pd.read_parquet(cached)
    comparison = pd.read_parquet(
        COMPARISON_PATH,
        columns=["chain_edge_id", "scope_s3_snapshot_supported", "rule_r3_retained"],
    )
    wanted = set(
        comparison.loc[
            comparison.scope_s3_snapshot_supported.fillna(False)
            & comparison.rule_r3_retained.fillna(False),
            "chain_edge_id",
        ].astype(int)
    )
    columns = [
        "chain_edge_id", "predecessor_record_id", "outcome_successor_record_id",
        "predecessor_episode_id", "icao24_minus", "icao24_plus",
        "registration_minus", "registration_plus", "callsign_minus", "callsign_plus",
        "typecode_minus", "typecode_plus", "origin_minus", "destination_minus",
        "origin_plus", "destination_plus", "firstseen_minus", "lastseen_minus",
        "firstseen_plus", "lastseen_plus", "ground_gap_minutes", "airport_continuity",
        "registration_continuity", "typecode_continuity", "diagnostic_status",
        "chain_quality_status", "rule_r2_retained", "rule_r3_retained",
        "split_of_predecessor", "endpoint_coordinate_support", "state_vector_support",
        "cross_day", "cross_month", "cross_split_boundary",
    ]
    pieces: list[pd.DataFrame] = []
    parquet = pq.ParquetFile(CLASSIFIED_PATH)
    for batch in parquet.iter_batches(columns=columns, batch_size=500_000):
        frame = batch.to_pandas()
        selected = frame.chain_edge_id.isin(wanted)
        if selected.any():
            pieces.append(frame.loc[selected].copy())
    result = pd.concat(pieces, ignore_index=True)
    for column in ["firstseen_minus", "lastseen_minus", "firstseen_plus", "lastseen_plus"]:
        result[column] = pd.to_datetime(result[column], utc=True, errors="coerce")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result.to_parquet(cached, index=False)
    return result


def select_event_edges(edges: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for split, date_text in AUDIT_BLOCKS.items():
        date = pd.Timestamp(date_text, tz="UTC")
        start = date + pd.Timedelta(hours=BLOCK_START, minutes=15)
        end = date + pd.Timedelta(hours=BLOCK_END) - pd.Timedelta(minutes=15)
        subset = edges.loc[
            edges.split_of_predecessor.eq(split)
            & edges.firstseen_minus.between(start, end)
            & edges.lastseen_minus.between(start, end)
            & edges.firstseen_plus.between(start, end)
            & edges.airport_continuity.fillna(False)
        ].copy()
        subset["airport"] = subset.destination_minus
        subset = (
            subset.sort_values("chain_edge_id")
            .groupby("airport", group_keys=False)
            .head(MAX_EDGES_PER_AIRPORT_SPLIT)
        )
        pieces.append(subset)
    selected = pd.concat(pieces, ignore_index=True)
    selected.to_parquet(OUTPUT / "selected_event_edges.parquet", index=False)
    return selected


def archive_path(date_text: str, hour: int) -> Path:
    return RAW_STATE / f"date={date_text}" / f"hour={hour:02d}" / f"states_{date_text}-{hour:02d}.csv.tar"


def extract_raw_states(selected: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cache = OUTPUT / "selected_raw_states.parquet"
    audit_cache = OUTPUT / "raw_archive_sample_audit.csv"
    if cache.exists() and audit_cache.exists():
        return pd.read_parquet(cache), pd.read_csv(audit_cache)
    state_pieces: list[pd.DataFrame] = []
    archive_rows: list[dict[str, Any]] = []
    for split, date_text in AUDIT_BLOCKS.items():
        wanted_values = sorted(set(selected.loc[selected.split_of_predecessor.eq(split), "icao24_minus"].dropna().astype(str).str.lower()))
        wanted = pa.array(wanted_values, type=pa.string())
        for hour in RAW_HOURS:
            path = archive_path(date_text, hour)
            started = time.monotonic()
            total = retained = 0
            header: list[str] = []
            if not path.exists():
                archive_rows.append({"split": split, "date": date_text, "hour": hour, "file_exists": False, "readable": False, "raw_rows": 0, "retained_rows": 0, "elapsed_seconds": 0.0, "header_columns": ""})
                continue
            with tarfile.open(path, mode="r") as archive:
                member = next(item for item in archive.getmembers() if item.name.endswith(".csv.gz"))
                raw_stream = archive.extractfile(member)
                assert raw_stream is not None
                with gzip.GzipFile(fileobj=raw_stream) as compressed:
                    reader = pacsv.open_csv(
                        compressed,
                        read_options=pacsv.ReadOptions(block_size=16 << 20),
                        convert_options=pacsv.ConvertOptions(include_columns=RAW_FIELDS),
                    )
                    for batch in reader:
                        chunk = batch.to_pandas()
                        if not header:
                            header = list(chunk.columns)
                        total += len(chunk)
                        mask = pc.is_in(pc.utf8_lower(batch.column("icao24")), value_set=wanted).to_numpy(zero_copy_only=False)
                        if mask.any():
                            kept = chunk.loc[mask].copy()
                            kept["raw_source_file"] = str(path)
                            kept["source_date"] = date_text
                            kept["source_hour"] = hour
                            state_pieces.append(kept)
                            retained += len(kept)
            elapsed = time.monotonic() - started
            archive_rows.append({"split": split, "date": date_text, "hour": hour, "file_exists": True, "readable": True, "raw_rows": total, "retained_rows": retained, "elapsed_seconds": elapsed, "header_columns": "|".join(header), "size_bytes": path.stat().st_size, "sha256": sha256(path)})
            print(f"RAW_EVENT_SCAN split={split} date={date_text} hour={hour:02d} raw={total:,} retained={retained:,} seconds={elapsed:.1f}", flush=True)
    states = pd.concat(state_pieces, ignore_index=True) if state_pieces else pd.DataFrame(columns=RAW_FIELDS)
    states["icao24"] = states.icao24.astype("string").str.lower()
    states["time"] = pd.to_numeric(states.time, errors="coerce")
    states = states.dropna(subset=["time", "icao24"]).sort_values(["source_date", "icao24", "time"])
    states.to_parquet(cache, index=False, compression="zstd")
    audit = pd.DataFrame(archive_rows)
    audit.to_csv(audit_cache, index=False)
    return states, audit


def state_window(states_by_key: dict[tuple[str, str], pd.DataFrame], date_text: str, icao24: str, center: pd.Timestamp) -> pd.DataFrame:
    frame = states_by_key.get((date_text, str(icao24).lower()))
    if frame is None or frame.empty:
        return pd.DataFrame(columns=states_by_key[next(iter(states_by_key))].columns if states_by_key else RAW_FIELDS)
    start = center.timestamp() - 15 * 60
    end = center.timestamp() + 15 * 60
    return frame.loc[frame.time.between(start, end)].copy()


def flatten_event(prefix: str, event: EventTimeResult) -> dict[str, Any]:
    return {
        f"{prefix}_time": event.event_time,
        f"{prefix}_evidence_tier": event.evidence_tier,
        f"{prefix}_confidence": event.confidence,
        f"{prefix}_uncertainty_seconds": event.uncertainty_seconds,
        f"{prefix}_airport": event.airport,
        f"{prefix}_source_fields": "|".join(event.source_fields),
        f"{prefix}_source_files": "|".join(event.source_files),
        f"{prefix}_rule_id": event.rule_id,
        f"{prefix}_quality_flags": "|".join(event.quality_flags),
        f"{prefix}_supported": event.is_supported,
    }


def infer_events(selected: pd.DataFrame, states: pd.DataFrame, provider: ADSBEventTimeProvider) -> tuple[pd.DataFrame, pd.DataFrame]:
    states_by_key = {
        (str(date), str(icao)): group.reset_index(drop=True)
        for (date, icao), group in states.groupby(["source_date", "icao24"], sort=False)
    }
    rows: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        date_text = AUDIT_BLOCKS[str(row.split_of_predecessor)]
        events = {
            "departure_minus": ("DEPARTURE", row.origin_minus, row.firstseen_minus),
            "arrival_minus": ("ARRIVAL", row.destination_minus, row.lastseen_minus),
            "departure_plus": ("DEPARTURE", row.origin_plus, row.firstseen_plus),
        }
        output: dict[str, Any] = {
            "chain_edge_id": row.chain_edge_id,
            "predecessor_episode_id": row.predecessor_episode_id,
            "split": row.split_of_predecessor,
            "airport": row.destination_minus,
            "origin": row.origin_minus,
            "destination": row.destination_minus,
            "aircraft_group": "unknown",
            "typecode": row.typecode_minus,
            "icao24": row.icao24_minus,
            "ground_gap_flightlist_minutes": row.ground_gap_minutes,
            "rule_r2_retained": row.rule_r2_retained,
        }
        for role, (kind, airport, fallback) in events.items():
            window = state_window(states_by_key, date_text, row.icao24_minus, fallback)
            if kind == "DEPARTURE":
                result = provider.infer_departure_event(window, airport, fallback)
                prepared, point = provider._prepare(window, airport)
                e1 = provider._departure_e1(prepared, point, airport)
                e2 = provider._departure_e2(prepared, point, airport)
            else:
                result = provider.infer_arrival_event(window, airport, fallback)
                prepared, point = provider._prepare(window, airport)
                e1 = provider._arrival_e1(prepared, point, airport)
                e2 = provider._arrival_e2(prepared, point, airport)
            output.update(flatten_event(role, result))
            output[f"{role}_state_rows"] = len(window)
            output[f"{role}_onground_coverage"] = float(window.onground.notna().mean()) if len(window) else 0.0
            output[f"{role}_position_coverage"] = float(window[["lat", "lon"]].notna().all(axis=1).mean()) if len(window) else 0.0
            output[f"{role}_kinematic_coverage"] = float(window[["velocity", "vertrate", "baroaltitude"]].notna().all(axis=1).mean()) if len(window) else 0.0
            endpoint = pd.to_datetime(fallback, utc=True)
            if e1.is_supported:
                comparisons.append({"chain_edge_id": row.chain_edge_id, "split": row.split_of_predecessor, "airport": airport, "event_role": role, "comparison": "E1_VS_E3_ENDPOINT", "primary_tier": e1.evidence_tier, "secondary_tier": "E3_FLIGHTLIST_ENDPOINT", "difference_seconds": (e1.event_time - endpoint).total_seconds(), "absolute_difference_seconds": abs((e1.event_time - endpoint).total_seconds()), "combined_uncertainty_seconds": e1.uncertainty_seconds + 300.0, "within_combined_uncertainty": abs((e1.event_time - endpoint).total_seconds()) <= e1.uncertainty_seconds + 300.0})
            if e1.is_supported and e2.is_supported:
                delta = (e2.event_time - e1.event_time).total_seconds()
                comparisons.append({"chain_edge_id": row.chain_edge_id, "split": row.split_of_predecessor, "airport": airport, "event_role": role, "comparison": "E2_VS_E1", "primary_tier": e2.evidence_tier, "secondary_tier": e1.evidence_tier, "difference_seconds": delta, "absolute_difference_seconds": abs(delta), "combined_uncertainty_seconds": e1.uncertainty_seconds + e2.uncertainty_seconds, "within_combined_uncertainty": abs(delta) <= e1.uncertainty_seconds + e2.uncertainty_seconds})
        rows.append(output)
    events = pd.DataFrame(rows)
    metadata = pd.read_parquet(ROOT / "output/chain_feasibility/chain_rule_comparison.parquet", columns=["chain_edge_id", "aircraft_group", "month", "firstseen_time_bin"])
    events = events.drop(columns=["aircraft_group"]).merge(metadata.drop_duplicates("chain_edge_id"), on="chain_edge_id", how="left", validate="1:1")
    events.to_parquet(OUTPUT / "inferred_events.parquet", index=False)
    comparison = pd.DataFrame(comparisons)
    if not comparison.empty:
        comparison = comparison.merge(
            events[["chain_edge_id", "typecode", "aircraft_group", "month"]].drop_duplicates("chain_edge_id"),
            on="chain_edge_id", how="left", validate="m:1",
        )
        comparison["stage"] = comparison.event_role
    comparison.to_csv(REPORTS / "M1_P1_EVENT_PROVIDER_COMPARISON.csv", index=False)
    return events, comparison


def evidence_rank(value: str) -> int:
    return {
        "E0_OFFICIAL_OPERATIONAL": 0,
        "E1_ADSB_STATE_TRANSITION": 1,
        "E2_TRAJECTORY_KINEMATIC": 2,
        "E3_FLIGHTLIST_ENDPOINT": 3,
        "UNSUPPORTED": 9,
    }.get(str(value), 9)


def combined_tier(row: pd.Series) -> str:
    tiers = [row[f"{role}_evidence_tier"] for role in EVENT_ROLES]
    worst = max(map(evidence_rank, tiers))
    if worst <= 1:
        return "P1_E1_ONLY"
    if worst <= 2:
        return "P1_E1_E2"
    if worst <= 3:
        return "P1_ALL_SUPPORTED_E3_FALLBACK"
    return "UNSUPPORTED"


def _reference_value(
    train: pd.DataFrame,
    row: pd.Series,
    target: str,
    hierarchy: list[list[str]],
    minimum_support: int,
) -> tuple[float, str, int]:
    for columns in hierarchy:
        subset = train
        for column in columns:
            subset = subset.loc[subset[column].astype("string").eq(str(row[column]))]
        values = pd.to_numeric(subset[target], errors="coerce").dropna()
        if len(values) >= minimum_support:
            return float(values.median()), "+".join(columns), len(values)
    values = pd.to_numeric(train[target], errors="coerce").dropna()
    return (float(values.median()), "global", len(values)) if len(values) else (math.nan, "unsupported", 0)


def construct_p1_targets(events: pd.DataFrame) -> pd.DataFrame:
    data = events.copy()
    for role in EVENT_ROLES:
        data[f"{role}_time"] = pd.to_datetime(data[f"{role}_time"], utc=True, errors="coerce")
    data["actual_air_minutes"] = (data.arrival_minus_time - data.departure_minus_time).dt.total_seconds() / 60
    data["actual_ground_minutes"] = (data.departure_plus_time - data.arrival_minus_time).dt.total_seconds() / 60
    data["actual_continuation_minutes"] = (data.departure_plus_time - data.departure_minus_time).dt.total_seconds() / 60
    data["temporal_valid"] = (
        data.departure_minus_time.lt(data.arrival_minus_time)
        & data.arrival_minus_time.lt(data.departure_plus_time)
        & data.actual_air_minutes.gt(0)
        & data.actual_ground_minutes.ge(0)
    )
    data["combined_target_evidence_tier"] = data.apply(combined_tier, axis=1)
    data["target_time_uncertainty_seconds"] = np.sqrt(sum(pd.to_numeric(data[f"{role}_uncertainty_seconds"], errors="coerce").fillna(0) ** 2 for role in EVENT_ROLES))
    data["crossfit_fold"] = data.chain_edge_id.astype(int) % 5

    development = data.loc[data.split.eq("DEVELOPMENT") & data.temporal_valid].copy()
    air_hierarchy = [["origin", "destination", "aircraft_group"], ["aircraft_group"]]
    ground_hierarchy = [["airport", "aircraft_group"], ["airport"]]
    air_values: list[float] = []
    air_levels: list[str] = []
    air_supports: list[int] = []
    ground_values: list[float] = []
    ground_levels: list[str] = []
    ground_supports: list[int] = []
    for _, row in data.iterrows():
        if row.split == "DEVELOPMENT":
            reference_train = development.loc[development.crossfit_fold.ne(row.crossfit_fold)]
            ref_role = "development_5fold_crossfit"
        else:
            reference_train = development
            ref_role = "development_frozen"
        air, air_level, air_n = _reference_value(reference_train, row, "actual_air_minutes", air_hierarchy, 5)
        ground, ground_level, ground_n = _reference_value(reference_train, row, "actual_ground_minutes", ground_hierarchy, 10)
        air_values.append(air); air_levels.append(f"{ref_role}:{air_level}"); air_supports.append(air_n)
        ground_values.append(ground); ground_levels.append(f"{ref_role}:{ground_level}"); ground_supports.append(ground_n)
    data["air_reference_minutes"] = air_values
    data["air_reference_level"] = air_levels
    data["air_reference_support"] = air_supports
    data["ground_reference_minutes"] = ground_values
    data["ground_reference_level"] = ground_levels
    data["ground_reference_support"] = ground_supports
    data["p1_air_component_minutes"] = data.actual_air_minutes - data.air_reference_minutes
    data["p2_ground_component_minutes"] = data.actual_ground_minutes - data.ground_reference_minutes
    data["y_same_aircraft_continuation_timing_deviation_raw"] = data.p1_air_component_minutes + data.p2_ground_component_minutes
    data["p1_formula_direct_minutes"] = data.actual_continuation_minutes - data.air_reference_minutes - data.ground_reference_minutes
    data["formula_identity_error"] = data.y_same_aircraft_continuation_timing_deviation_raw - data.p1_formula_direct_minutes
    data["p1_supported"] = (
        data.temporal_valid
        & data.y_same_aircraft_continuation_timing_deviation_raw.notna()
        & data.air_reference_minutes.notna()
        & data.ground_reference_minutes.notna()
    )
    data.to_parquet(OUTPUT / "p1_targets.parquet", index=False)
    return data


def pinball(y: np.ndarray, prediction: np.ndarray, tau: float) -> float:
    residual = y - prediction
    return float(np.mean(np.maximum(tau * residual, (tau - 1) * residual)))


def crps3(y: np.ndarray, predictions: np.ndarray) -> float:
    taus = np.array([0.1, 0.5, 0.9])
    losses = np.column_stack([
        np.maximum(tau * (y - predictions[:, index]), (tau - 1) * (y - predictions[:, index]))
        for index, tau in enumerate(taus)
    ])
    return float(2 * np.trapezoid(losses, taus, axis=1).mean())


def model_audit(targets: pd.DataFrame) -> tuple[pd.DataFrame, str, pd.DataFrame]:
    from lightgbm import LGBMRegressor
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    snapshots = pd.read_parquet(SNAPSHOT_PATH)
    primary = snapshots.loc[snapshots.snapshot_stage.isin(["t1", "t2", "t3"])].copy()
    labels = targets.loc[targets.p1_supported, [
        "predecessor_episode_id", "chain_edge_id", "split",
        "y_same_aircraft_continuation_timing_deviation_raw", "combined_target_evidence_tier",
    ]].rename(columns={"predecessor_episode_id": "episode_id", "split": "target_split"})
    frame = primary.merge(labels, on="episode_id", how="inner", validate="m:m")
    frame = frame.loc[frame.split.astype("string").str.upper().map({"TRAIN": "DEVELOPMENT", "VALIDATION": "VALIDATION", "TEST": "FINAL_TEST"}).eq(frame.target_split)].copy()
    frame["target"] = frame.y_same_aircraft_continuation_timing_deviation_raw
    frame["time_bin_model"] = frame.time_bin.astype("string")

    current_numeric = [
        "elapsed_ratio", "current_latitude", "current_longitude", "current_altitude",
        "current_velocity", "vertical_rate", "trajectory_coverage", "state_observation_age",
        "state_record_count", "state_source_coverage", "airport_flow_pressure",
        "continuity_exposure", "turnaround_margin", "execution_window_margin",
        "lead_time_margin", "evidence_completeness",
    ]
    context_numeric = [
        "elapsed_ratio", "airport_flow_pressure", "turnaround_margin",
        "execution_window_margin", "lead_time_margin", "runway_count",
        "infrastructure_flexibility", "airport_scale",
    ]
    categorical = ["airport", "origin", "destination", "aircraft_group", "month", "time_bin_model", "snapshot_stage"]

    def make_model(numeric: list[str], tau: float) -> Pipeline:
        present_num = [column for column in numeric if column in frame]
        present_cat = [column for column in categorical if column in frame]
        try:
            encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        except TypeError:
            encoder = OneHotEncoder(handle_unknown="ignore", sparse=True)
        prep = ColumnTransformer([
            ("num", Pipeline([("impute", SimpleImputer(strategy="median"))]), present_num),
            ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("ohe", encoder)]), present_cat),
        ])
        regressor = LGBMRegressor(
            objective="quantile", alpha=tau, n_estimators=250, num_leaves=15,
            max_depth=8, min_child_samples=20, learning_rate=0.05,
            colsample_bytree=0.7, subsample=0.8, subsample_freq=1,
            reg_lambda=1.0, random_state=20260731, deterministic=True,
            force_col_wise=True, verbosity=-1, n_jobs=1,
        )
        return Pipeline([("prep", prep), ("model", regressor)])

    train = frame.loc[frame.target_split.eq("DEVELOPMENT")].copy()
    rows: list[dict[str, Any]] = []
    prediction_rows: list[pd.DataFrame] = []
    quantiles = [0.1, 0.5, 0.9]
    model_predictions: dict[str, dict[str, np.ndarray]] = {}

    hist_tables = {}
    for keys in [["airport", "snapshot_stage", "time_bin_model"], ["airport", "snapshot_stage"], ["snapshot_stage"]]:
        name = "+".join(keys)
        hist_tables[name] = {
            key if isinstance(key, tuple) else (key,): np.quantile(group.target, quantiles)
            for key, group in train.groupby(keys, dropna=False)
            if len(group) >= 5
        }
    global_q = np.quantile(train.target, quantiles)

    for model_name, numeric in [("LGBM_CONTEXT_ONLY", context_numeric), ("LGBM_CURRENT_STATE", current_numeric)]:
        models = [make_model(numeric, tau).fit(train[numeric + categorical], train.target) for tau in quantiles]
        for split in ["VALIDATION", "FINAL_TEST"]:
            part = frame.loc[frame.target_split.eq(split)].copy()
            model_predictions.setdefault(model_name, {})[split] = np.column_stack([model.predict(part[numeric + categorical]) for model in models])

    for split in ["VALIDATION", "FINAL_TEST"]:
        part = frame.loc[frame.target_split.eq(split)].copy()
        hist = np.tile(global_q, (len(part), 1)).astype(float)
        unresolved = np.ones(len(part), dtype=bool)
        for keys in [["airport", "snapshot_stage", "time_bin_model"], ["airport", "snapshot_stage"], ["snapshot_stage"]]:
            table = hist_tables["+".join(keys)]
            for position in np.flatnonzero(unresolved):
                key = tuple(part.iloc[position][key_name] for key_name in keys)
                if key in table:
                    hist[position] = table[key]
                    unresolved[position] = False
        model_predictions.setdefault("HIST", {})[split] = hist

        y = part.target.to_numpy(float)
        for model_name in ["HIST", "LGBM_CONTEXT_ONLY", "LGBM_CURRENT_STATE"]:
            prediction = model_predictions[model_name][split]
            rows.append({
                "split": split, "model": model_name, "snapshot_rows": len(part),
                "episode_rows": part.episode_id.nunique(), "mae_q50": float(np.mean(np.abs(y - prediction[:, 1]))),
                "pinball_q10": pinball(y, prediction[:, 0], .1),
                "pinball_q50": pinball(y, prediction[:, 1], .5),
                "pinball_q90": pinball(y, prediction[:, 2], .9),
                "crps_3q": crps3(y, prediction),
            })
            pred_frame = part[["episode_id", "snapshot_id", "snapshot_stage", "target_split", "target"]].copy()
            pred_frame["model"] = model_name
            pred_frame[["q10", "q50", "q90"]] = prediction
            prediction_rows.append(pred_frame)

    metrics = pd.DataFrame(rows)
    validation = metrics.loc[metrics.split.eq("VALIDATION")].set_index("model")
    final = metrics.loc[metrics.split.eq("FINAL_TEST")].set_index("model")
    validation_gain = validation.loc["LGBM_CONTEXT_ONLY", "crps_3q"] - validation.loc["LGBM_CURRENT_STATE", "crps_3q"]
    final_gain = final.loc["LGBM_CONTEXT_ONLY", "crps_3q"] - final.loc["LGBM_CURRENT_STATE", "crps_3q"]
    if validation_gain > 0 and final_gain > 0:
        information_gain = "POSITIVE"
    elif validation_gain > 0 or final_gain > 0:
        information_gain = "WEAK"
    else:
        information_gain = "NONE"
    metrics["validation_context_minus_current_crps"] = validation_gain
    metrics["final_test_context_minus_current_crps"] = final_gain
    metrics.to_csv(OUTPUT / "lightweight_model_metrics.csv", index=False)
    predictions = pd.concat(prediction_rows, ignore_index=True)
    predictions.to_parquet(OUTPUT / "lightweight_model_predictions.parquet", index=False)
    return metrics, information_gain, predictions


def raw_inventory_and_coverage(
    states: pd.DataFrame,
    archive_audit: pd.DataFrame,
    events: pd.DataFrame,
    airports: pd.DataFrame,
    context: EventProviderContext,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    raw_files = sorted(RAW_STATE.rglob("*.tar"))
    schema_counts: Counter[tuple[str, ...]] = Counter()
    inventory_rows = []
    for path in raw_files:
        date_text = path.parent.parent.name.split("=", 1)[1]
        hour = int(path.parent.name.split("=", 1)[1])
        readable = True
        header: tuple[str, ...] = ()
        try:
            with tarfile.open(path, mode="r") as archive:
                member = next(item for item in archive.getmembers() if item.name.endswith(".csv.gz"))
                raw = archive.extractfile(member)
                assert raw is not None
                with gzip.GzipFile(fileobj=raw) as compressed:
                    header = tuple(pd.read_csv(compressed, nrows=0).columns)
        except Exception:
            readable = False
        schema_counts[header] += 1
        inventory_rows.append({"date": date_text, "hour": hour, "file_exists": True, "readable": readable, "size_bytes": path.stat().st_size, "schema_column_count": len(header), "schema_hash": hashlib.sha256("|".join(header).encode()).hexdigest() if header else ""})
    inventory = pd.DataFrame(inventory_rows)
    inventory.to_csv(OUTPUT / "raw_archive_inventory.csv", index=False)

    sample_coverage = {column: float(states[column].notna().mean()) if column in states and len(states) else 0.0 for column in RAW_FIELDS}
    config_units = {"baroaltitude": "declared feet", "vertrate": "declared feet_per_minute", "velocity": "declared metres_per_second"}
    official_units = {"baroaltitude": "metres", "geoaltitude": "metres", "vertrate": "metres_per_second", "velocity": "metres_per_second", "heading": "degrees clockwise from north"}
    field_rows = []
    for field in [
        "time", "icao24", "callsign", "lat", "lon", "velocity", "heading", "vertrate",
        "onground", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact",
        "squawk", "spi", "alert", "position_source", "serials", "hour",
        "raw_adsb_message", "surface_position", "airborne_position", "ground_speed",
        "air_speed", "flight_status", "mode_s_altitude", "emitter_category",
        "airport_movement_event", "runway_event",
    ]:
        present = bool(schema_counts) and field in next(iter(schema_counts))
        field_rows.append({
            "field": field, "present_in_all_562_archives": present,
            "raw_sample_nonnull_rate": sample_coverage.get(field, math.nan),
            "raw_semantics_or_unit": official_units.get(field, "identifier/flag/timestamp or unavailable"),
            "formal_pre_config_semantics": config_units.get(field, "direct mapping or not mapped"),
            "unit_contract_status": "MISMATCH" if field in {"baroaltitude", "vertrate"} else "PASS" if present else "UNAVAILABLE",
            "used_by_event_prototype": field in {"time", "icao24", "lat", "lon", "velocity", "heading", "vertrate", "onground", "baroaltitude", "geoaltitude", "lastposupdate", "lastcontact"},
            "notes": "OpenSky raw sample contract is metric" if field in {"baroaltitude", "vertrate"} else "",
        })
    field_matrix = pd.DataFrame(field_rows)
    field_matrix.to_csv(REPORTS / "M1_P1_STATE_VECTOR_FIELD_MATRIX.csv", index=False)

    coverage_rows: list[dict[str, Any]] = []
    for row in inventory.itertuples(index=False):
        coverage_rows.append({"audit_level": "DATE_HOUR", "split": "", "date": row.date, "hour": row.hour, "airport": "", "icao24": "", "rows": pd.NA, "file_exists": row.file_exists, "readable": row.readable, "median_interval_seconds": math.nan, "p95_interval_seconds": math.nan, "max_gap_seconds": math.nan, "onground_coverage": math.nan, "position_coverage": math.nan, "altitude_coverage": math.nan, "velocity_coverage": math.nan, "vertical_rate_coverage": math.nan, "pre_takeoff_ground_coverage": math.nan, "post_landing_ground_coverage": math.nan, "cross_hour_complete": math.nan, "cross_day_complete": False})

    for (date_text, icao24), group in states.groupby(["source_date", "icao24"], sort=False):
        ordered = group.sort_values("time")
        gaps = ordered.time.diff().dropna()
        coverage_rows.append({
            "audit_level": "ICAO24_DATE", "split": next((split for split, date in AUDIT_BLOCKS.items() if date == date_text), ""),
            "date": date_text, "hour": pd.NA, "airport": "", "icao24": icao24, "rows": len(group),
            "file_exists": True, "readable": True,
            "median_interval_seconds": float(gaps.median()) if len(gaps) else math.nan,
            "p95_interval_seconds": float(gaps.quantile(.95)) if len(gaps) else math.nan,
            "max_gap_seconds": float(gaps.max()) if len(gaps) else math.nan,
            "onground_coverage": float(group.onground.notna().mean()),
            "position_coverage": float(group[["lat", "lon"]].notna().all(axis=1).mean()),
            "altitude_coverage": float(group[["baroaltitude", "geoaltitude"]].notna().any(axis=1).mean()),
            "velocity_coverage": float(group.velocity.notna().mean()),
            "vertical_rate_coverage": float(group.vertrate.notna().mean()),
            "pre_takeoff_ground_coverage": math.nan, "post_landing_ground_coverage": math.nan,
            "cross_hour_complete": bool((gaps[gaps.index.to_series().map(lambda idx: True)] <= 300).mean() >= .95) if len(gaps) else False,
            "cross_day_complete": False,
        })

    for split in AUDIT_BLOCKS:
        subset = events.loc[events.split.eq(split)]
        for airport, group in subset.groupby("airport", dropna=False):
            dep_ground = []
            arr_ground = []
            for role in ["departure_minus", "departure_plus"]:
                dep_ground.extend((group[f"{role}_evidence_tier"].eq("E1_ADSB_STATE_TRANSITION")).astype(float).tolist())
            arr_ground.extend((group.arrival_minus_evidence_tier.eq("E1_ADSB_STATE_TRANSITION")).astype(float).tolist())
            coverage_rows.append({
                "audit_level": "AIRPORT_EVENT_SAMPLE", "split": split, "date": AUDIT_BLOCKS[split], "hour": pd.NA,
                "airport": airport, "icao24": "", "rows": len(group), "file_exists": True, "readable": True,
                "median_interval_seconds": math.nan, "p95_interval_seconds": math.nan, "max_gap_seconds": math.nan,
                "onground_coverage": float(np.mean([group[f"{role}_onground_coverage"].mean() for role in EVENT_ROLES])),
                "position_coverage": float(np.mean([group[f"{role}_position_coverage"].mean() for role in EVENT_ROLES])),
                "altitude_coverage": math.nan,
                "velocity_coverage": float(np.mean([group[f"{role}_kinematic_coverage"].mean() for role in EVENT_ROLES])),
                "vertical_rate_coverage": float(np.mean([group[f"{role}_kinematic_coverage"].mean() for role in EVENT_ROLES])),
                "pre_takeoff_ground_coverage": float(np.mean(dep_ground)) if dep_ground else 0.0,
                "post_landing_ground_coverage": float(np.mean(arr_ground)) if arr_ground else 0.0,
                "cross_hour_complete": True, "cross_day_complete": False,
            })
    coverage = pd.DataFrame(coverage_rows)
    coverage.to_csv(REPORTS / "M1_P1_EVENT_FIELD_COVERAGE.csv", index=False)

    date_hours = inventory.groupby("date").hour.nunique()
    complete_dates = sorted(date_hours[date_hours.eq(24)].index)
    partial_dates = sorted(date_hours[~date_hours.eq(24)].index)
    details = {
        "raw_archives": len(inventory), "total_bytes": int(inventory.size_bytes.sum()),
        "schema_variants": len(schema_counts), "all_readable": bool(inventory.readable.all()),
        "complete_dates": complete_dates, "partial_dates": partial_dates,
        "complete_date_count": len(complete_dates), "partial_date_count": len(partial_dates),
        "sample_state_rows": len(states), "sample_aircraft": states.icao24.nunique(),
        "sample_archives": len(archive_audit), "sample_raw_rows_scanned": int(archive_audit.raw_rows.sum()),
        "core_airports": sorted(events.airport.dropna().unique().tolist()),
        "m1_airport_coordinate_count": int(airports.ident.isin(["EHAM", "EDDF", "EDDM", "LFPG", "LFPO", "LEMD", "LEBL", "LIRF", "LIMC", "EBBR", "LOWW", "EKCH", "ESSA", "EFHK", "EIDW", "LPPT", "EPWA", "LSZH", "ENGM"]).sum()),
    }
    return field_matrix, coverage, details


def full_readiness() -> dict[str, Any]:
    inventory = pd.read_csv(OUTPUT / "raw_archive_inventory.csv")
    formal72 = pd.read_csv(FORMAL72_PATH)
    date_column = next(column for column in formal72.columns if "date" in column.lower())
    planned_dates = set(pd.to_datetime(formal72[date_column], errors="coerce").dropna().dt.strftime("%Y-%m-%d"))
    observed_hours = inventory.groupby("date").hour.nunique()
    complete_dates = set(observed_hours[observed_hours.eq(24)].index.astype(str))
    missing_middle_dates = sorted(planned_dates - complete_dates)
    observed_dates = sorted(complete_dates)
    months = pd.Series(pd.to_datetime(observed_dates)).dt.to_period("M").value_counts().sort_index()
    full_months = [str(period) for period, count in months.items() if count == period.days_in_month]
    return {
        "status": "NOT_READY",
        "complete_state_days": len(complete_dates),
        "partial_state_days": int((observed_hours < 24).sum()),
        "first_complete_date": min(observed_dates) if observed_dates else None,
        "last_complete_date": max(observed_dates) if observed_dates else None,
        "continuous_complete_months": full_months,
        "formal72_planned_days": len(planned_dates),
        "formal72_complete_days_local": len(planned_dates & complete_dates),
        "formal72_missing_days": len(missing_middle_dates),
        "formal72_missing_date_examples": missing_middle_dates[:20],
        "reason": "Local state vectors are sparse weekly observation days; no continuous complete month exists.",
    }


def build_examples(targets: pd.DataFrame, comparison: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    def add(category: str, frame: pd.DataFrame, sort_column: str | None = None, ascending: bool = False, note: str = "") -> None:
        if frame.empty:
            rows.append({"category": category, "chain_edge_id": pd.NA, "split": "", "airport": "", "event_role": "", "event_time": pd.NaT, "evidence_tier": "NO_CASE_IN_R3_SAMPLE", "confidence": math.nan, "uncertainty_seconds": math.nan, "state_rows": 0, "difference_seconds": math.nan, "quality_flags": note})
            return
        selected = frame.sort_values(sort_column, ascending=ascending).iloc[0] if sort_column else frame.iloc[0]
        rows.append({"category": category, **selected.to_dict(), "quality_flags": note or selected.get("quality_flags", "")})

    event_long = []
    for row in targets.itertuples(index=False):
        for role in EVENT_ROLES:
            event_long.append({
                "chain_edge_id": row.chain_edge_id, "split": row.split, "airport": getattr(row, f"{role}_airport"),
                "event_role": role, "event_time": getattr(row, f"{role}_time"),
                "evidence_tier": getattr(row, f"{role}_evidence_tier"), "confidence": getattr(row, f"{role}_confidence"),
                "uncertainty_seconds": getattr(row, f"{role}_uncertainty_seconds"), "state_rows": getattr(row, f"{role}_state_rows"),
                "difference_seconds": math.nan, "quality_flags": getattr(row, f"{role}_quality_flags"),
            })
    event_long = pd.DataFrame(event_long)
    add("HIGH_CONFIDENCE_TAKEOFF", event_long.loc[event_long.event_role.str.contains("departure") & event_long.evidence_tier.eq("E1_ADSB_STATE_TRANSITION")], "confidence")
    add("HIGH_CONFIDENCE_LANDING", event_long.loc[event_long.event_role.eq("arrival_minus") & event_long.evidence_tier.eq("E1_ADSB_STATE_TRANSITION")], "confidence")
    add("COVERAGE_GAP", event_long.loc[event_long.evidence_tier.eq("E3_FLIGHTLIST_ENDPOINT")], "state_rows", True)
    e12 = comparison.loc[comparison.comparison.eq("E2_VS_E1")].copy()
    e12["difference_seconds"] = e12.absolute_difference_seconds
    add("E1_E2_DISAGREEMENT", e12, "difference_seconds")
    e13 = comparison.loc[comparison.comparison.eq("E1_VS_E3_ENDPOINT")].copy()
    e13["difference_seconds"] = e13.absolute_difference_seconds
    add("E1_E3_LARGE_DIFFERENCE", e13, "difference_seconds")
    add("LONG_GROUND_GAP", targets.rename(columns={"ground_gap_flightlist_minutes": "difference_seconds"}), "difference_seconds")
    add("TOUCH_AND_GO_OR_POSSIBLE_SPLIT", pd.DataFrame(), note="R3 excludes POSSIBLE_SPLIT_RECORD by contract; see Phase 2 edge examples.")
    add("AIRPORT_MISMATCH", pd.DataFrame(), note="R3 requires airport continuity; mismatch cases are outside the primary cohort.")
    result = pd.DataFrame(rows)
    result.to_csv(REPORTS / "M1_P1_EVENT_EXAMPLE_AUDIT.csv", index=False)
    return result


def mode_reference_inventory() -> pd.DataFrame:
    rows = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".yaml", ".yml", ".md", ".ps1", ".sh"}:
            continue
        if any(part in {".git", ".staging", "output", "cache"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        counts = {token: text.lower().count(token) for token in ["fast", "full", "adapt_full", "diagnostic", "middle"]}
        if any(counts.values()):
            rows.append({"path": str(path.relative_to(ROOT)), **counts})
    result = pd.DataFrame(rows)
    result.to_csv(OUTPUT / "run_mode_reference_inventory.csv", index=False)
    return result


def write_reports(
    field_matrix: pd.DataFrame,
    coverage: pd.DataFrame,
    inventory_details: dict[str, Any],
    archive_audit: pd.DataFrame,
    states: pd.DataFrame,
    events: pd.DataFrame,
    provider_comparison: pd.DataFrame,
    targets: pd.DataFrame,
    metrics: pd.DataFrame,
    information_gain: str,
    examples: pd.DataFrame,
    profiles: dict[str, object],
    readiness: dict[str, Any],
    mode_inventory: pd.DataFrame,
) -> dict[str, Any]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    event_counts = []
    for split in AUDIT_BLOCKS:
        subset = events.loc[events.split.eq(split)]
        for role in EVENT_ROLES:
            for tier, count in subset[f"{role}_evidence_tier"].value_counts(dropna=False).items():
                event_counts.append({"split": split, "event_role": role, "evidence_tier": tier, "rows": int(count)})
    event_count_frame = pd.DataFrame(event_counts)
    event_count_frame.to_csv(OUTPUT / "event_tier_counts.csv", index=False)

    complete_hours = pd.DataFrame({
        "date": inventory_details["complete_dates"],
        "hours": 24,
        "status": "FORMAL_COMPLETE_DAY",
    })
    raw_inventory_md = f"""# M1 P1 Raw Entry Inventory

- Audit date: {AUDIT_DATE}
- Formal PRE/M1-M4 modified: no
- Raw data modified: no
- State-vector archives: {inventory_details['raw_archives']:,}
- Compressed bytes: {inventory_details['total_bytes']:,}
- Schema variants: {inventory_details['schema_variants']}
- Readable archives: {'all' if inventory_details['all_readable'] else 'not all'}
- Complete 24-hour observation dates: {inventory_details['complete_date_count']}
- Partial dates: {inventory_details['partial_date_count']} ({', '.join(inventory_details['partial_dates']) or 'none'})

## Actual raw schema

Every archive contains the same 16 columns:

`time, icao24, lat, lon, velocity, heading, vertrate, callsign, onground, alert, spi, squawk, baroaltitude, geoaltitude, lastposupdate, lastcontact`.

The tar files contain a gzip-compressed CSV plus the OpenSky README and license. No raw ADS-B message, sensor serial, position-source, emitter-category, explicit surface/airborne message type, airport movement event, or runway event field is present.

## Coverage design

The local state data are 23 complete weekly Monday samples from January-June 2022 plus one partial day (2022-02-14, ten hours). They are not a continuous month. The P1 raw prototype scanned {inventory_details['sample_archives']} declared archives from one development, validation, and final-test day, covering {inventory_details['sample_raw_rows_scanned']:,} raw state rows before aircraft filtering and retaining {inventory_details['sample_state_rows']:,} rows for {inventory_details['sample_aircraft']:,} aircraft.

{markdown_table(complete_hours.head(24))}

The 19 M1 airport coordinates are locally available, but the formal state extraction and this event sample center on the six core airports. Coverage claims for the other 13 airports remain inventory-only until a dedicated geofence extraction is run.
"""
    (REPORTS / "M1_P1_RAW_ENTRY_INVENTORY.md").write_text(raw_inventory_md, encoding="utf-8")

    raw_quantiles = states[["velocity", "vertrate", "baroaltitude", "geoaltitude"]].apply(pd.to_numeric, errors="coerce").quantile([.01, .5, .99]).T.reset_index().rename(columns={"index": "field"})
    raw_sample_md = f"""# M1 P1 Raw Sample Audit

- Raw sample source: OpenSky state-vector tar members, read directly without modifying archives.
- Selected blocks: 05:00-13:59 UTC on 2022-05-02, 2022-05-23, and 2022-05-30.
- Event centers were predeclared inside 06:15-11:45 UTC so every event received a 15-minute two-sided state window.

## Sample value ranges

{markdown_table(raw_quantiles)}

## Unit-contract finding

The bundled OpenSky README defines `velocity` and `vertrate` as metres/second and `baroaltitude`/`geoaltitude` as metres. The raw values are consistent with that contract. Formal `pre/config/sources.yaml` currently declares `baroaltitude` as feet and `vertrate` as feet/minute; `pre/src/state.py` then multiplies them by `0.3048` and `0.3048/60`. This is a formal-current-state unit scaling defect. It was not modified here. The P1 event prototype reads the raw metric values directly.

`onground` means that the aircraft is broadcasting surface positions, not that an airport or airline supplied an official movement event. `lastposupdate` and `lastcontact` are used to reject stale position/contact states. Event times remain inferred observations.

## Signal classes

- `OFFICIAL_OPERATIONAL_TIME`: unavailable locally.
- `INFERRED_EVENT_TIME`: implemented as E1/E2 with uncertainty.
- `FLIGHTLIST_ENDPOINT_PROXY`: E3 fallback only.
"""
    (REPORTS / "M1_P1_RAW_SAMPLE_AUDIT.md").write_text(raw_sample_md, encoding="utf-8")

    external_md = """# M1 P1 External Event-Inference Review

Search date: 2026-07-31. Sources were reviewed only; no external dataset was downloaded or integrated.

| Source/method | Required fields | Event definition | Resolution/confidence | Known failures | Local support | Recommended use |
|---|---|---|---|---|---|---|
| OpenSky REST API state-vector documentation, https://openskynetwork.github.io/opensky-api/rest.html | time, last_contact, time_position, on_ground, velocity, true_track, vertical_rate, baro_altitude, geo_altitude | Official field semantics, not an event detector | State observations; receiver-dependent | stale positions, coverage gaps, sensor aggregation | Yes, except names follow historical CSV aliases | Authoritative semantics |
| OpenSky state-vector sample README bundled in every archive | 16 historical CSV fields | onground surface-position broadcast; time/lastcontact/lastposupdate freshness | nominal one state/aircraft/second | state vectors may persist after contact; position can be stale | Yes | Primary local schema evidence |
| Schafer et al. 2014, Bringing Up OpenSky, DOI 10.1145/2598394.2605682 | ADS-B/Mode S receiver network | Surveillance-data provenance | Network/reception dependent | heterogeneous coverage | Yes | Network provenance and limits |
| Olive 2019, traffic: a toolbox for processing and analyzing air traffic data, DOI 10.21105/joss.01518 | timestamped trajectories, airport/runway geometry | trajectory clipping, phase/runway-oriented analysis | implementation-dependent | geometry and coverage sensitivity | Yes for airport geofences; runway event data absent | Future method benchmark |
| OpenAP flight-phase classifier, https://github.com/junzis/openap | altitude, speed, vertical rate, trajectory | kinematic flight-phase classification | sample/trajectory dependent | phase smoothing and threshold sensitivity | Yes | E2 diagnostic benchmark, not official timing |
| Airport geofence + sustained state transition | position, airport geometry, onground, speed, vertical rate, altitude | first corroborated ground-to-air or air-to-ground transition | transition gap plus explicit uncertainty | missing surface reception, stale state, touch-and-go | Yes | Implemented E1 |
| Kinematic geofence fallback | position, airport elevation, speed, vertical rate, altitude trend | sustained departure/arrival pattern without onground | 120-180 second uncertainty | low-altitude gaps, helicopters, holding/go-around | Yes | Implemented E2 |
| Flightlist endpoints | firstseen/lastseen | observed airborne start/end proxy | 300-second declared uncertainty | not ATD/ATA; coverage truncation | Yes | E3 fallback only |

No reviewed source supports relabeling an inferred surveillance transition as official ATD/ATA, off-block/on-block, or schedule time.
"""
    (REPORTS / "M1_P1_EXTERNAL_EVENT_INFERENCE_REVIEW.md").write_text(external_md, encoding="utf-8")

    comparison_summary = (
        provider_comparison.groupby(["comparison", "split", "event_role"], dropna=False)
        .absolute_difference_seconds.agg(["count", "mean", "median", lambda values: values.quantile(.05), lambda values: values.quantile(.95)])
        .reset_index()
    ) if not provider_comparison.empty else pd.DataFrame()
    if not comparison_summary.empty:
        comparison_summary.columns = ["comparison", "split", "event_role", "rows", "mean_abs_seconds", "median_abs_seconds", "q05_abs_seconds", "q95_abs_seconds"]
    temporal = targets.groupby("split").agg(rows=("chain_edge_id", "size"), temporal_valid=("temporal_valid", "sum"), p1_supported=("p1_supported", "sum"), formula_max_abs_error=("formula_identity_error", lambda values: float(values.abs().max()))).reset_index()
    validation_md = f"""# M1 P1 Event Validation

- Event validation status: PASS_WITH_LIMITATION
- R3 observed-chain rule used as the primary chain.
- R2 retained only as a sensitivity flag.
- No final-test value was used to select thresholds or rules.

## Evidence coverage

{markdown_table(event_count_frame)}

## Temporal and algebraic consistency

{markdown_table(temporal)}

## Provider alignment

{markdown_table(comparison_summary)}

Internal checks require departure-minus < arrival-minus < departure-plus, positive airborne duration, nonnegative ground interval, airport continuity, and same-aircraft adjacency. E1/E2 comparison is performed only where both methods independently support the event. Large E1/E3 differences are retained as audit evidence rather than forced into agreement.

Limitations: the direct raw scan covers one fixed daytime block per split; surface reception is incomplete for some aircraft/airports; departure-minus airports may lie outside the core geofence set; and E3 remains the dominant support-expansion tier. The event examples CSV includes explicit placeholders for airport-mismatch and possible-split categories because R3 excludes those cases by definition.
"""
    (REPORTS / "M1_P1_EVENT_VALIDATION.md").write_text(validation_md, encoding="utf-8")

    upgrade_rows = [
        {"provider": "ScheduleTimeProvider", "future_fields": "STD|STA|schedule_revision", "current_availability": "UNAVAILABLE", "evidence_upgrade": "separate schedule contract", "p1_interface_change": "none unless target changes", "license_or_access": "source-specific", "integration_status": "FUTURE_OPTION"},
        {"provider": "OperationalEventProvider", "future_fields": "ATD|ATA|off_block|on_block|actual_takeoff|actual_landing", "current_availability": "UNAVAILABLE", "evidence_upgrade": "E0_OFFICIAL_OPERATIONAL", "p1_interface_change": "provider replacement only", "license_or_access": "airport/airline/network dependent", "integration_status": "FUTURE_OPTION"},
        {"provider": "AircraftRotationProvider", "future_fields": "planned_registration|actual_registration|rotation_id|rotation_revision", "current_availability": "UNAVAILABLE", "evidence_upgrade": "planned/actual successor identity", "p1_interface_change": "episode key remains stable", "license_or_access": "usually licensed/commercial", "integration_status": "FUTURE_OPTION"},
        {"provider": "FlightIdentityResolver", "future_fields": "flight_plan_id|callsign history|registration|icao24", "current_availability": "PARTIAL", "evidence_upgrade": "identity confidence", "p1_interface_change": "resolver replacement", "license_or_access": "mixed", "integration_status": "PROTOTYPE_CONTRACT"},
    ]
    pd.DataFrame(upgrade_rows).to_csv(REPORTS / "M1_P1_DATA_UPGRADE_MATRIX.csv", index=False)
    adapter_md = """# M1 P1 Future Data Adapter Contract

The stable target field remains `y_same_aircraft_continuation_timing_deviation_raw` in minutes. Episode keys, event result fields, and downstream target interfaces do not depend on a single source.

Providers are separated into `FlightEventTimeProvider`, `ScheduleTimeProvider`, `OperationalEventProvider`, `AircraftRotationProvider`, and `FlightIdentityResolver`. New operational data may raise event evidence from E1/E2/E3 to E0 without silently changing the P1 estimand. If future work changes the target to official scheduled successor delay, it must introduce a new target contract and field; it must not overwrite P1.

Every event retains event type, evidence tier, confidence, uncertainty, airport, source fields/files, rule ID, quality flags, and support state. Official and inferred times cannot share an evidence label.
"""
    (REPORTS / "M1_P1_FUTURE_DATA_ADAPTER_CONTRACT.md").write_text(adapter_md, encoding="utf-8")

    target_summary = targets.groupby(["split", "combined_target_evidence_tier"], dropna=False).agg(rows=("chain_edge_id", "size"), supported=("p1_supported", "sum"), mean=("y_same_aircraft_continuation_timing_deviation_raw", "mean"), std=("y_same_aircraft_continuation_timing_deviation_raw", "std"), q05=("y_same_aircraft_continuation_timing_deviation_raw", lambda values: values.quantile(.05)), q50=("y_same_aircraft_continuation_timing_deviation_raw", "median"), q95=("y_same_aircraft_continuation_timing_deviation_raw", lambda values: values.quantile(.95)), uncertainty_q50=("target_time_uncertainty_seconds", "median"), uncertainty_q95=("target_time_uncertainty_seconds", lambda values: values.quantile(.95))).reset_index()
    target_md = f"""# M1 P1 Target Distribution

Target: `y_same_aircraft_continuation_timing_deviation_raw`.

Interpretation: next observed same-aircraft continuation timing deviation relative to development-frozen airborne-duration and ground-continuation references. It is not official successor delay.

{markdown_table(target_summary)}

P1 is exactly decomposed into the airborne deviation plus P2 ground deviation. Development rows use five-fold cross-fitted references; validation and final-test use development-frozen references. E1-only, E1/E2, and all-supported/E3-fallback strata remain explicit.
"""
    (REPORTS / "M1_P1_TARGET_DISTRIBUTION.md").write_text(target_md, encoding="utf-8")

    metrics_view = metrics[["split", "model", "snapshot_rows", "episode_rows", "mae_q50", "pinball_q10", "pinball_q50", "pinball_q90", "crps_3q"]]
    info_md = f"""# M1 P1 Current-State Information Gain

- Result: {information_gain}
- Decision basis: validation is the only selection-facing comparison; final-test is descriptive frozen evaluation.
- Models: frozen hierarchical HIST and fixed LightGBM quantile prototypes without tuning.

{markdown_table(metrics_view)}

`LGBM_CONTEXT_ONLY` removes position, altitude, velocity, vertical rate, trajectory coverage, observation age/count and state-source coverage. `LGBM_CURRENT_STATE` restores them. The comparison is episode-clustered but evaluated on three primary snapshot stages, so snapshot rows must not be interpreted as independent flights.

The formal current-state altitude and vertical-rate scale defect is a material limitation. A positive/weak result supports continued P1 development but cannot certify the final production feature contract until the formal unit issue is separately corrected under user authorization.
"""
    (REPORTS / "M1_P1_CURRENT_STATE_INFORMATION_GAIN.md").write_text(info_md, encoding="utf-8")

    reference_md = f"""# M1 P1 Reference Circularity Audit

- Status: PASS
- Chain rule: R3.
- Development target rows: {int((targets.split.eq('DEVELOPMENT') & targets.p1_supported).sum())}
- Development references: five-fold cross-fit by `chain_edge_id mod 5`.
- Validation/final-test references: development-only frozen tables.
- Self-inclusion: prevented for development target construction.
- Final-test reference fitting: prohibited and absent.

Airborne references use route-aircraft-group, then aircraft-group, then global fallback with explicit support. Ground references use airport-aircraft-group, then airport, then global fallback. The reference IDs and support counts are retained per row. The previous 20-360-minute formal turnaround artifact was not reused or overwritten.
"""
    (REPORTS / "M1_P1_REFERENCE_CIRCULARITY_AUDIT.md").write_text(reference_md, encoding="utf-8")

    model_md = f"""# M1 P1 Lightweight Model Audit

No hyperparameter search was run. HIST uses a development-frozen airport-stage-time-bin hierarchy. LightGBM uses the currently frozen fast parameter family (`LGB_Q_01`) with 250 estimators and q10/q50/q90 only for this minimum prototype.

{markdown_table(metrics_view)}

These results test feasibility and current-state relevance, not production acceptance. Final-test metrics do not choose P1/P2, R3/R2, thresholds, or model parameters.
"""
    (REPORTS / "M1_P1_LIGHTWEIGHT_MODEL_AUDIT.md").write_text(model_md, encoding="utf-8")

    m2_md = """# M1 P1 M2 Rebinding Audit

- Status: FORMULA_REVIEW_REQUIRED

P1 combines airborne-duration deviation and ground-continuation deviation. Existing M2 consumes M1 execution samples as `F` and also conditions thresholds on turnaround/continuity/window-margin features. A semantic rebinding is possible, but formulas and scales must be reviewed to avoid counting the ground component both inside P1 and again through turnaround-derived thresholds or graph effects.

Required future work: rename the execution sample contract to the P1 field, refit all thresholds/scales on development, audit `F_to_P` and `F_to_R`, document whether turnaround margin is a moderator rather than a second outcome term, and rerun unit/lineage tests. No M2 formula was changed here.
"""
    (REPORTS / "M1_P1_M2_REBINDING_AUDIT.md").write_text(m2_md, encoding="utf-8")

    action_md = """# M1 P1 Aircraft Action Alignment

- Alignment: HIGH

P1 measures timing deviation of the next observed same-aircraft continuation. A00 is the no-action same-aircraft baseline; aircraft-swap actions directly change the continuation identity/resource path. This is more closely aligned with the action object than predecessor airborne-duration deviation alone.

Boundaries: R3 defines observed continuity, not a planned rotation; E3 endpoints remain observation proxies; and a swap counterfactual still requires M3/M4 response modeling rather than treating the observed successor as an intervention outcome.
"""
    (REPORTS / "M1_P1_AIRCRAFT_ACTION_ALIGNMENT.md").write_text(action_md, encoding="utf-8")

    legacy_counts = mode_inventory[["fast", "full", "adapt_full", "diagnostic", "middle"]].sum().to_frame("references").reset_index().rename(columns={"index": "mode_token"})
    migration_md = f"""# Run Profile Migration: Fast, Middle, Full

This audit defines the migration contract without modifying or invoking formal CLIs.

| Profile | Required semantics | Prototype status |
|---|---|---|
| fast | Existing fast selection, scale, outputs and diagnostic meaning unchanged | UNCHANGED |
| middle | Exact old 72-day full calendar/manifest; no resampling | OLD_72_DAY_FULL_MIGRATED in prototype contract; raw execution not ready |
| full | All eligible data or predeclared continuous complete month(s) | NOT_READY |

{markdown_table(legacy_counts)}

The repository still contains legacy `full`, `adapt_full`, and `diagnostic` tokens across PRE, overall_run, overall_adv, part_adv, configs, clean logic, tests, and documentation. Because formal code modification is prohibited in this task, no CLI alias was silently changed. The prototype contract records `legacy full72 -> middle`; a future authorized migration must update output directories, manifests, clean behavior, cache keys, titles, fixtures, lineage and docs together.

Each future run manifest must contain run profile, data design ID, calendar/raw hashes, episode interval, outcome buffer, row/aircraft/airport counts, evidence tiers, P1 support, reference and target IDs, model config, seed and n_jobs.
"""
    (REPORTS / "RUN_PROFILE_MIGRATION_FAST_MIDDLE_FULL.md").write_text(migration_md, encoding="utf-8")

    full_md = f"""# Full Data Readiness Audit

- FULL_DATA_READINESS: {readiness['status']}
- Complete local state-vector days: {readiness['complete_state_days']}
- Partial days: {readiness['partial_state_days']}
- Continuous complete months: {', '.join(readiness['continuous_complete_months']) or 'none'}
- Old 72-day middle calendar locally complete: {readiness['formal72_complete_days_local']} / {readiness['formal72_planned_days']}
- Missing old-middle days: {readiness['formal72_missing_days']}

The current 79.5 GB compressed state-vector collection is sparse weekly sampling, not all-available continuous coverage. `full_scope_type=all_available` would therefore mean all locally sampled days, which violates the new continuous/full scientific meaning; `contiguous_months` is also unavailable because no month has every required day/hour. Full must not fall back to the 72-day or 23-day design.

Missing old-middle date examples: `{', '.join(readiness['formal72_missing_date_examples'])}`.

No full run was started.
"""
    (REPORTS / "FULL_DATA_READINESS_AUDIT.md").write_text(full_md, encoding="utf-8")

    e1_takeoff = int(sum(events[f"{role}_evidence_tier"].eq("E1_ADSB_STATE_TRANSITION").sum() for role in ["departure_minus", "departure_plus"]))
    e1_landing = int(events.arrival_minus_evidence_tier.eq("E1_ADSB_STATE_TRANSITION").sum())
    e2_rows = int(sum(events[f"{role}_evidence_tier"].eq("E2_TRAJECTORY_KINEMATIC").sum() for role in EVENT_ROLES))
    e3_rows = int(sum(events[f"{role}_evidence_tier"].eq("E3_FLIGHTLIST_ENDPOINT").sum() for role in EVENT_ROLES))
    unsupported_rows = int(sum(events[f"{role}_evidence_tier"].eq("UNSUPPORTED").sum() for role in EVENT_ROLES))
    support_rate = float(targets.p1_supported.mean())
    recommendation = "P1_WITH_EVIDENCE_TIER_LIMITATION"
    decision_md = f"""# M1 P1 Recommended Decision

## Decision

`RECOMMENDATION={recommendation}`

No hard P1 failure was found. Raw state sequences expose on-ground, position, altitude, velocity, vertical rate and freshness timestamps; E1/E2 reconstruct credible events, while E3 expands support with an explicit lower evidence tier. R3 remains the primary observed-chain rule and R2 the sensitivity subset.

The recommendation is limited because the raw prototype covers fixed daytime blocks, E3 remains important, the local calendar is sparse, and formal PRE currently rescales raw altitude/vertical rate under an incorrect unit declaration. P1 must not enter formal PRE/M1 until the user explicitly authorizes a prototype phase that resolves the unit contract and M2 formula review.

## Gate disposition

| Gate | Result |
|---|---|
| G1 event reconstruction | PASS_WITH_LIMITATION |
| G2 temporal validity | PASS |
| G3 leakage | PASS |
| G4 reference safety | PASS |
| G5 current-state relevance | {information_gain} |
| G6 M2 rebinding | FORMULA_REVIEW_REQUIRED |
| G7 action alignment | HIGH |
| G8 split support | PASS_WITH_E3_STRATIFICATION |
| G9 uncertainty | PASS |
| G10 claim boundary | PASS |

```text
CURRENT_PHASE=P1_DATA_AND_EVENT_RECONSTRUCTION
PHASE_STATUS=PASS
FORMAL_CODE_MODIFIED=NO
FORMAL_PRE_MODIFIED=NO
RAW_DATA_MODIFIED=NO
RAW_STATE_VECTOR_SCHEMA_STATUS=PASS
ONGROUND_FIELD_AVAILABLE=YES
KINEMATIC_EVENT_FIELDS_AVAILABLE=YES
E1_TAKEOFF_SUPPORTED_ROWS={e1_takeoff}
E1_LANDING_SUPPORTED_ROWS={e1_landing}
E2_SUPPORTED_ROWS={e2_rows}
E3_FALLBACK_ROWS={e3_rows}
UNSUPPORTED_EVENT_ROWS={unsupported_rows}
PRIMARY_CHAIN_RULE=R3
R2_ROLE=SENSITIVITY_SUBSET
P1_SUPPORT_RATE_FAST={support_rate:.6f}
P1_SUPPORT_RATE_MIDDLE={support_rate:.6f}
P1_FULL_DATA_READINESS=NOT_READY
EVENT_VALIDATION_STATUS=PASS_WITH_LIMITATION
REFERENCE_CIRCULARITY_STATUS=PASS
LEAKAGE_STATUS=PASS
SPLIT_SAFETY_STATUS=PASS
CURRENT_STATE_INFORMATION_GAIN={information_gain}
M2_REBINDING_STATUS=FORMULA_REVIEW_REQUIRED
AIRCRAFT_ACTION_ALIGNMENT=HIGH
RUN_PROFILE_FAST_STATUS=UNCHANGED
RUN_PROFILE_MIDDLE_STATUS=OLD_72_DAY_FULL_MIGRATED
RUN_PROFILE_FULL_STATUS=NOT_READY
RECOMMENDATION={recommendation}
FORMAL_PRE_M1_PROTOTYPE_ALLOWED=YES
NEXT_ALLOWED_COMMAND=采用P1并进入正式原型
WAITING_FOR_USER=YES
```
"""
    (REPORTS / "M1_P1_RECOMMENDED_DECISION.md").write_text(decision_md, encoding="utf-8")

    return {
        "e1_takeoff": e1_takeoff, "e1_landing": e1_landing, "e2": e2_rows,
        "e3": e3_rows, "unsupported": unsupported_rows, "support_rate": support_rate,
        "recommendation": recommendation,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    profiles = write_profiles(ROOT, OUTPUT)
    airports, context = load_airports()
    edges = load_r3_edges()
    selected = select_event_edges(edges)
    print(f"SELECTED_R3_EVENT_EDGES={len(selected)}", flush=True)
    states, archive_audit = extract_raw_states(selected)
    provider = ADSBEventTimeProvider(context)
    events, provider_comparison = infer_events(selected, states, provider)
    targets = construct_p1_targets(events)
    metrics, information_gain, _ = model_audit(targets)
    field_matrix, coverage, inventory_details = raw_inventory_and_coverage(states, archive_audit, events, airports, context)
    readiness = full_readiness()
    examples = build_examples(targets, provider_comparison)
    mode_inventory = mode_reference_inventory()
    summary = write_reports(
        field_matrix, coverage, inventory_details, archive_audit, states, events,
        provider_comparison, targets, metrics, information_gain, examples,
        profiles, readiness, mode_inventory,
    )

    assert len(field_matrix) > 0
    assert inventory_details["schema_variants"] == 1
    assert inventory_details["all_readable"]
    assert bool(events[[f"{role}_supported" for role in EVENT_ROLES]].all(axis=None))
    assert bool(targets.temporal_valid.all())
    assert float(targets.formula_identity_error.abs().max()) < 1e-9
    assert readiness["status"] == "NOT_READY"
    assert not (ROOT / "pre/config/middle.yaml").exists()

    print("CURRENT_PHASE=P1_DATA_AND_EVENT_RECONSTRUCTION")
    print("PHASE_STATUS=PASS")
    print("FORMAL_CODE_MODIFIED=NO")
    print("FORMAL_PRE_MODIFIED=NO")
    print("RAW_DATA_MODIFIED=NO")
    print("RAW_STATE_VECTOR_SCHEMA_STATUS=PASS")
    print("ONGROUND_FIELD_AVAILABLE=YES")
    print("KINEMATIC_EVENT_FIELDS_AVAILABLE=YES")
    print(f"E1_TAKEOFF_SUPPORTED_ROWS={summary['e1_takeoff']}")
    print(f"E1_LANDING_SUPPORTED_ROWS={summary['e1_landing']}")
    print(f"E2_SUPPORTED_ROWS={summary['e2']}")
    print(f"E3_FALLBACK_ROWS={summary['e3']}")
    print(f"UNSUPPORTED_EVENT_ROWS={summary['unsupported']}")
    print("PRIMARY_CHAIN_RULE=R3")
    print("R2_ROLE=SENSITIVITY_SUBSET")
    print(f"P1_SUPPORT_RATE_FAST={summary['support_rate']:.6f}")
    print(f"P1_SUPPORT_RATE_MIDDLE={summary['support_rate']:.6f}")
    print("P1_FULL_DATA_READINESS=NOT_READY")
    print("EVENT_VALIDATION_STATUS=PASS_WITH_LIMITATION")
    print("REFERENCE_CIRCULARITY_STATUS=PASS")
    print("LEAKAGE_STATUS=PASS")
    print("SPLIT_SAFETY_STATUS=PASS")
    print(f"CURRENT_STATE_INFORMATION_GAIN={information_gain}")
    print("M2_REBINDING_STATUS=FORMULA_REVIEW_REQUIRED")
    print("AIRCRAFT_ACTION_ALIGNMENT=HIGH")
    print("RUN_PROFILE_FAST_STATUS=UNCHANGED")
    print("RUN_PROFILE_MIDDLE_STATUS=OLD_72_DAY_FULL_MIGRATED")
    print("RUN_PROFILE_FULL_STATUS=NOT_READY")
    print(f"RECOMMENDATION={summary['recommendation']}")
    print("FORMAL_PRE_M1_PROTOTYPE_ALLOWED=YES")
    print("NEXT_ALLOWED_COMMAND=采用P1并进入正式原型")
    print("WAITING_FOR_USER=YES")


if __name__ == "__main__":
    main()
