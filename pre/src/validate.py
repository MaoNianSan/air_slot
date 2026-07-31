from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .target_contract import (
    FORMAL_TARGET_COLUMN,
    SENSITIVITY_TARGET_COLUMN,
    target_contract_metadata,
)


@dataclass
class PreBundle:
    episodes: pd.DataFrame
    snapshots: pd.DataFrame
    calibration: pd.DataFrame
    rules: pd.DataFrame
    evidence_audit: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        return {
            "episodes": self.episodes,
            "snapshots": self.snapshots,
            "calibration": self.calibration,
            "rules": self.rules,
            "evidence_audit": self.evidence_audit,
        }


def load_bundle(output_root: str | Path) -> PreBundle:
    root = Path(output_root)
    names = ["episodes", "snapshots", "calibration", "rules", "evidence_audit"]
    missing = [name for name in names if not (root / f"{name}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"missing formal tables: {missing}")
    return PreBundle(**{name: pd.read_parquet(root / f"{name}.parquet") for name in names})


def _require_columns(frame: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing columns: {missing}")


def _validate_schema(bundle: PreBundle, cfg: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    table_specs = cfg["schema"]["tables"]
    for name, frame in bundle.tables().items():
        spec = table_specs[name]
        _require_columns(frame, list(spec["required"]), name)
        key = list(spec.get("key", []))
        duplicate_count = int(frame.duplicated(key).sum()) if key else 0
        if duplicate_count:
            raise ValueError(f"duplicate {name} primary key: {duplicate_count}")
        result[name] = {"rows": len(frame), "duplicate_keys": duplicate_count}
    return result


def _validate_splits(bundle: PreBundle) -> None:
    episodes = bundle.episodes
    snapshots = bundle.snapshots
    if not (episodes["episode_id"].astype(str) == episodes["flight_id"].astype(str)).all():
        raise ValueError("episode_id != flight_id")
    if episodes.groupby("flight_id")["split"].nunique().max() > 1:
        raise ValueError("same flight appears in multiple splits")
    joined = snapshots[["episode_id", "split"]].merge(
        episodes[["episode_id", "split"]], on="episode_id", how="left", suffixes=("_snapshot", "_episode"), validate="many_to_one"
    )
    if (joined["split_snapshot"] != joined["split_episode"]).any():
        raise ValueError("snapshot split mismatch")


def _validate_snapshots(bundle: PreBundle, cfg: dict[str, Any]) -> None:
    snapshots = bundle.snapshots
    if snapshots[["flight_id", "aircraft_id", "anchor_date", "trigger_event_group_id"]].isna().any().any():
        raise ValueError("snapshot canonical episode identifiers contain nulls")
    episode_identity = bundle.episodes.set_index("episode_id")["flight_id"]
    if not snapshots["flight_id"].eq(snapshots["episode_id"].map(episode_identity)).all():
        raise ValueError("snapshot flight_id differs from episode authority table")
    tolerance = float(cfg["snapshots"]["ratio_tolerance"])
    if ((snapshots["snapshot_ratio"] - snapshots["elapsed_ratio"]).abs() > tolerance).any():
        raise ValueError("elapsed_ratio differs from snapshot_ratio")
    stage_map = {float(key): value for key, value in cfg["snapshots"]["dense_stage_map"].items()}
    for row in snapshots.itertuples(index=False):
        ratio = round(float(row.snapshot_ratio), 1)
        if stage_map.get(ratio) != row.snapshot_stage:
            raise ValueError(f"stage-ratio mismatch: {row.snapshot_id}")
    source_gap_filled = (
        snapshots["state_source_coverage_status"].eq("SOURCE_COVERAGE_GAP")
        & snapshots["state_is_imputed"].fillna(False)
    )
    if source_gap_filled.any():
        raise ValueError("source coverage gap was filled")
    primary = snapshots[snapshots["is_primary_snapshot"]]
    # Retention measures the extraction/quality pipeline only where a state
    # record is causally expected.  A flight that has already completed and a
    # declared source-coverage gap are structural exclusions, not failed
    # state retrievals; both remain visible in the published audit tables.
    eligible_primary = primary[
        ~primary["snapshot_exclusion_reason"].isin(
            ["FLIGHT_COMPLETED_BEFORE_SNAPSHOT", "SOURCE_COVERAGE_GAP"]
        )
    ]
    if not eligible_primary.empty:
        quality = (
            eligible_primary["snapshot_valid"].fillna(False)
            & (eligible_primary["state_record_count"] >= int(cfg["state_vectors"]["minimum_records"]))
            & (eligible_primary["state_observation_age"] <= float(cfg["state_vectors"]["maximum_observation_age_minutes"]))
            & (eligible_primary["trajectory_coverage"] >= float(cfg["state_vectors"]["minimum_trajectory_coverage"]))
        )
        retention = float(quality.mean())
    else:
        retention = 0.0
    if retention < float(cfg["validation"]["minimum_state_retention"]):
        raise ValueError(
            f"state validation retention {retention:.3f} below {cfg['validation']['minimum_state_retention']}"
        )


def _validate_availability(bundle: PreBundle) -> None:
    audit = bundle.evidence_audit
    factual = audit["evidence_status"].isin(["OBSERVED", "DERIVED"])
    violations = factual & ~audit["available_by_t"].fillna(False).astype(bool)
    if violations.any():
        raise ValueError(f"factual availability violations: {int(violations.sum())}")
    forbidden = {
        "lastseen_utc", "observed_movement_time", "y_movement_raw", "y_movement_model",
        "future_successor", "future_metar", "future_state_vector",
    }
    leaked = audit["feature_name"].isin(forbidden)
    if leaked.any():
        raise ValueError(f"outcome/future fields in audit: {sorted(audit.loc[leaked, 'feature_name'].unique())}")
    imputed_observed = bundle.snapshots["weather_imputed"].fillna(False) & bundle.snapshots["weather_evidence_status"].eq("OBSERVED")
    if imputed_observed.any():
        raise ValueError("imputed weather marked OBSERVED")


def _validate_rules(bundle: PreBundle, cfg: dict[str, Any]) -> None:
    rules = bundle.rules
    snapshots = bundle.snapshots
    expected = set(cfg["actions"]["action_ids"])
    if not rules.empty and not rules["rule_evidence_status"].eq("RULE_GENERATED").all():
        raise ValueError("rule evidence status must be RULE_GENERATED")
    counts = rules.groupby(["episode_id", "snapshot_id"], observed=True)["action_id"].agg(["size", lambda values: set(values)]) if not rules.empty else pd.DataFrame()
    for key in map(tuple, snapshots.loc[snapshots["snapshot_valid"], ["episode_id", "snapshot_id"]].to_numpy()):
        if key not in counts.index:
            raise ValueError(f"valid snapshot has no rules: {key}")
        if int(counts.loc[key, "size"]) != len(expected) or counts.loc[key, "<lambda_0>"] != expected:
            raise ValueError(f"valid snapshot lacks exact action library: {key}")
    if not rules.empty:
        checks = {
            "airport_resource_available": "resource_available_r",
            "aircraft_sequence_available": "resource_available_f",
            "passenger_handling_available": "resource_available_p",
        }
        for canonical, deprecated in checks.items():
            mismatch = ~pd.to_numeric(rules[canonical], errors="coerce").eq(pd.to_numeric(rules[deprecated], errors="coerce"))
            if mismatch.fillna(False).any():
                raise ValueError(f"deprecated alias mapping mismatch: {deprecated}->{canonical}")
        if not rules["deprecated_alias_mapping_version"].eq("legacy-fpr-to-afp-v1").all():
            raise ValueError("deprecated alias mapping version missing")


def _validate_target_contract(bundle: PreBundle, cfg: dict[str, Any]) -> dict[str, Any]:
    metadata = target_contract_metadata(cfg)
    episodes = bundle.episodes
    required = [FORMAL_TARGET_COLUMN, SENSITIVITY_TARGET_COLUMN, "m1_outcome_label"]
    missing = [column for column in required if column not in episodes]
    if missing:
        raise ValueError(f"FORMAL_TARGET_CONTRACT_BLOCKED: missing episode columns {missing}")

    raw = pd.to_numeric(episodes[FORMAL_TARGET_COLUMN], errors="coerce")
    model = pd.to_numeric(episodes[SENSITIVITY_TARGET_COLUMN], errors="coerce")
    formal_alias = pd.to_numeric(episodes["m1_outcome_label"], errors="coerce")
    valid = episodes["episode_valid"].fillna(False).astype(bool)
    expected_raw = (
        pd.to_numeric(episodes["observed_movement_time"], errors="coerce")
        - pd.to_numeric(episodes["reference_movement_time"], errors="coerce")
    )

    raw_identity = raw.eq(expected_raw) | (raw.isna() & expected_raw.isna())
    if not raw_identity[valid].all():
        raise ValueError(f"FORMAL_TARGET_CONTRACT_BLOCKED: raw target transformed or exchanged on {int((~raw_identity & valid).sum())} rows")
    alias_identity = formal_alias.eq(raw) | (formal_alias.isna() & raw.isna())
    if not alias_identity.all():
        raise ValueError(f"FORMAL_TARGET_CONTRACT_BLOCKED: m1_outcome_label differs from raw on {int((~alias_identity).sum())} rows")

    transform = cfg["labels"]["sensitivity_transform"]
    train = episodes["split"].eq(transform["fit_split"]) & valid
    training_raw = raw[train].dropna()
    if training_raw.empty:
        raise ValueError("FORMAL_TARGET_CONTRACT_BLOCKED: no training raw labels for sensitivity trace")
    low_q, high_q = [float(value) for value in transform["clip_quantiles"]]
    low, high = float(training_raw.quantile(low_q)), float(training_raw.quantile(high_q))
    expected_model = raw.clip(low, high)
    model_identity = model.eq(expected_model) | (model.isna() & expected_model.isna())
    if not model_identity.all():
        raise ValueError(f"FORMAL_TARGET_CONTRACT_BLOCKED: sensitivity derivation mismatch on {int((~model_identity).sum())} rows")
    if not raw.isna().eq(model.isna()).all():
        raise ValueError("FORMAL_TARGET_CONTRACT_BLOCKED: sensitivity transform changed cohort missingness")

    comparable = raw.notna() & model.notna()
    absolute_difference = (raw[comparable] - model[comparable]).abs()
    return {
        **metadata,
        "status": "PASS",
        "rows_total": int(len(episodes)),
        "raw_non_null": int(raw.notna().sum()),
        "model_non_null": int(model.notna().sum()),
        "raw_model_difference_rows": int(absolute_difference.gt(0).sum()),
        "raw_model_max_abs_difference": float(absolute_difference.max()) if not absolute_difference.empty else 0.0,
        "raw_model_mean_abs_difference": float(absolute_difference.mean()) if not absolute_difference.empty else 0.0,
        "label_identity_mismatch_count": int((~alias_identity).sum()),
        "sensitivity_transformation": transform["method"],
        "sensitivity_fit_split": transform["fit_split"],
        "sensitivity_clip_quantiles": [low_q, high_q],
        "sensitivity_clip_bounds": [low, high],
    }


def validate_bundle(bundle: PreBundle, cfg: dict[str, Any]) -> dict[str, Any]:
    schema = _validate_schema(bundle, cfg)
    target_contract = _validate_target_contract(bundle, cfg)
    _validate_splits(bundle)
    _validate_snapshots(bundle, cfg)
    _validate_availability(bundle)
    _validate_rules(bundle, cfg)
    snapshots = bundle.snapshots
    anchor_days = int(bundle.episodes.loc[bundle.episodes["formal_eligible"].fillna(False), "anchor_date"].nunique())
    if cfg.get("mode") == "fast" and anchor_days < 4:
        raise ValueError(f"fast requires at least 4 complete formal-eligible anchor days; found {anchor_days}")
    return {
        "status": "PASS",
        "tables": schema,
        "valid_episodes": int(bundle.episodes["episode_valid"].sum()),
        "valid_snapshots": int(snapshots["snapshot_valid"].sum()),
        "primary_snapshots": int(snapshots["is_primary_snapshot"].sum()),
        "balanced_flights": int(snapshots.groupby("episode_id")["balanced_primary_cohort"].first().sum()),
        "availability_violations": 0,
        "leakage_violations": 0,
        "source_gap_filled": 0,
        "anchor_days": anchor_days,
        "split_overlap": 0,
        "deprecated_alias_mismatches": 0,
        "mode_isolation": "PASS",
        "formal_target_contract": target_contract,
    }


def readiness(bundle: PreBundle, cfg: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    tables = bundle.tables()
    matrix_rows = []
    cohort_rows = []
    for consumer, spec in cfg["schema"].get("consumers", {}).items():
        for table_name in spec["tables"]:
            frame = tables[table_name]
            required = cfg["schema"]["tables"][table_name]["required"]
            missing = [column for column in required if column not in frame.columns]
            matrix_rows.append({
                "consumer": consumer,
                "table": table_name,
                "present": True,
                "required_column_count": len(required),
                "missing_required_columns": ",".join(missing),
                "ready": not missing and not frame.empty,
            })
        snapshots = bundle.snapshots
        balanced = snapshots.groupby("episode_id", observed=True)["balanced_primary_cohort"].first()
        for split in ["train", "validation", "test"]:
            split_ids = set(bundle.episodes.loc[bundle.episodes["split"] == split, "episode_id"])
            count = int(balanced.reindex(list(split_ids)).fillna(False).sum())
            cohort_rows.append({
                "consumer": consumer,
                "split": split,
                "balanced_episode_count": count,
                "ready": count > 0,
            })
    matrix = pd.DataFrame(matrix_rows)
    cohort = pd.DataFrame(cohort_rows)
    summary = {
        "status": "PASS" if (not matrix.empty and matrix["ready"].all() and not cohort.empty and cohort["ready"].all()) else "FAIL",
        "consumers": sorted(matrix["consumer"].unique()) if not matrix.empty else [],
        "input_matrix_ready": bool(matrix["ready"].all()) if not matrix.empty else False,
        "cohort_ready": bool(cohort["ready"].all()) if not cohort.empty else False,
    }
    return matrix, cohort, summary
