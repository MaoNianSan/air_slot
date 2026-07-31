from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np

from .failures import FormalRunBlocked
from .utils import first_existing, sha256_file

TABLE_FILES = {
    "episodes": "episodes.parquet",
    "snapshots": "snapshots.parquet",
    "calibration": "calibration.parquet",
    "rules": "rules.parquet",
    "evidence_audit": "evidence_audit.parquet",
}

FORMAL_TARGET_COLUMN = "y_movement_raw"
SENSITIVITY_TARGET_COLUMN = "y_movement_model"
FORMAL_TARGET_CONTRACT_VERSION = "Y_MOVEMENT_RAW_V1_20260725"


@dataclass(frozen=True)
class ColumnMap:
    episode_id: str
    flight_id: str
    snapshot_id: str
    split: str
    target: str
    airport: str
    stage: str
    decision_time: str
    action_id: str


@dataclass(frozen=True)
class PreBundle:
    episodes: pd.DataFrame
    snapshots: pd.DataFrame
    calibration: pd.DataFrame
    rules: pd.DataFrame
    evidence_audit: pd.DataFrame
    pre_output: Path
    file_hashes: dict[str, str]
    pre_manifest: dict[str, Any]
    columns: ColumnMap


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _coalesce_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    col = first_existing(df.columns, candidates)
    if col is None:
        raise FormalRunBlocked(f"PRE_SCHEMA_MISSING: no {label} column among {candidates}")
    return col


def resolve_m1_target_column(
    episodes: pd.DataFrame, m1: dict[str, Any], *, sensitivity: bool = False
) -> str:
    if "target_candidates" in m1:
        raise FormalRunBlocked("FORMAL_TARGET_AMBIGUOUS: m1.target_candidates is prohibited")
    key = "sensitivity_target" if sensitivity else "formal_target"
    expected = SENSITIVITY_TARGET_COLUMN if sensitivity else FORMAL_TARGET_COLUMN
    configured = m1.get(key)
    if configured != expected:
        raise FormalRunBlocked(f"{key.upper()}_INVALID: expected {expected}, configured {configured!r}")
    if configured not in episodes.columns:
        raise FormalRunBlocked(f"{key.upper()}_MISSING: {configured}")
    return configured


def _build_column_map(episodes: pd.DataFrame, snapshots: pd.DataFrame, rules: pd.DataFrame, scientific: dict[str, Any]) -> ColumnMap:
    m1 = scientific.get("m1", {})
    target = resolve_m1_target_column(episodes, m1)
    episode_id = _coalesce_column(snapshots, ["episode_id", "flight_id"], "episode id")
    flight_id = _coalesce_column(snapshots, m1.get("flight_id_candidates", ["flight_id", "episode_id"]), "flight id")
    snapshot_id = _coalesce_column(snapshots, ["snapshot_id", "snapshot_stage", "stage"], "snapshot id")
    split = _coalesce_column(snapshots, m1.get("split_candidates", ["split", "subset_role"]), "split")
    airport = _coalesce_column(snapshots, m1.get("airport_candidates", []), "airport")
    stage = _coalesce_column(snapshots, m1.get("stage_candidates", []), "snapshot stage")
    decision_time = _coalesce_column(snapshots, m1.get("time_candidates", []), "decision time")
    action_id = _coalesce_column(rules, ["action_id", "action"], "action id")
    return ColumnMap(episode_id, flight_id, snapshot_id, split, target, airport, stage, decision_time, action_id)


def _validate_pre_target_contract(pre_output: Path) -> dict[str, Any]:
    summary = _read_json_if_exists(pre_output / "run_summary.json")
    registry = _read_json_if_exists(pre_output / "artifact_registry.json")
    for source, metadata in (("run_summary", summary), ("artifact_registry", registry)):
        if metadata.get("formal_target_column") != FORMAL_TARGET_COLUMN:
            raise FormalRunBlocked(f"PRE_{source.upper()}_FORMAL_TARGET_INVALID")
        if metadata.get("formal_target_contract_version") != FORMAL_TARGET_CONTRACT_VERSION:
            raise FormalRunBlocked(f"PRE_{source.upper()}_TARGET_CONTRACT_VERSION_INVALID")
        if metadata.get("sensitivity_target_column") != SENSITIVITY_TARGET_COLUMN:
            raise FormalRunBlocked(f"PRE_{source.upper()}_SENSITIVITY_TARGET_INVALID")
        if not metadata.get("formal_target_definition_hash"):
            raise FormalRunBlocked(f"PRE_{source.upper()}_TARGET_DEFINITION_HASH_MISSING")
    if summary["formal_target_definition_hash"] != registry["formal_target_definition_hash"]:
        raise FormalRunBlocked("PRE_FORMAL_TARGET_DEFINITION_HASH_MISMATCH")
    return summary


def load_pre_bundle(pre_output: Path, scientific: dict[str, Any], require_acceptance: bool = True) -> PreBundle:
    pre_output = pre_output.resolve()
    if not pre_output.exists():
        raise FormalRunBlocked(f"PRE_OUTPUT_MISSING: {pre_output}")

    paths = {name: pre_output / filename for name, filename in TABLE_FILES.items()}
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FormalRunBlocked("PRE_TABLE_MISSING: " + ", ".join(missing))

    _validate_pre_target_contract(pre_output)

    acceptance = _read_json_if_exists(pre_output / "reports" / "pre_acceptance.json")
    manifest = _read_json_if_exists(pre_output / "manifests" / "pre_manifest.json")
    if require_acceptance:
        formal = acceptance.get("formal_eligible", manifest.get("formal_eligible"))
        if formal is False:
            raise FormalRunBlocked("PRE_NOT_FORMALLY_ELIGIBLE")
        if formal is None:
            raise FormalRunBlocked("PRE_ACCEPTANCE_MISSING: formal_eligible was not found")

    tables = {}
    for name, path in paths.items():
        if name == "evidence_audit":
            # Read only gate columns while hashing the complete artifact below.
            import pyarrow.parquet as pq

            available = set(pq.ParquetFile(path).schema_arrow.names)
            requested = [
                column for column in (
                    "feature_name", "evidence_status", "imputation_status", "available_by_t",
                    "availability_violation", "future_state_used", "future_metar_used",
                    "future_successor_used", "target_leakage",
                ) if column in available
            ]
            tables[name] = pd.read_parquet(path, columns=requested)
        else:
            tables[name] = pd.read_parquet(path)
    columns = _build_column_map(tables["episodes"], tables["snapshots"], tables["rules"], scientific)
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    return PreBundle(
        episodes=tables["episodes"],
        snapshots=tables["snapshots"],
        calibration=tables["calibration"],
        rules=tables["rules"],
        evidence_audit=tables["evidence_audit"],
        pre_output=pre_output,
        file_hashes=hashes,
        pre_manifest=manifest,
        columns=columns,
    )


def normalize_bundle(bundle: PreBundle) -> dict[str, pd.DataFrame]:
    c = bundle.columns
    episodes = bundle.episodes.copy()
    snapshots = bundle.snapshots.copy()
    rules = bundle.rules.copy()

    if c.episode_id not in episodes.columns:
        source = first_existing(episodes.columns, ["episode_id", "flight_id"])
        if source is None:
            raise FormalRunBlocked("PRE_SCHEMA_MISSING: episode id absent from episodes")
        episodes["episode_id"] = episodes[source].astype(str)
    else:
        episodes["episode_id"] = episodes[c.episode_id].astype(str)
    snapshots["episode_id"] = snapshots[c.episode_id].astype(str)
    snapshots["flight_id"] = snapshots[c.flight_id].astype(str)
    snapshots["snapshot_id"] = snapshots[c.snapshot_id].astype(str)
    snapshots["split"] = snapshots[c.split].astype(str).str.lower()
    snapshots["airport"] = snapshots[c.airport].astype(str).str.upper()
    snapshots["snapshot_stage"] = snapshots[c.stage].astype(str)
    snapshots["decision_time"] = pd.to_datetime(snapshots[c.decision_time], utc=True, errors="coerce")
    episodes["target"] = pd.to_numeric(episodes[FORMAL_TARGET_COLUMN], errors="coerce")
    raw = pd.to_numeric(episodes[FORMAL_TARGET_COLUMN], errors="coerce")
    mismatch = ~(episodes["target"].eq(raw) | (episodes["target"].isna() & raw.isna()))
    if int(mismatch.sum()) != 0:
        raise FormalRunBlocked("FORMAL_TARGET_ALIAS_IDENTITY_MISMATCH")
    rules["episode_id"] = rules[first_existing(rules.columns, ["episode_id", "flight_id"])].astype(str)
    rules["snapshot_id"] = rules[first_existing(rules.columns, ["snapshot_id", "snapshot_stage", "stage"])].astype(str)
    rules["action_id"] = rules[c.action_id].astype(str)

    return {
        "episodes": episodes,
        "snapshots": snapshots,
        "calibration": bundle.calibration.copy(),
        "rules": rules,
        "evidence_audit": bundle.evidence_audit,
    }


def validate_bundle(bundle: PreBundle, scientific: dict[str, Any]) -> dict[str, Any]:
    t = normalize_bundle(bundle)
    e, s, r = t["episodes"], t["snapshots"], t["rules"]
    issues: list[dict[str, Any]] = []

    def add(code: str, value: Any, hard: bool = True) -> None:
        issues.append({"code": code, "value": value, "hard": hard})

    add("duplicate_episode_key", int(e["episode_id"].duplicated().sum()))
    add("duplicate_snapshot_key", int(s.duplicated(["episode_id", "snapshot_id"]).sum()))
    add("duplicate_rule_key", int(r.duplicated(["episode_id", "snapshot_id", "action_id"]).sum()))
    add("invalid_decision_time", int(s["decision_time"].isna().sum()))
    if "episode_valid" in e.columns:
        valid_episode_mask = e["episode_valid"].fillna(False).astype(bool)
    else:
        valid_episode_mask = pd.Series(True, index=e.index)
    add("missing_target_for_valid_episode", int(e.loc[valid_episode_mask, "target"].isna().sum()))
    split_per_flight = s.groupby("flight_id")["split"].nunique()
    add("same_flight_in_multiple_splits", int((split_per_flight > 1).sum()))
    if "split" in e.columns:
        episode_split = e[["episode_id", "split"]].copy()
        episode_split["split"] = episode_split["split"].astype(str).str.lower()
        split_join = s[["episode_id", "split"]].merge(
            episode_split, on="episode_id", how="left", suffixes=("_snapshot", "_episode"), validate="many_to_one"
        )
        add(
            "snapshot_split_mismatch",
            int((split_join["split_snapshot"] != split_join["split_episode"]).fillna(True).sum()),
        )
    if "snapshot_ratio" in s.columns:
        ratio = pd.to_numeric(s["snapshot_ratio"], errors="coerce")
        add("invalid_snapshot_ratio", int((~ratio.between(0, 1)).sum() + ratio.isna().sum()))
        if "elapsed_ratio" in s.columns:
            elapsed = pd.to_numeric(s["elapsed_ratio"], errors="coerce")
            add("snapshot_ratio_mismatch", int((np.abs(ratio - elapsed) > 1e-8).fillna(False).sum()))
    if "snapshot_stage" in s.columns and "snapshot_ratio" in s.columns:
        expected_ratio = {"t1": 0.2, "t2": 0.5, "t3": 0.8}
        primary = s[s["snapshot_stage"].isin(expected_ratio)]
        mismatch = sum(abs(float(row.snapshot_ratio) - expected_ratio[str(row.snapshot_stage)]) > 1e-8 for row in primary.itertuples())
        add("primary_stage_ratio_mismatch", int(mismatch))

    for group_name, candidates in scientific.get("m1", {}).get("required_feature_groups", {}).items():
        add(
            f"m1_feature_group_missing:{group_name}",
            int(not any(col in s.columns for col in candidates)),
        )
    for group_name, candidates in scientific.get("m2", {}).get("required_anchor_groups", {}).items():
        present = any(col in s.columns for col in candidates) or any(col in t["calibration"].columns for col in candidates)
        add(f"m2_anchor_group_missing:{group_name}", int(not present))
    for group_name, candidates in scientific.get("m3", {}).get("required_rule_groups", {}).items():
        found = [field for field in candidates if field in r.columns]
        missing = not found
        add(
            f"m3_rule_group_missing:{group_name}",
            int(missing),
        )
        if missing:
            add(
                f"m3_rule_group_missing_detail:{group_name}",
                f"searched={candidates}, found_none",
                hard=True,
            )
    direct_span = any(c in r.columns for c in ("capacity_span", "flow_q95_minus_q05"))
    paired_span = all(c in r.columns for c in ("capacity_reference_p05", "capacity_reference_p95")) or all(
        c in r.columns for c in ("flow_p05", "flow_p95")
    )
    add("m3_capacity_span_schema_missing", int(not (direct_span or paired_span)))

    expected_actions = {a["id"] for a in scientific.get("m3", {}).get("actions", [])}
    counts = r.groupby(["episode_id", "snapshot_id"], observed=True)["action_id"].nunique()
    valid_snapshot_mask = pd.Series(True, index=s.index)
    for valid_col in ("snapshot_valid", "is_valid", "valid"):
        if valid_col in s.columns:
            valid_snapshot_mask = s[valid_col].fillna(False).astype(bool)
            break
    if "is_primary_snapshot" in s.columns:
        valid_snapshot_mask &= s["is_primary_snapshot"].fillna(False).astype(bool)
    else:
        primary_stages = set(scientific.get("cohort", {}).get("primary_stages", ["t1", "t2", "t3"]))
        valid_snapshot_mask &= s["snapshot_stage"].isin(primary_stages)
    valid_keys = pd.MultiIndex.from_frame(s.loc[valid_snapshot_mask, ["episode_id", "snapshot_id"]].drop_duplicates())
    aligned_counts = counts.reindex(valid_keys, fill_value=0)
    add("valid_snapshot_without_11_actions", int((aligned_counts != len(expected_actions)).sum()))
    a00 = r.groupby(["episode_id", "snapshot_id"], observed=True)["action_id"].apply(lambda x: "A00" in set(x))
    add("a00_missing", int((~a00.reindex(valid_keys, fill_value=False)).sum()))
    add("extra_action_id", int((~r["action_id"].isin(expected_actions)).sum()))
    if "rule_evidence_status" in r.columns:
        add(
            "rule_evidence_status_violation",
            int((r["rule_evidence_status"].astype(str).str.upper() != "RULE_GENERATED").sum()),
        )

    audit = bundle.evidence_audit
    if {"evidence_status", "available_by_t"}.issubset(audit.columns):
        factual = audit["evidence_status"].astype(str).str.upper().isin(["OBSERVED", "DERIVED"])
        available = audit["available_by_t"].fillna(False).astype(bool)
        add("factual_availability_violation", int((factual & ~available).sum()))
    if "feature_name" in audit.columns:
        names = audit["feature_name"].astype(str).str.lower()
        add("target_outcome_in_decision_audit", int(names.str.contains(r"lastseen|y_movement|movement_outcome", regex=True).sum()))
    if "evidence_status" in audit.columns and "imputation_status" in audit.columns:
        observed = audit["evidence_status"].astype(str).str.upper().eq("OBSERVED")
        calibration_imp = audit["imputation_status"].astype(str).str.upper().isin(["CALIBRATION_IMPUTED", "FROZEN_REFERENCE_IMPUTED"])
        add("calibration_proxy_marked_observed", int((observed & calibration_imp).sum()))
    for col, code in (
        ("availability_violation", "factual_availability_violation"),
        ("future_state_used", "future_state_violation"),
        ("future_metar_used", "future_metar_violation"),
        ("future_successor_used", "future_successor_violation"),
        ("target_leakage", "target_leakage"),
    ):
        if col in audit.columns:
            add(code, int(pd.to_numeric(audit[col], errors="coerce").fillna(0).astype(bool).sum()))

    hard_failures = [x for x in issues if x["hard"] and x["value"] not in (0, 0.0, False)]
    if hard_failures:
        lines: list[str] = []
        shown = 0
        for x in hard_failures:
            if shown >= 5:
                lines.append(f"... ({len(hard_failures) - shown} more)")
                break
            value = x["value"]
            if isinstance(value, str):
                lines.append(f"  {x['code']}: {value}")
            else:
                lines.append(f"  {x['code']}={value}")
            shown += 1
        raise FormalRunBlocked(
            f"PRE_INPUT_VALIDATION_FAILED ({len(hard_failures)} issues):\n" + "\n".join(lines)
        )

    return {
        "status": "PASS",
        "issues": issues,
        "rows": {name: int(len(df)) for name, df in t.items()},
        "file_hashes": bundle.file_hashes,
    }
