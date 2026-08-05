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


def build_column_registry(
    tables: dict[str, pd.DataFrame], cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    roles = cfg["core_schema"].get("column_roles", {})
    aliases = cfg["core_schema"].get("column_aliases", {})
    alias_target = {value: key for key, value in aliases.items()}
    units = {
        "altitude": "metres",
        "velocity": "metres_per_second",
        "vertical_rate": "metres_per_second",
        "observed_ground_gap_minutes": "minutes",
        "reference_value": "declared_by_reference_type",
    }
    frames = dict(tables)
    frames["observations"] = pd.DataFrame(columns=COMMON_COLUMNS)
    rows: list[dict[str, Any]] = []
    for table, frame in frames.items():
        for column in frame.columns:
            rows.append(
                {
                    "table": table,
                    "column": column,
                    "dtype": str(frame[column].dtype),
                    "nullable": bool(frame[column].isna().any()) if len(frame) else True,
                    "unit": units.get(column, "dimensionless_or_not_applicable"),
                    "roles": roles.get(column, ["AUDIT_ONLY"]),
                    "source_column": alias_target.get(column, "DERIVED_OR_DECLARED"),
                    "alias_target": aliases.get(column, ""),
                    "preprocessing": "IDENTITY_OR_DECLARED_TRANSFORM",
                    "evidence_support": "EXPLICIT_LINEAGE",
                }
            )
    return sorted(rows, key=lambda row: (row["table"], row["column"]))


def validate_column_registry(
    registry: list[dict[str, Any]], cfg: dict[str, Any]
) -> dict[str, Any]:
    required = set(cfg["core_schema"]["column_registry_required"])
    missing_fields = sorted(
        {field for row in registry for field in required if field not in row}
    )
    cycles = _alias_cycles(cfg["core_schema"].get("column_aliases", {}))
    forbidden = set(cfg["core_schema"].get("forbidden_aliases", []))
    aliases = set(cfg["core_schema"].get("column_aliases", {}))
    forbidden_present = sorted(forbidden & aliases)
    return {
        "status": "PASS" if not missing_fields and not cycles and not forbidden_present else "FAIL",
        "registry_rows": len(registry),
        "missing_registry_fields": missing_fields,
        "alias_cycles": cycles,
        "forbidden_aliases_present": forbidden_present,
    }
