from __future__ import annotations

from typing import Any

import pandas as pd

from .observation_builder import COMMON_COLUMNS


def _alias_cycles(aliases: dict[str, str]) -> list[list[str]]:
    cycles: list[list[str]] = []
    for start in aliases:
        path: list[str] = []
        current = start
        while current in aliases:
            if current in path:
                cycles.append(path[path.index(current) :] + [current])
                break
            path.append(current)
            current = aliases[current]
    return cycles


def _base_row(
    *,
    table: str,
    source: str,
    raw_column: str,
    standard_column: str,
    dtype: str,
    nullable: bool,
    roles: list[str],
    alias_target: str,
    retention_status: str,
    retention_reason: str,
    preprocessing: str,
    evidence_support: str,
) -> dict[str, Any]:
    forbidden = "FORBIDDEN_MODEL_INPUT" in roles or "AUDIT_ONLY" in roles
    return {
        "table": table,
        "source": source,
        "raw_column": raw_column,
        "standard_column": standard_column,
        # ``column`` and ``source_column`` remain as compatibility aliases for
        # existing internal consumers; V2 fields above are authoritative.
        "column": standard_column,
        "dtype": dtype,
        "nullable": bool(nullable),
        "unit": "dimensionless_or_not_applicable",
        "roles": roles,
        "source_column": raw_column or "DERIVED_OR_DECLARED",
        "preprocessing": preprocessing,
        "retention_status": retention_status,
        "retention_reason": retention_reason,
        "alias_target": alias_target,
        "evidence_support": evidence_support,
        "model_input_allowed": not forbidden,
    }


def build_column_registry(
    tables: dict[str, pd.DataFrame],
    cfg: dict[str, Any],
    *,
    raw_inventory: pd.DataFrame | None = None,
    source_columns: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    roles = cfg["core_schema"].get("column_roles", {})
    aliases = cfg["core_schema"].get("column_aliases", {})
    units = {
        "altitude": "metres",
        "velocity": "metres_per_second",
        "vertical_rate": "metres_per_second",
        "observed_ground_gap_minutes": "minutes",
        "reference_value": "declared_by_reference_type",
    }
    frames = dict(tables)
    observed_columns = set(COMMON_COLUMNS)
    for values in (source_columns or {}).values():
        observed_columns.update(values)
    frames.setdefault("observations", pd.DataFrame(columns=sorted(observed_columns)))
    rows: list[dict[str, Any]] = []

    # First register every raw source mapping, including fields that are not
    # materialized in this run.  Presence in an output DataFrame is not the
    # definition of the raw audit surface.
    for source_name, spec in sorted(cfg.get("sources", {}).items()):
        mapping = spec.get("columns", {})
        for standard, raw in sorted(mapping.items()):
            raw_text = str(raw)
            retained = raw_text in (source_columns or {}).get(source_name, []) or standard in observed_columns
            source_table = "observations" if source_name in {"state_vectors", "metar"} else "source_audit"
            rows.append(
                _base_row(
                    table=source_table,
                    source=source_name,
                    raw_column=raw_text,
                    standard_column=str(standard),
                    dtype="unknown_until_source_audit",
                    nullable=True,
                    roles=list(roles.get(str(standard), ["AUDIT_ONLY"])),
                    alias_target=aliases.get(str(standard), ""),
                    retention_status="RETAINED" if retained else "NOT_MATERIALIZED",
                    retention_reason="" if retained else "SOURCE_COLUMN_NOT_AVAILABLE_IN_CACHE_OR_NOT_REQUESTED",
                    preprocessing="STANDARDIZED_MAPPING",
                    evidence_support="SOURCE_SCHEMA_DECLARED",
                )
            )

    source_aliases = {"state": "state_vectors", "weather": "metar", "flow": "state_vectors"}
    existing_raw = {(row["source"], row["raw_column"], row["standard_column"]) for row in rows}
    for observation_source, columns in sorted((source_columns or {}).items()):
        source_name = source_aliases.get(observation_source, observation_source)
        for column in sorted(set(columns) - set(COMMON_COLUMNS)):
            identity = (source_name, str(column), str(column))
            if identity in existing_raw:
                continue
            rows.append(
                _base_row(
                    table="observations",
                    source=source_name,
                    raw_column=str(column),
                    standard_column=str(column),
                    dtype="published_source_dtype",
                    nullable=True,
                    roles=list(roles.get(str(column), ["AUDIT_ONLY"])),
                    alias_target=aliases.get(str(column), ""),
                    retention_status="RETAINED",
                    retention_reason="",
                    preprocessing="RAW_COLUMN_PRESERVED",
                    evidence_support="OBSERVED_IN_PUBLISHED_SOURCE_SCHEMA",
                )
            )
            existing_raw.add(identity)

    # Then register every published/derived table column, preserving the
    # historical compatibility key ``column``.
    for table, frame in frames.items():
        for column in frame.columns:
            name = str(column)
            row = _base_row(
                table=table,
                source="DERIVED" if table != "observations" else "SOURCE_GLOBAL",
                raw_column="",
                standard_column=name,
                dtype=str(frame[column].dtype),
                nullable=bool(frame[column].isna().any()) if len(frame) else True,
                roles=list(roles.get(name, ["AUDIT_ONLY"])),
                alias_target=aliases.get(name, ""),
                retention_status="RETAINED",
                retention_reason="",
                preprocessing="IDENTITY_OR_DECLARED_TRANSFORM",
                evidence_support="EXPLICIT_LINEAGE",
            )
            row["unit"] = units.get(name, "dimensionless_or_not_applicable")
            rows.append(row)
    return sorted(rows, key=lambda row: (row["table"], row["source"], row["standard_column"], row["raw_column"]))


def validate_column_registry(registry: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    required = set(cfg["core_schema"]["column_registry_required"])
    missing_fields = sorted({field for row in registry for field in required if field not in row})
    cycles = _alias_cycles(cfg["core_schema"].get("column_aliases", {}))
    forbidden = set(cfg["core_schema"].get("forbidden_aliases", []))
    aliases = set(cfg["core_schema"].get("column_aliases", {}))
    forbidden_present = sorted(forbidden & aliases)
    raw_coverage = [
        row for row in registry
        if row.get("raw_column") and row.get("retention_status") == "NOT_MATERIALIZED"
        and not row.get("retention_reason")
    ]
    status = "PASS" if not missing_fields and not cycles and not forbidden_present and not raw_coverage else "FAIL"
    return {
        "status": status,
        "registry_rows": len(registry),
        "missing_registry_fields": missing_fields,
        "alias_cycles": cycles,
        "forbidden_aliases_present": forbidden_present,
        "raw_coverage_gaps": len(raw_coverage),
    }
