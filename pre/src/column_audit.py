from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import yaml

from .column_audit_sources import raw_samples
from .column_audit_report import write_column_audit_reports


AUDIT_COLUMNS = [
    "table_or_source",
    "actual_column",
    "source_column",
    "dtype",
    "unit",
    "nonmissing_count",
    "missing_rate",
    "unique_count",
    "example_values",
    "time_semantics",
    "availability_semantics",
    "current_consumers",
    "candidate_roles",
    "proposed_preprocessing",
    "retain_status",
    "alias_target",
    "evidence_support",
    "notes",
]


def _examples(series: pd.Series) -> str:
    values = series.dropna().astype(str).drop_duplicates().head(3).tolist()
    return json.dumps(values, ensure_ascii=False)


def _roles(table: str, column: str, dtype: str) -> list[str]:
    name = column.lower()
    roles: list[str] = []
    if name.endswith("_id") or name in {
        "episode_id",
        "snapshot_id",
        "flight_id",
        "icao24",
        "action_id",
        "airport",
        "origin",
        "destination",
    }:
        roles.append("IDENTITY")
    if any(token in name for token in ["time", "date", "month", "period", "firstseen", "lastseen"]):
        roles.append("TIME")
    if any(token in name for token in ["coverage", "age", "count", "missing", "quality", "valid", "eligible", "status"]):
        roles.append("QUALITY")
    if any(token in name for token in ["source", "evidence", "hash", "record_id", "availability", "fallback"]):
        roles.append("EVIDENCE")
    if name.startswith("y_") or "label" in name:
        roles.extend(["LABEL", "TARGET_SOURCE"])
    if any(token in name for token in ["reference", "climatology", "typical", "p05", "p50", "p90", "p95"]):
        roles.append("REFERENCE")
    if table == "calibration" or name in {"turnaround_margin", "airport_flow_pressure"}:
        roles.append("M2_ANCHOR")
    if table == "rules" or any(token in name for token in ["authority", "resource_available", "window_open", "constraint"]):
        roles.append("M4_CONSTRAINT_SOURCE")
    if any(token in name for token in ["lastseen", "outcome", "successor_", "future_"]) or name.startswith("y_"):
        roles.append("FORBIDDEN_MODEL_INPUT")
    numeric = any(token in dtype.lower() for token in ["int", "float", "double", "decimal"])
    if numeric and not set(roles) & {"LABEL", "TIME"}:
        roles.append(
            "STATIC_CONTINUOUS"
            if any(token in name for token in ["runway", "infrastructure", "airport_scale", "seat_capacity"])
            else "DYNAMIC_CONTINUOUS"
        )
    if not numeric and not set(roles) & {"TIME", "EVIDENCE"}:
        roles.append("CATEGORICAL")
    if table.startswith("raw:"):
        roles.append("LINEAGE")
    if not roles:
        roles.append("AUDIT_ONLY")
    return list(dict.fromkeys(roles))


def _time_semantics(column: str) -> str:
    name = column.lower()
    if "availability" in name or "ingested" in name:
        return "knowledge_time_utc"
    if any(token in name for token in ["event_time", "observation_time", "valid", "firstseen", "lastseen", "decision_time", "snapshot_time"]):
        return "event_or_decision_time_utc"
    if "month" in name or "period" in name:
        return "calendar_period"
    if "date" in name:
        return "calendar_date"
    return "not_time"


def _availability_semantics(table: str, column: str) -> str:
    name = column.lower()
    if "availability_time" in name:
        return "explicit_availability_time"
    if table == "raw:state_vectors":
        return "current_PRE_sets_availability_equal_event_time_plus_configured_lag"
    if table == "raw:metar":
        return "current_PRE_sets_availability_from_observation_time_plus_configured_lag"
    if table == "raw:flightlist":
        return "completed_flight_record; current_PRE_uses_completed_flightlist_lag"
    if table.startswith("raw:eurostat"):
        return "period_end_publication_semantics_required"
    return "derived_or_not_applicable"


def _consumers(table: str, column: str, m1_features: set[str]) -> str:
    consumers = ["PRE"] if table.startswith("raw:") else []
    if table in {"episodes", "snapshots", "calibration", "rules", "evidence_audit"}:
        consumers.append("overall_run")
    if table in {"episodes", "snapshots"}:
        consumers.append("part_adv")
    if column in m1_features:
        consumers.append("M1")
    if table == "calibration":
        consumers.append("M2")
    if table == "rules":
        consumers.extend(["M3", "M4"])
    return "|".join(dict.fromkeys(consumers))


def _preprocessing(roles: list[str], dtype: str) -> str:
    if "FORBIDDEN_MODEL_INPUT" in roles:
        return "retain_for_label_or_audit; exclude_from_model_features"
    if "TIME" in roles:
        return "parse_utc_or_period; preserve_original"
    if "CATEGORICAL" in roles:
        return "normalize_explicitly; encode_downstream; keep_missing_category"
    if any(role.endswith("CONTINUOUS") for role in roles):
        return "numeric_coerce; preserve_missing; fit_scaling_on_train_only"
    return "preserve"


def _profile_frame(
    table: str,
    frame: pd.DataFrame,
    *,
    source_map: dict[str, str],
    units: dict[str, str],
    aliases: dict[str, str],
    m1_features: set[str],
    total_rows: int | None = None,
    full_nonmissing: dict[str, int] | None = None,
    notes: str = "",
) -> list[dict[str, Any]]:
    denominator = int(total_rows if total_rows is not None else len(frame))
    rows = []
    for column in frame.columns:
        sample = frame[column]
        dtype = str(sample.dtype)
        nonmissing = int((full_nonmissing or {}).get(column, sample.notna().sum()))
        roles = _roles(table, str(column), dtype)
        alias_target = aliases.get(str(column), "")
        row_notes = notes
        if total_rows is not None and len(frame) < total_rows:
            row_notes = (row_notes + "; " if row_notes else "") + (
                f"examples_and_unique_count_sampled_from={len(frame)}"
            )
        rows.append(
            {
                "table_or_source": table,
                "actual_column": str(column),
                "source_column": source_map.get(str(column), str(column)),
                "dtype": dtype,
                "unit": units.get(str(column), "unspecified"),
                "nonmissing_count": nonmissing,
                "missing_rate": (1.0 - nonmissing / denominator) if denominator else 1.0,
                "unique_count": int(sample.nunique(dropna=True)),
                "example_values": _examples(sample),
                "time_semantics": _time_semantics(str(column)),
                "availability_semantics": _availability_semantics(table, str(column)),
                "current_consumers": _consumers(table, str(column), m1_features),
                "candidate_roles": "|".join(roles),
                "proposed_preprocessing": _preprocessing(roles, dtype),
                "retain_status": "ALIAS_RETAIN" if alias_target else "RETAIN",
                "alias_target": alias_target,
                "evidence_support": "OBSERVED_RAW" if table.startswith("raw:") else "DERIVED_OR_PUBLISHED",
                "notes": row_notes,
            }
        )
    return rows


def _parquet_profile(path: Path) -> tuple[pd.DataFrame, int, dict[str, int]]:
    parquet = pq.ParquetFile(path)
    total = parquet.metadata.num_rows
    sample = parquet.read_row_group(0).slice(0, 50_000).to_pandas()
    nonmissing: dict[str, int] = {}
    for index, name in enumerate(parquet.schema_arrow.names):
        nulls = 0
        known = True
        for group in range(parquet.num_row_groups):
            stats = parquet.metadata.row_group(group).column(index).statistics
            if stats is None or stats.null_count is None:
                known = False
                break
            nulls += int(stats.null_count)
        nonmissing[name] = int(total - nulls) if known else int(sample[name].notna().sum())
    return sample, int(total), nonmissing


def build_column_audit(cfg: dict[str, Any], output_root: Path) -> pd.DataFrame:
    inventory = pd.read_parquet(output_root / "manifests" / "raw_inventory.parquet")
    aliases = cfg["schema"].get("aliases", {})
    m1_features = set(cfg["schema"].get("m1_required_inputs", {}).get("continuous", []))
    m1_features.update(cfg["schema"].get("m1_required_inputs", {}).get("categorical", []))
    overall_root = cfg["project_root"].parent / "overall_run" / "config"
    for config_name in ["default.yaml", "scientific.yaml"]:
        payload = yaml.safe_load((overall_root / config_name).read_text(encoding="utf-8"))
        m1_features.update(payload.get("m1", {}).get("feature_allowlist", []))
    rows: list[dict[str, Any]] = []
    for table in ["episodes", "snapshots", "calibration", "rules", "evidence_audit"]:
        sample, total, nonmissing = _parquet_profile(output_root / f"{table}.parquet")
        rows.extend(
            _profile_frame(
                table,
                sample,
                source_map={},
                units={},
                aliases=aliases,
                m1_features=m1_features,
                total_rows=total,
                full_nonmissing=nonmissing,
                notes="accepted_fast_2026-08-03",
            )
        )
    source_maps: dict[str, dict[str, str]] = {}
    units: dict[str, dict[str, str]] = {}
    for source, spec in cfg["sources"].items():
        mapping = spec.get("columns", {})
        source_maps[f"raw:{source}"] = {actual: canonical for canonical, actual in mapping.items()}
        unit_map = spec.get("input_units", {})
        units[f"raw:{source}"] = {mapping.get(canonical, canonical): unit for canonical, unit in unit_map.items()}
    airport_spec = cfg["sources"]["ourairports"]
    source_maps["raw:ourairports_airports"] = {
        actual: canonical
        for canonical, actual in airport_spec["airport_columns"].items()
    }
    source_maps["raw:ourairports_runways"] = {
        actual: canonical
        for canonical, actual in airport_spec["runway_columns"].items()
    }
    source_maps["raw:eurostat_passengers"].update(
        {"rep_airp": "airport", "time": "source_period", "value": "passengers"}
    )
    source_maps["raw:eurostat_flights"].update(
        {"rep_airp": "airport", "time": "source_period", "value": "commercial_flights"}
    )
    for table, (sample, note) in raw_samples(inventory).items():
        rows.extend(
            _profile_frame(
                table,
                sample,
                source_map=source_maps.get(table, {}),
                units=units.get(table, {}),
                aliases=aliases,
                m1_features=m1_features,
                notes=note,
            )
        )
    return pd.DataFrame(rows, columns=AUDIT_COLUMNS)


def write_column_audit(cfg: dict[str, Any], output_root: Path, report_dir: Path) -> pd.DataFrame:
    audit = build_column_audit(cfg, output_root)
    write_column_audit_reports(audit, report_dir)
    return audit
