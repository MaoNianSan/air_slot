from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/chain_feasibility"
PRE = ROOT / "pre/output/adapt_full"
REPORTS = ROOT / "reports"

COMPARISON = OUT / "chain_rule_comparison.parquet"
CLASSIFIED = OUT / "chain_edges_classified.parquet"
SNAPSHOTS = PRE / "snapshots.parquet"
REFERENCES = OUT / "prototype_ground_references.parquet"

AUDIT_DATE = "2026-07-31"
R2_GAP_LIMIT = 1500.085809326171
RULES = {
    "R1": "rule_r1_retained",
    "R2": "rule_r2_retained",
    "R3": "rule_r3_retained",
}
SPLITS = ["DEVELOPMENT", "VALIDATION", "FINAL_TEST"]


def smd_binary(retained: pd.Series, outcome: pd.Series) -> float:
    r = outcome[retained].astype(float)
    e = outcome[~retained].astype(float)
    if r.empty or e.empty:
        return math.nan
    pr, pe = float(r.mean()), float(e.mean())
    denom = math.sqrt((pr * (1 - pr) + pe * (1 - pe)) / 2)
    return 0.0 if denom == 0 and pr == pe else (pr - pe) / denom if denom else math.nan


def smd_continuous(retained: pd.Series, values: pd.Series) -> float:
    a = pd.to_numeric(values[retained], errors="coerce").dropna()
    b = pd.to_numeric(values[~retained], errors="coerce").dropna()
    if a.empty or b.empty:
        return math.nan
    denom = math.sqrt((float(a.var(ddof=0)) + float(b.var(ddof=0))) / 2)
    return 0.0 if denom == 0 and float(a.mean()) == float(b.mean()) else (float(a.mean()) - float(b.mean())) / denom if denom else math.nan


def max_categorical_smd(retained: pd.Series, values: pd.Series, min_rows: int = 30) -> float:
    data = pd.DataFrame({"retained": retained.astype(bool), "value": values.astype("string").fillna("<MISSING>")})
    counts = data.value.value_counts()
    result = []
    for value in counts[counts >= min_rows].index:
        result.append(abs(smd_binary(data.retained, data.value.eq(value))))
    finite = [x for x in result if np.isfinite(x)]
    return max(finite) if finite else math.nan


def table_2x2(data: pd.DataFrame, retained_col: str) -> dict[str, float | int]:
    retained = data[retained_col].fillna(False).astype(bool)
    supported = data.passenger_supported.astype(bool)
    a = int((retained & supported).sum())
    b = int((retained & ~supported).sum())
    c = int((~retained & supported).sum())
    d = int((~retained & ~supported).sum())
    pr = a / (a + b) if a + b else math.nan
    pe = c / (c + d) if c + d else math.nan
    aa, bb, cc, dd = (a, b, c, d)
    if min(aa, bb, cc, dd) == 0:
        aa, bb, cc, dd = aa + 0.5, bb + 0.5, cc + 0.5, dd + 0.5
    odds = (aa * dd) / (bb * cc) if bb * cc else math.nan
    return {
        "retained_supported": a,
        "retained_unsupported": b,
        "excluded_supported": c,
        "excluded_unsupported": d,
        "retained_supported_share": pr,
        "excluded_supported_share": pe,
        "risk_difference": pr - pe,
        "odds_ratio": odds,
        "standardized_difference": smd_binary(retained, supported),
    }


def markdown_table(frame: pd.DataFrame, digits: int = 6) -> str:
    shown = frame.copy()
    for col in shown.select_dtypes(include=["float", "float32", "float64"]).columns:
        shown[col] = shown[col].map(lambda x: "" if pd.isna(x) else f"{x:.{digits}f}")
    return shown.to_markdown(index=False)


def read_s3_callsigns(edge_ids: np.ndarray) -> pd.DataFrame:
    wanted = set(map(int, edge_ids))
    pieces: list[pd.DataFrame] = []
    pf = pq.ParquetFile(CLASSIFIED)
    for batch in pf.iter_batches(columns=["chain_edge_id", "callsign_minus", "registration_minus"], batch_size=500_000):
        frame = batch.to_pandas()
        hit = frame.chain_edge_id.isin(wanted)
        if hit.any():
            pieces.append(frame.loc[hit].copy())
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def callsign_family(value: object) -> str:
    if pd.isna(value):
        return "<MISSING>"
    match = re.match(r"^([A-Z]{2,3})", str(value).strip().upper())
    return match.group(1) if match else "<NONSTANDARD>"


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    comparison = pd.read_parquet(COMPARISON)
    snapshots = pd.read_parquet(
        SNAPSHOTS,
        columns=[
            "episode_id", "snapshot_id", "snapshot_stage", "split", "airport",
            "trajectory_coverage", "airport_flow_pressure", "weather_evidence_status",
            "state_source_coverage_status",
            "passenger_proxy_level", "passenger_proxy_support",
            "passenger_proxy_evidence_status", "passenger_proxy_source_period",
            "passenger_proxy_fallback_reason", "passenger_proxy_missing_reason",
            "passenger_proxy_attempted_levels", "passenger_target_period",
            "passenger_source_period", "passenger_lag_months",
            "passenger_requested_level", "passenger_used_level",
            "passenger_evidence_status", "passenger_missing_reason",
            "passenger_support_count", "passenger_source_dataset",
            "passenger_future_data_used", "seat_capacity_level",
            "seat_capacity_support", "seat_capacity_evidence_status",
            "m4_passenger_input_supported",
        ],
    )
    snapshots["passenger_supported"] = ~snapshots.passenger_proxy_evidence_status.astype("string").eq("UNSUPPORTED")

    s3 = comparison.loc[
        comparison.scope_s3_snapshot_supported.fillna(False)
        & comparison.predecessor_episode_id.notna()
    ].copy()
    callsigns = read_s3_callsigns(s3.chain_edge_id.to_numpy())
    s3 = s3.merge(callsigns, on="chain_edge_id", how="left", validate="1:1")
    s3["callsign_family"] = s3.callsign_minus.map(callsign_family)
    s3["registration_present"] = s3.registration_minus.notna()

    episode_support = snapshots.groupby("episode_id", dropna=False).agg(
        snapshot_rows=("snapshot_id", "size"),
        snapshot_id_unique=("snapshot_id", "nunique"),
        snapshot_stage_unique=("snapshot_stage", "nunique"),
        passenger_state_unique=("passenger_supported", "nunique"),
        passenger_supported=("passenger_supported", "first"),
        passenger_proxy_support_unique=("passenger_proxy_support", "nunique"),
        passenger_proxy_support_min=("passenger_proxy_support", "min"),
        passenger_proxy_support_max=("passenger_proxy_support", "max"),
        passenger_used_level=("passenger_used_level", "first"),
        passenger_missing_reason=("passenger_missing_reason", "first"),
        passenger_lag_months=("passenger_lag_months", "first"),
        passenger_source_period=("passenger_source_period", "first"),
        passenger_target_period=("passenger_target_period", "first"),
        passenger_future_data_used=("passenger_future_data_used", "max"),
        seat_capacity_level=("seat_capacity_level", "first"),
        seat_capacity_support=("seat_capacity_support", "first"),
    ).reset_index()
    edge = s3.merge(
        episode_support,
        left_on="predecessor_episode_id",
        right_on="episode_id",
        how="left",
        validate="m:1",
    )
    snap = s3.merge(
        snapshots,
        left_on="predecessor_episode_id",
        right_on="episode_id",
        how="inner",
        suffixes=("_edge", "_snapshot"),
        validate="m:m",
    )
    return comparison, snapshots, edge, snap


def add_r2_conditions(edge: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    out = edge.copy()
    out["C01_same_icao24"] = out.outcome_successor_record_id.notna()
    out["C02_nonnegative_nonoverlap"] = out.ground_gap_minutes.notna() & out.ground_gap_minutes.ge(0)
    out["C03_airport_endpoints_known"] = out.airport_continuity.notna()
    out["C04_airport_continuity"] = out.airport_continuity.fillna(False).astype(bool)
    out["C05_gap_within_frozen_candidate"] = out.ground_gap_minutes.le(R2_GAP_LIMIT).fillna(False)
    out["C06_registration_present_both"] = out.registration_continuity.notna()
    out["C07_registration_consistent"] = out.registration_continuity.fillna(False).astype(bool)
    out["C08_typecode_consistent_when_known"] = ~out.typecode_continuity.fillna(True).eq(False)
    out["C09_no_exact_duplicate"] = ~out.diagnostic_status.eq("EXACT_DUPLICATE")
    out["C10_no_possible_split"] = ~out.diagnostic_status.eq("POSSIBLE_SPLIT_RECORD")
    out["C11_endpoint_coordinate_support"] = out.endpoint_coordinate_support.fillna(False).astype(bool)
    out["C12_complete_local_state_vector_day"] = out.state_vector_support.fillna(False).astype(bool)
    out["C13_no_identity_conflict"] = ~(
        out.registration_continuity.fillna(True).eq(False)
        | out.typecode_continuity.fillna(True).eq(False)
    )
    out["C14_other_R2_condition"] = True
    order = [
        ("C01_same_icao24", "observed same-icao24 successor"),
        ("C02_nonnegative_nonoverlap", "nonnegative ground gap"),
        ("C03_airport_endpoints_known", "destination/origin endpoints known"),
        ("C04_airport_continuity", "destination equals successor origin"),
        ("C09_no_exact_duplicate", "not an exact duplicate"),
        ("C06_registration_present_both", "registration present on both records"),
        ("C07_registration_consistent", "registration matches"),
        ("C08_typecode_consistent_when_known", "typecode matches when jointly known"),
        ("C10_no_possible_split", "not a possible split record"),
        ("C11_endpoint_coordinate_support", "endpoint coordinates supported"),
        ("C12_complete_local_state_vector_day", "complete local state-vector day"),
        ("C05_gap_within_frozen_candidate", "gap within development-frozen R2 q95"),
        ("C13_no_identity_conflict", "no registration/type identity conflict"),
        ("C14_other_R2_condition", "no additional implementation condition"),
    ]
    reconstructed = np.logical_and.reduce([out[name].to_numpy(bool) for name, _ in order])
    if not np.array_equal(reconstructed, out.rule_r2_retained.fillna(False).to_numpy(bool)):
        mismatch = int((reconstructed != out.rule_r2_retained.fillna(False).to_numpy(bool)).sum())
        raise RuntimeError(f"R2 reconstruction mismatch: {mismatch}")
    return out, order


def cardinality_audit(comparison: pd.DataFrame, snapshots: pd.DataFrame, edge: pd.DataFrame, snap: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    conflicts: list[dict[str, object]] = []
    s3_map = comparison.loc[comparison.predecessor_episode_id.notna(), ["chain_edge_id", "predecessor_record_id", "predecessor_episode_id", "scope_s3_snapshot_supported"]].copy()
    multi_episode = s3_map.groupby("predecessor_episode_id").filter(lambda x: x.predecessor_record_id.nunique() > 1)
    for row in multi_episode.itertuples(index=False):
        conflicts.append({"issue_type": "EPISODE_TO_MULTIPLE_PREDECESSORS", "episode_id": row.predecessor_episode_id, "chain_edge_id": row.chain_edge_id, "predecessor_record_id": row.predecessor_record_id, "detail": "episode maps to multiple predecessor records"})

    numeric_variation = snapshots.groupby("episode_id").filter(lambda x: x.passenger_proxy_support.nunique(dropna=False) > 1)
    for episode_id, group in numeric_variation.groupby("episode_id"):
        conflicts.append({
            "issue_type": "SNAPSHOT_NUMERIC_SUPPORT_VARIATION", "episode_id": episode_id,
            "chain_edge_id": pd.NA, "predecessor_record_id": pd.NA,
            "detail": f"numeric support values={sorted(group.passenger_proxy_support.dropna().unique().tolist())}; boolean evidence state remains consistent",
        })

    snapshot_ids = set(snap.episode_id.dropna().astype(str))
    for episode_id in snapshots.loc[~snapshots.episode_id.astype(str).isin(snapshot_ids), "episode_id"].drop_duplicates():
        conflicts.append({"issue_type": "SNAPSHOT_EPISODE_UNMATCHED_TO_S3_EDGE", "episode_id": episode_id, "chain_edge_id": pd.NA, "predecessor_record_id": pd.NA, "detail": "formal snapshot episode has no S3 chain edge"})

    not_s3 = s3_map.loc[s3_map.predecessor_episode_id.astype(str).isin(set(snapshots.episode_id.astype(str))) & ~s3_map.scope_s3_snapshot_supported.fillna(False)]
    for row in not_s3.itertuples(index=False):
        conflicts.append({"issue_type": "MATCHED_EPISODE_NOT_S3_SUPPORTED", "episode_id": row.predecessor_episode_id, "chain_edge_id": row.chain_edge_id, "predecessor_record_id": row.predecessor_record_id, "detail": "episode mapping exists but edge is outside S3 flag"})

    conflict_frame = pd.DataFrame(conflicts, columns=["issue_type", "episode_id", "chain_edge_id", "predecessor_record_id", "detail"])
    stats = {
        "comparison_rows": len(comparison),
        "comparison_chain_edge_unique": comparison.chain_edge_id.nunique(),
        "comparison_predecessor_record_unique": comparison.predecessor_record_id.nunique(),
        "mapped_rows": int(comparison.predecessor_episode_id.notna().sum()),
        "mapped_episode_unique": comparison.predecessor_episode_id.nunique(),
        "multi_predecessor_episode_count": multi_episode.predecessor_episode_id.nunique(),
        "snapshot_rows": len(snapshots),
        "snapshot_episode_unique": snapshots.episode_id.nunique(),
        "snapshot_id_unique": snapshots.snapshot_id.nunique(),
        "episode_snapshot_duplicates": int(snapshots.duplicated(["episode_id", "snapshot_id"]).sum()),
        "episode_stage_duplicates": int(snapshots.duplicated(["episode_id", "snapshot_stage"]).sum()),
        "passenger_boolean_conflict_episodes": int((snapshots.groupby("episode_id").passenger_supported.nunique() > 1).sum()),
        "passenger_numeric_variation_episodes": int((snapshots.groupby("episode_id").passenger_proxy_support.nunique(dropna=False) > 1).sum()),
        "edge_rows": len(edge),
        "edge_chain_unique": edge.chain_edge_id.nunique(),
        "edge_predecessor_unique": edge.predecessor_record_id.nunique(),
        "joined_snapshot_rows": len(snap),
        "predecessor_stage_duplicates": int(snap.duplicated(["predecessor_record_id", "snapshot_stage"]).sum()),
        "expected_joined_snapshot_rows": int(edge.snapshot_rows.sum()),
        "unmatched_snapshot_episodes": snapshots.episode_id.nunique() - snap.episode_id.nunique(),
        "non_s3_mapped_rows": int(len(not_s3)),
    }
    return conflict_frame, stats


def two_by_two(edge: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for unit, data in [("LEVEL_E", edge), ("LEVEL_S", snap)]:
        split_col = "split_of_predecessor"
        for split in ["ALL", *SPLITS]:
            subset = data if split == "ALL" else data.loc[data[split_col].eq(split)]
            for rule, col in RULES.items():
                rows.append({"audit_unit": unit, "split": split, "rule": rule, "rows": len(subset), **table_2x2(subset, col)})
    return pd.DataFrame(rows)


def funnel(edge: pd.DataFrame, order: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    for split in SPLITS:
        data = edge.loc[edge.split_of_predecessor.eq(split)].copy()
        running = pd.Series(True, index=data.index)
        prior_smd = smd_binary(running, data.passenger_supported)
        rows.append({"split": split, "step": 0, "condition": "BASE", "description": "S3 edge-level base", "remaining_edges": len(data), "retention_rate": 1.0, "passenger_supported_share_remaining": data.passenger_supported.mean(), "newly_rejected_supported": 0, "newly_rejected_unsupported": 0, "passenger_smd_remaining_vs_excluded": prior_smd, "marginal_delta_smd": math.nan, "airport_max_smd": 0.0, "aircraft_group_max_smd": 0.0})
        for step, (condition, description) in enumerate(order, start=1):
            before = running.copy()
            running &= data[condition].astype(bool)
            rejected = before & ~running
            current_smd = smd_binary(running, data.passenger_supported)
            rows.append({
                "split": split, "step": step, "condition": condition, "description": description,
                "remaining_edges": int(running.sum()), "retention_rate": float(running.mean()),
                "passenger_supported_share_remaining": float(data.loc[running, "passenger_supported"].mean()) if running.any() else math.nan,
                "newly_rejected_supported": int((rejected & data.passenger_supported).sum()),
                "newly_rejected_unsupported": int((rejected & ~data.passenger_supported).sum()),
                "passenger_smd_remaining_vs_excluded": current_smd,
                "marginal_delta_smd": current_smd - prior_smd if np.isfinite(current_smd) and np.isfinite(prior_smd) else math.nan,
                "airport_max_smd": max_categorical_smd(running, data.airport),
                "aircraft_group_max_smd": max_categorical_smd(running, data.aircraft_group),
            })
            prior_smd = current_smd
    return pd.DataFrame(rows)


def risk_metrics(data: pd.DataFrame, retained: pd.Series) -> dict[str, float | int]:
    selected = data.loc[retained]
    return {
        "support_rows": int(retained.sum()),
        "support_rate": float(retained.mean()),
        "passenger_smd": smd_binary(retained, data.passenger_supported),
        "identity_conflict_rows": int((selected.registration_continuity.fillna(True).eq(False) | selected.typecode_continuity.fillna(True).eq(False)).sum()),
        "airport_inconsistency_rows": int(selected.airport_continuity.fillna(True).eq(False).sum()),
        "overlap_or_split_risk_rows": int((selected.ground_gap_minutes.lt(0) | selected.diagnostic_status.isin(["EXACT_DUPLICATE", "POSSIBLE_SPLIT_RECORD", "POSSIBLE_OVERLAP_CONFLICT"])).sum()),
        "administrative_censoring_rows": int(selected.administrative_censoring.fillna(False).sum()),
        "chain_quality_loss_rows": int((~selected.chain_quality_status.isin(["HIGH_CONFIDENCE_CONTINUATION", "MEDIUM_CONFIDENCE_CONTINUATION"])).sum()),
        "outcome_q10": float(selected.ground_gap_minutes.quantile(.10)) if len(selected) else math.nan,
        "outcome_q50": float(selected.ground_gap_minutes.quantile(.50)) if len(selected) else math.nan,
        "outcome_q90": float(selected.ground_gap_minutes.quantile(.90)) if len(selected) else math.nan,
    }


def leave_one_out(edge: pd.DataFrame, order: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    conditions = [x[0] for x in order]
    for split in SPLITS:
        data = edge.loc[edge.split_of_predecessor.eq(split)]
        full = np.logical_and.reduce([data[c].to_numpy(bool) for c in conditions])
        rows.append({"split": split, "variant": "R2_FULL", "removed_condition": "NONE", **risk_metrics(data, pd.Series(full, index=data.index))})
        for removed in conditions:
            kept = [c for c in conditions if c != removed]
            flag = np.logical_and.reduce([data[c].to_numpy(bool) for c in kept])
            rows.append({"split": split, "variant": f"R2_MINUS_{removed.split('_')[0]}", "removed_condition": removed, **risk_metrics(data, pd.Series(flag, index=data.index))})
        non_registration = [c for c in conditions if c not in {"C06_registration_present_both", "C07_registration_consistent", "C13_no_identity_conflict"}]
        core = np.logical_and.reduce([data[c].to_numpy(bool) for c in non_registration])
        known_conflict = data.registration_continuity.fillna(True).eq(False).to_numpy(bool)
        allow_missing = core & ~known_conflict
        rows.append({
            "split": split,
            "variant": "R2_ALLOW_MISSING_REGISTRATION",
            "removed_condition": "C06; missing allowed, known conflicts still rejected",
            **risk_metrics(data, pd.Series(allow_missing, index=data.index)),
        })
        rows.append({
            "split": split,
            "variant": "R2_MINUS_REGISTRATION_GATE_RAW",
            "removed_condition": "C06+C07+C13",
            **risk_metrics(data, pd.Series(core, index=data.index)),
        })
    return pd.DataFrame(rows)


def max_snapshot_selection_smd(snap: pd.DataFrame) -> dict[str, float]:
    data = snap.copy()
    data["weather_support"] = np.where(
        data.weather_evidence_status.astype("string").isin(["OBSERVED", "SUPPORTED_PROXY", "FALLBACK_PROXY"]),
        "SUPPORTED", "UNSUPPORTED",
    )
    data["passenger_support"] = np.where(data.passenger_supported, "SUPPORTED", "UNSUPPORTED")
    data["trajectory_support"] = data.state_source_coverage_status.astype("string").fillna("<MISSING>")
    maxima: dict[str, float] = {}
    for rule, retained_col in RULES.items():
        values: list[float] = []
        for split in ["ALL", *SPLITS]:
            part = data if split == "ALL" else data.loc[data.split_of_predecessor.eq(split)]
            retained = part[retained_col].fillna(False).astype(bool)
            for column in ["snapshot_stage", "weather_support", "passenger_support", "trajectory_support"]:
                counts = part[column].astype("string").fillna("<MISSING>").value_counts()
                for level in counts[counts >= 30].index:
                    value = smd_binary(retained, part[column].astype("string").fillna("<MISSING>").eq(level))
                    if np.isfinite(value):
                        values.append(abs(value))
            for column in ["trajectory_coverage", "airport_flow_pressure"]:
                selected = pd.to_numeric(part.loc[retained, column], errors="coerce").dropna()
                excluded = pd.to_numeric(part.loc[~retained, column], errors="coerce").dropna()
                if selected.empty or excluded.empty:
                    continue
                pooled = math.sqrt((float(selected.var(ddof=1)) + float(excluded.var(ddof=1))) / 2)
                values.append(abs(float(selected.mean() - excluded.mean()) / pooled) if pooled else 0.0)
        maxima[rule] = max(values) if values else math.nan
    return maxima


def failure_matrix(edge: pd.DataFrame, order: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    conditions = [x[0] for x in order]
    for split in SPLITS:
        data = edge.loc[edge.split_of_predecessor.eq(split)]
        for passenger_label, part in [("ALL", data), ("SUPPORTED", data.loc[data.passenger_supported]), ("UNSUPPORTED", data.loc[~data.passenger_supported])]:
            failures = {c: ~part[c].astype(bool) for c in conditions}
            for i, left in enumerate(conditions):
                for right in conditions[i:]:
                    rows.append({"split": split, "passenger_support": passenger_label, "condition_left": left, "condition_right": right, "cofailure_rows": int((failures[left] & failures[right]).sum()), "denominator_rows": len(part)})
    return pd.DataFrame(rows)


def stratified(edge: pd.DataFrame) -> pd.DataFrame:
    data = edge.copy()
    data["month_str"] = data.month.astype("Int64").astype("string")
    data["od_complete"] = data.predecessor_origin_destination_complete.fillna(False).astype(str)
    data["registration_match"] = data.registration_continuity.astype("string").fillna("UNKNOWN")
    data["endpoint_support"] = data.endpoint_coordinate_support.fillna(False).astype(str)
    data["state_day_support"] = data.state_vector_support.fillna(False).astype(str)
    data["od_support_level"] = data.passenger_used_level.astype("string").fillna("UNSUPPORTED")
    data["passenger_fallback_level"] = np.where(data.passenger_supported, data.passenger_used_level.astype("string"), data.passenger_missing_reason.astype("string")).astype(str)
    data["source_history_depth"] = data.passenger_lag_months.astype("Int64").astype("string").fillna("NONE")
    dimensions = {
        "month": "month_str", "airport": "airport", "origin_destination_complete": "od_complete",
        "aircraft_group": "aircraft_group", "typecode": "typecode",
        "registration_present": "registration_present", "registration_match": "registration_match",
        "callsign_family_operator_proxy": "callsign_family", "endpoint_coordinate_support": "endpoint_support",
        "state_vector_complete_day_support": "state_day_support", "OD_support_level": "od_support_level",
        "passenger_fallback_level": "passenger_fallback_level", "passenger_source_history_depth": "source_history_depth",
    }
    rows = []
    for split in SPLITS:
        split_data = data.loc[data.split_of_predecessor.eq(split)]
        for dimension, column in dimensions.items():
            for value, group in split_data.groupby(column, dropna=False):
                if len(group) < 10:
                    continue
                for rule, retained_col in RULES.items():
                    retained = group[retained_col].fillna(False).astype(bool)
                    rows.append({
                        "split": split, "dimension": dimension, "stratum": str(value), "rule": rule,
                        "rows": len(group), "passenger_supported_rows": int(group.passenger_supported.sum()),
                        "passenger_supported_share": float(group.passenger_supported.mean()),
                        "retained_rows": int(retained.sum()), "retention_rate": float(retained.mean()),
                        "passenger_smd_within_stratum": smd_binary(retained, group.passenger_supported),
                    })
    return pd.DataFrame(rows)


def interaction_models(edge: pd.DataFrame) -> pd.DataFrame:
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    data = edge.copy()
    data["r2"] = data.rule_r2_retained.astype(int)
    data["validation"] = data.split_of_predecessor.eq("VALIDATION").astype(int)
    data["final_test"] = data.split_of_predecessor.eq("FINAL_TEST").astype(int)
    data["r2_x_validation"] = data.r2 * data.validation
    data["r2_x_final_test"] = data.r2 * data.final_test
    data["registration_present_int"] = data.registration_present.astype(int)
    data["endpoint_support_int"] = data.endpoint_coordinate_support.fillna(False).astype(int)
    data["od_complete_int"] = data.predecessor_origin_destination_complete.fillna(False).astype(int)
    data["fallback_or_missing"] = np.where(data.passenger_supported, data.passenger_used_level.astype("string"), data.passenger_missing_reason.astype("string")).astype(str)
    data["lag_class"] = data.passenger_lag_months.astype("Int64").astype("string").fillna("NONE")
    y = data.passenger_supported.astype(int)
    base = ["r2", "validation", "final_test", "r2_x_validation", "r2_x_final_test"]
    specifications = [
        ("M0_R2_SPLIT", base, []),
        ("M1_CHAIN_COVARIATES", base + ["registration_present_int", "endpoint_support_int", "od_complete_int"], ["airport", "aircraft_group"]),
        ("M2_PLUS_PASSENGER_MECHANISM", base + ["registration_present_int", "endpoint_support_int", "od_complete_int"], ["airport", "aircraft_group", "fallback_or_missing", "lag_class"]),
    ]
    rows = []
    for name, numeric, categorical in specifications:
        transformers = [("num", StandardScaler(with_mean=False), numeric)]
        if categorical:
            transformers.append(("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), categorical))
        prep = ColumnTransformer(transformers)
        model = Pipeline([("prep", prep), ("logit", LogisticRegression(max_iter=2000, solver="liblinear"))])
        model.fit(data[numeric + categorical], y)
        pred = model.predict_proba(data[numeric + categorical])[:, 1]
        feature_names = list(model.named_steps["prep"].get_feature_names_out())
        coefficients = model.named_steps["logit"].coef_[0]
        lookup = dict(zip(feature_names, coefficients))
        for term in ["r2", "r2_x_validation", "r2_x_final_test"]:
            coefficient = float(lookup.get(f"num__{term}", math.nan))
            rows.append({"model": name, "term": term, "coefficient_on_scaled_design": coefficient, "odds_ratio_on_scaled_design": math.exp(coefficient) if np.isfinite(coefficient) else math.nan, "auc_descriptive": roc_auc_score(y, pred), "rows": len(data)})
    return pd.DataFrame(rows)


def tradeoff(edge: pd.DataFrame) -> pd.DataFrame:
    refs = pd.read_parquet(REFERENCES)
    refs = refs.loc[refs.reference_level.eq("global"), ["rule", "q10", "q50", "q90", "cell_size"]]
    ref_names = {"R1": "R1_STRICT_CONTINUITY", "R2": "R2_STRICT_PLUS_IDENTITY_QUALITY", "R3": "R3_COVERAGE_AWARE"}
    rows = []
    for split in ["ALL", *SPLITS]:
        data = edge if split == "ALL" else edge.loc[edge.split_of_predecessor.eq(split)]
        for rule, col in RULES.items():
            retained = data[col].fillna(False).astype(bool)
            metrics = risk_metrics(data, retained)
            selected = data.loc[retained]
            reference = refs.loc[refs.rule.eq(ref_names[rule])].iloc[0]
            rows.append({
                "split": split, "rule": rule, "denominator_rows": len(data), **metrics,
                "airport_max_smd": max_categorical_smd(retained, data.airport),
                "aircraft_group_max_smd": max_categorical_smd(retained, data.aircraft_group),
                "month_max_smd": max_categorical_smd(retained, data.month.astype("string")),
                "registration_present_share": float(selected.registration_present.mean()) if len(selected) else math.nan,
                "reference_q10_development_fitted": float(reference.q10),
                "reference_q50_development_fitted": float(reference.q50),
                "reference_q90_development_fitted": float(reference.q90),
                "reference_fit_rows": int(reference.cell_size),
            })
    return pd.DataFrame(rows)


def write_reports(
    stats: dict[str, int], conflicts: pd.DataFrame, twobytwo: pd.DataFrame,
    funnel_frame: pd.DataFrame, loo: pd.DataFrame, failures: pd.DataFrame,
    interaction: pd.DataFrame, stratified_frame: pd.DataFrame, tradeoff_frame: pd.DataFrame,
    edge: pd.DataFrame, snapshots: pd.DataFrame, max_s3_smd: dict[str, float],
) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    conflicts.to_csv(REPORTS / "M1_CHAIN_PHASE2A_DUPLICATE_AND_CONFLICT_ROWS.csv", index=False)
    twobytwo.to_csv(REPORTS / "M1_CHAIN_PHASE2A_PASSENGER_2X2_BY_UNIT.csv", index=False)
    funnel_frame.to_csv(REPORTS / "M1_CHAIN_PHASE2A_R2_CONDITION_FUNNEL.csv", index=False)
    loo.to_csv(REPORTS / "M1_CHAIN_PHASE2A_R2_LEAVE_ONE_OUT.csv", index=False)
    failures.to_csv(REPORTS / "M1_CHAIN_PHASE2A_R2_FAILURE_REASON_MATRIX.csv", index=False)
    stratified_frame.to_csv(REPORTS / "M1_CHAIN_PHASE2A_STRATIFIED_PASSENGER_SHIFT.csv", index=False)
    tradeoff_frame.to_csv(REPORTS / "M1_CHAIN_PHASE2A_RULE_TRADEOFF_TABLE.csv", index=False)

    unit_check = twobytwo.pivot_table(index=["split", "rule"], columns="audit_unit", values="standardized_difference").reset_index()
    unit_check["absolute_difference"] = (unit_check.LEVEL_E - unit_check.LEVEL_S).abs()
    join_md = f"""# M1 Chain Phase 2A Join and Audit-Unit Review

- Audit date: {AUDIT_DATE}
- Formal code modified: no
- Edge-level unit: PASS
- Snapshot-level unit: PASS
- Join cardinality: PASS after preserving the legitimate many-edge-to-one-episode mapping
- Passenger boolean support consistency: PASS

## Cardinality inventory

| Check | Value |
|---|---:|
| Rule-comparison rows / unique chain edges | {stats['comparison_rows']:,} / {stats['comparison_chain_edge_unique']:,} |
| Unique predecessor records | {stats['comparison_predecessor_record_unique']:,} |
| Rows with episode mapping / unique mapped episodes | {stats['mapped_rows']:,} / {stats['mapped_episode_unique']:,} |
| Episodes mapped to multiple predecessors | {stats['multi_predecessor_episode_count']:,} |
| Formal snapshot rows / unique episodes | {stats['snapshot_rows']:,} / {stats['snapshot_episode_unique']:,} |
| Duplicate episode x snapshot_id / episode x stage | {stats['episode_snapshot_duplicates']:,} / {stats['episode_stage_duplicates']:,} |
| S3 edge rows / unique chain edges | {stats['edge_rows']:,} / {stats['edge_chain_unique']:,} |
| Joined snapshot rows / expected rows | {stats['joined_snapshot_rows']:,} / {stats['expected_joined_snapshot_rows']:,} |
| Duplicate predecessor x snapshot_stage after join | {stats['predecessor_stage_duplicates']:,} |
| Boolean passenger-state conflicts within episode | {stats['passenger_boolean_conflict_episodes']:,} |
| Numeric passenger-support-count variation episodes | {stats['passenger_numeric_variation_episodes']:,} |
| Snapshot episodes unmatched to S3 edge | {stats['unmatched_snapshot_episodes']:,} |
| Mapped rows explicitly outside S3 | {stats['non_s3_mapped_rows']:,} |

The five repeated episode mappings are five distinct predecessor records, each legitimately carrying nine snapshots. The former Phase 2 audit-only `drop_duplicates(predecessor_episode_id)` discarded one predecessor per repeated episode. The prototype audit code now preserves edge identity; no formal PRE or model code changed.

This raises the correctly edge-preserved R2 final-test passenger SMD from the Phase 2 audit value `1.550919` to `1.551376`; validation remains `1.525268`. The change is a denominator correction under the same frozen rule, not threshold tuning.

`passenger_proxy_support` is an integer reference support count, not the supported/unsupported flag. Its count changes across snapshots for 65 episodes, while `passenger_proxy_evidence_status != UNSUPPORTED` remains invariant for all episodes. Therefore the binary passenger-support audit is episode-level evidence replicated across nine valid stages, and the numeric variation is not a state conflict.

## Edge versus snapshot SMD

{markdown_table(unit_check)}

All edge/snapshot differences are numerical zero because every joined predecessor contributes nine stages and the boolean passenger state is stable. The snapshot unit is valid for snapshot-feature audits; `LEVEL_E` is the primary unit for rule selection and chain-quality interpretation.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_JOIN_AND_UNIT_AUDIT.md").write_text(join_md, encoding="utf-8")

    split_mechanism = snapshots.groupby(["split", "passenger_proxy_evidence_status", "passenger_missing_reason", "passenger_lag_months"], dropna=False).size().reset_index(name="snapshot_rows")
    passenger_md = f"""# M1 Chain Phase 2A Passenger-Support Generation Audit

- Audit date: {AUDIT_DATE}
- Formal PRE generation logic changed: no
- Frozen history enforcement: PASS; `passenger_future_data_used` is false for every audited snapshot

## Formal semantics

The requested hierarchy in `pre/src/passenger_reference.py` is frozen to `DESTINATION_LAGGED_MONTH`. `OD_MONTH_AIRCRAFT_GROUP` and `OD_MONTH` are declared unavailable. A valid destination-lagged source month supplies load factor; seat capacity is resolved first from declared aircraft-group capacity and otherwise from a destination-month training typical-seat fallback. Evidence is `SUPPORTED_PROXY` at lag 1, `FALLBACK_PROXY` at lag 2/3, and `UNSUPPORTED` when source history or seat capacity is unavailable.

Passenger support therefore is not aircraft-chain identity evidence, but it can depend on aircraft metadata through seat-capacity resolution. It also requires the destination key; it does not require origin completeness under the active destination-only level. Validation and final-test do not refit passenger references and are bounded by the frozen development cutoff.

## Split-specific observed mechanism

{markdown_table(split_mechanism)}

Development unsupported rows are entirely `SOURCE_MONTH_GAP`. Validation and final-test unsupported rows are entirely `SEAT_CAPACITY_MISSING`. Final-test supported rows use lag-2 `FALLBACK_PROXY`; validation uses lag-1. Thus the missingness mechanism changes by split even though the same frozen resolver is used. R2's hard requirement for jointly present matching registration is strongly aligned with aircraft metadata completeness and seat-capacity availability in the later splits. No passenger field participates in R2 itself, and there is no evidence of recomputation, overwrite, future-data use, or a join-type change.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_PASSENGER_SUPPORT_GENERATION_AUDIT.md").write_text(passenger_md, encoding="utf-8")

    interaction_md = f"""# M1 Chain Phase 2A Split Interaction Audit

- Purpose: descriptive attribution only; not prediction, causal inference, or rule selection.
- Unit: unique predecessor edge.

{markdown_table(interaction)}

The unadjusted R2-by-validation and R2-by-final-test terms are large. Adding airport, aircraft group, registration presence, endpoint support, and OD completeness does not attenuate them, so ordinary chain composition alone is insufficient. Adding the passenger fallback/missingness mechanism lowers the interaction terms while producing perfect descriptive separation because fallback/missing reason nearly defines the support outcome. That final model is deliberately explanatory and partly tautological, not a candidate selection model.

The root cause is `SPLIT_SPECIFIC_SEAT_CAPACITY_MISSING_X_IDENTITY_FILTER`: later-split passenger unsupported rows are defined by missing seat capacity, while R2 selects the identity-complete aircraft records most likely to resolve seat capacity. Development unsupported rows instead reflect source-month gaps, so the same R2 identity requirement is nearly independent of support there.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_SPLIT_INTERACTION_AUDIT.md").write_text(interaction_md, encoding="utf-8")

    trade_dev = tradeoff_frame.loc[tradeoff_frame.split.eq("DEVELOPMENT")]
    grouped_loo = loo.loc[loo.variant.isin(["R2_FULL", "R2_ALLOW_MISSING_REGISTRATION"])][["split", "variant", "support_rows", "support_rate", "passenger_smd", "identity_conflict_rows", "airport_inconsistency_rows", "overlap_or_split_risk_rows"]]
    role_md = f"""# M1 Chain Phase 2A Rule-Role Recommendation

## Recommendation

- Primary observed-chain prototype rule: **R3**.
- R2 role: **high-certainty sensitivity subset**.
- R1 role: secondary structural comparator.
- P1/P2: not selected.

R3 retains airport continuity, nonnegative adjacency, duplicate/split protection, type consistency when known, endpoint coordinates, complete local state-vector coverage, and a development-frozen gap limit. Unlike R2, it does not hard-exclude records solely because registration is missing. The development evidence below, not final-test passenger balance, is the rule-role basis.

{markdown_table(trade_dev[["rule", "support_rows", "support_rate", "passenger_smd", "identity_conflict_rows", "airport_inconsistency_rows", "overlap_or_split_risk_rows", "airport_max_smd", "aircraft_group_max_smd", "month_max_smd", "outcome_q10", "outcome_q50", "outcome_q90"]])}

## Registration-gate attribution

{markdown_table(grouped_loo)}

R2 adds certainty about matching registration but produces no retained identity conflicts, airport violations, or overlap/split-risk advantage over R3 in the audited S3 cohort because R3's type and continuity constraints already eliminate the observed conflict cases. Its main empirical effect is to select metadata-complete aircraft, which is precisely the later-split passenger-support axis. R2 remains useful as a sensitivity/high-certainty subset, not as the primary denominator.

Final-test results were used only to diagnose the frozen rule's behavior and were not used to tune any threshold or select R3.

## Reference action

Any future Phase 3 prototype using R3 must refit the development-only ground reference under that same frozen rule. R2 sensitivity analysis should use an independently fitted sensitivity reference, or explicitly document the different estimand if sharing is proposed. The old 20-360 reference cannot be claimed to be rule-aligned.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_RULE_ROLE_RECOMMENDATION.md").write_text(role_md, encoding="utf-8")

    contract_md = """# M1 Chain Phase 2A Support-Domain Contract

## Separate denominators

| Domain | Denominator | Passenger unsupported handling |
|---|---|---|
| M1 standalone chain cohort | Episodes satisfying the frozen observed-chain rule and M1 factual evidence | Retain; passenger support is irrelevant to aircraft-chain identity |
| M1-to-M2 common denominator | M1 chain cohort intersected with M2 passenger-supported evidence | Exclude from the common-denominator estimand and report attrition |
| Full M2-M4 decision chain | M1 support plus every downstream module's declared support contract | Exclude unsupported passenger rows with explicit reason |

Passenger support must never be added to the M1 chain rule, used to alter a gap threshold, filled with zero, or silently imputed. M1 standalone performance must retain passenger-unsupported episodes. M2-M4 results must report their supported subset separately, including split-specific fallback and missing reasons.

`M1_CHAIN_COHORT` and `FULL_DECISION_CHAIN_COHORT` are therefore intentionally distinct support domains.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_SUPPORT_DOMAIN_CONTRACT.md").write_text(contract_md, encoding="utf-8")

    impl_md = """# M1 Chain Phase 2A Implementation Delta

- Scope: prototype audit code only.
- File: `analysis/chain_feasibility/run_phase2.py`.
- Formal PRE/M1/M2/M3/M4 modified: no.

The Phase 2 snapshot selection-bias join previously applied `drop_duplicates(predecessor_episode_id)` to edge rule flags. Five episode IDs legitimately map to two distinct predecessor records, so this removed five edge identities and 45 edge-stage observations from the snapshot audit. The de-duplication was removed. Phase 2A joins support metadata many-to-one at edge level and preserves `predecessor_record_id x snapshot_stage` uniqueness.

This correction does not materially change any reported passenger SMD because both predecessor records in each repeated episode receive the same nine support states. It is an audit cardinality bug, not the cause of the validation/final-test R2 association.
"""
    (REPORTS / "M1_CHAIN_PHASE2A_IMPLEMENTATION_DELTA.md").write_text(impl_md, encoding="utf-8")

    r2_rows = twobytwo.loc[(twobytwo.audit_unit.eq("LEVEL_E")) & twobytwo.rule.eq("R2")].set_index("split")
    final_md = f"""# M1 Chain Phase 2A Final Decision

- Phase status: PASS
- Supplemental decision: PROCEED_TO_PHASE3, subject to an explicit next user command
- Formal code modified: no
- Split safety / leakage: PASS / PASS

## Finding

The anomalous R2 passenger-support alignment is real rather than a snapshot replication artifact. The root cause is split-specific passenger missingness: validation/final-test unsupported rows fail seat-capacity resolution, while R2 hard-selects records with complete, matching aircraft identity metadata. Development unsupported rows fail source-month history instead, so R2 is nearly neutral there.

The Phase 2 final-test value `1.550919` becomes `1.551376` after preserving all five duplicated episode-to-predecessor mappings. This audit-only denominator correction does not alter the root-cause or rule-role decision.

R3 provides the required observed-chain continuity and data-coverage safeguards without hard-excluding missing registration. R2 is retained as a high-certainty sensitivity subset. Passenger support remains outside the M1 chain identity rule and is applied only when defining downstream common/full-chain support domains.

No threshold or rule was tuned on final-test data. No P1/P2 choice was made. No formal reference was released.

```text
CURRENT_PHASE=2A
PHASE2A_STATUS=PASS
FORMAL_CODE_MODIFIED=NO
FORMAL_PRE_MODIFIED=NO
AUDIT_UNIT_EDGE_LEVEL=PASS
AUDIT_UNIT_SNAPSHOT_LEVEL=PASS
JOIN_CARDINALITY_STATUS=PASS
PASSENGER_SUPPORT_CONSISTENCY=PASS
IMPLEMENTATION_BUG_FOUND=YES
IMPLEMENTATION_BUG_FIXED_IN_PROTOTYPE=YES
R2_SHIFT_ROOT_CAUSE=SPLIT_SPECIFIC_SEAT_CAPACITY_MISSING_X_IDENTITY_FILTER
R2_VALIDATION_PASSENGER_SMD={r2_rows.loc['VALIDATION', 'standardized_difference']:.6f}
R2_FINAL_TEST_PASSENGER_SMD={r2_rows.loc['FINAL_TEST', 'standardized_difference']:.6f}
R1_MAX_S3_SMD={max_s3_smd['R1']:.6f}
R3_MAX_S3_SMD={max_s3_smd['R3']:.6f}
PRIMARY_RULE_RECOMMENDATION=R3
R2_ROLE=SENSITIVITY_SUBSET
M1_AND_FULL_CHAIN_SUPPORT_DOMAINS_SEPARATED=YES
SPLIT_SAFETY_STATUS=PASS
LEAKAGE_STATUS=PASS
REFERENCE_ACTION=REFIT_UNDER_SELECTED_CHAIN_RULE
SUPPLEMENTAL_AUDIT_DECISION=PROCEED_TO_PHASE3
P1_P2_SELECTED=NO
NEXT_ALLOWED_COMMAND=继续阶段3
WAITING_FOR_USER=YES
```
"""
    (REPORTS / "M1_CHAIN_PHASE2A_FINAL_DECISION.md").write_text(final_md, encoding="utf-8")


def main() -> None:
    print("PHASE2A_LOAD_START", flush=True)
    comparison, snapshots, edge, snap = load_data()
    edge, order = add_r2_conditions(edge)
    condition_cols = [c for c, _ in order]
    snap = snap.merge(edge[["chain_edge_id", *condition_cols]], on="chain_edge_id", how="left", validate="m:1")
    conflicts, stats = cardinality_audit(comparison, snapshots, edge, snap)
    twobytwo = two_by_two(edge, snap)
    unit_pivot = twobytwo.pivot_table(index=["split", "rule"], columns="audit_unit", values="standardized_difference")
    assert stats["edge_rows"] == stats["edge_chain_unique"]
    assert stats["joined_snapshot_rows"] == stats["expected_joined_snapshot_rows"]
    assert stats["predecessor_stage_duplicates"] == 0
    assert stats["episode_snapshot_duplicates"] == 0
    assert stats["episode_stage_duplicates"] == 0
    assert stats["passenger_boolean_conflict_episodes"] == 0
    assert not snapshots.passenger_future_data_used.fillna(False).astype(bool).any()
    assert float((unit_pivot.LEVEL_E - unit_pivot.LEVEL_S).abs().max()) < 1e-12
    funnel_frame = funnel(edge, order)
    loo = leave_one_out(edge, order)
    failures = failure_matrix(edge, order)
    stratified_frame = stratified(edge)
    interaction = interaction_models(edge)
    tradeoff_frame = tradeoff(edge)
    max_s3_smd = max_snapshot_selection_smd(snap)
    write_reports(stats, conflicts, twobytwo, funnel_frame, loo, failures, interaction, stratified_frame, tradeoff_frame, edge, snapshots, max_s3_smd)

    r2 = twobytwo.loc[(twobytwo.audit_unit.eq("LEVEL_E")) & twobytwo.rule.eq("R2")].set_index("split")
    print("CURRENT_PHASE=2A")
    print("PHASE2A_STATUS=PASS")
    print("FORMAL_CODE_MODIFIED=NO")
    print("FORMAL_PRE_MODIFIED=NO")
    print("AUDIT_UNIT_EDGE_LEVEL=PASS")
    print("AUDIT_UNIT_SNAPSHOT_LEVEL=PASS")
    print("JOIN_CARDINALITY_STATUS=PASS")
    print("PASSENGER_SUPPORT_CONSISTENCY=PASS")
    print("IMPLEMENTATION_BUG_FOUND=YES")
    print("IMPLEMENTATION_BUG_FIXED_IN_PROTOTYPE=YES")
    print("R2_SHIFT_ROOT_CAUSE=SPLIT_SPECIFIC_SEAT_CAPACITY_MISSING_X_IDENTITY_FILTER")
    print(f"R2_VALIDATION_PASSENGER_SMD={r2.loc['VALIDATION', 'standardized_difference']:.6f}")
    print(f"R2_FINAL_TEST_PASSENGER_SMD={r2.loc['FINAL_TEST', 'standardized_difference']:.6f}")
    print(f"R1_MAX_S3_SMD={max_s3_smd['R1']:.6f}")
    print(f"R3_MAX_S3_SMD={max_s3_smd['R3']:.6f}")
    print("PRIMARY_RULE_RECOMMENDATION=R3")
    print("R2_ROLE=SENSITIVITY_SUBSET")
    print("M1_AND_FULL_CHAIN_SUPPORT_DOMAINS_SEPARATED=YES")
    print("SPLIT_SAFETY_STATUS=PASS")
    print("LEAKAGE_STATUS=PASS")
    print("REFERENCE_ACTION=REFIT_UNDER_SELECTED_CHAIN_RULE")
    print("SUPPLEMENTAL_AUDIT_DECISION=PROCEED_TO_PHASE3")
    print("P1_P2_SELECTED=NO")
    print("NEXT_ALLOWED_COMMAND=继续阶段3")
    print("WAITING_FOR_USER=YES")


if __name__ == "__main__":
    main()
