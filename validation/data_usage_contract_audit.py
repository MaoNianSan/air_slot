"""Read-only Data1/Data2 raw-to-PRE-to-M1 contract audit.

The generated mapping is a diagnostic draft. It never updates authoritative
registries and it never opens a raw-data root.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import subprocess
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import yaml

from model.M1.data import FEATURE_NAMES_V2, STATIC_FEATURE_NAMES
from model.PRE.adapters.registry import SourceAdapterDefinition, SourceAdapterRegistry
from model.PRE.feature_registry.loader import RegistryBundle, load_registry_bundle
from validation.data_usage_classification import (
    ALL_STATUSES,
    classify_source_column,
    zero_failure_counts,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "diagnostics" / "data_usage_contract_audit"
SCHEMA_VERSION = "AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT_V2"
_CANONICALIZERS = {
    "D1-FLIGHTLIST": (
        ("model/PRE/canonical/normalization_flights.py", "canonicalize_flightlist_row"),
    ),
    "D1-STATE": (
        (
            "model/PRE/canonical/normalization_flights.py",
            "canonicalize_state_vector_row",
        ),
    ),
    "D1-METAR": (
        ("model/PRE/canonical/normalization_weather.py", "canonicalize_metar_row"),
    ),
    "D1-EUROSTAT": (
        (
            "model/PRE/canonical/normalization_references.py",
            "canonicalize_eurostat_payload",
        ),
        (
            "model/PRE/canonical/normalization_references.py",
            "canonicalize_eurostat_passengers_payload",
        ),
    ),
    "D1-OURAIRPORTS": (
        ("model/PRE/canonical/normalization_references.py", "canonicalize_airport_row"),
    ),
    "D2-ONTIME": (
        ("model/PRE/canonical/normalization_flights.py", "canonicalize_ontime_row"),
    ),
    "D2-DB1B": (
        (
            "model/PRE/canonical/normalization_references.py",
            "canonicalize_aggregate_row",
        ),
    ),
    "D2-T100": (
        (
            "model/PRE/canonical/normalization_references.py",
            "canonicalize_aggregate_row",
        ),
    ),
    "D2-TIMEZONE": (
        (
            "model/PRE/canonical/normalization_references.py",
            "canonicalize_timezone_row",
        ),
    ),
    "D2-AIRPORT-REFERENCE": (
        ("model/PRE/canonical/normalization_references.py", "canonicalize_airport_row"),
    ),
    "D2-ISD": (
        ("model/PRE/canonical/normalization_weather.py", "canonicalize_isd_row"),
    ),
}
_DOWNSTREAM_ROOTS = ("model/M1", "model/M2", "model/M3", "model/M4", "exp")
_AMBIGUOUS_COLUMN_KEYS = {
    "class",
    "id",
    "lat",
    "lon",
    "number",
    "size",
    "time",
    "type",
    "value",
}
_STATIC_PUBLICATION = {
    "route_context",
    "carrier_context",
    "aircraft_identity",
    "schedule_reference",
    "turnaround_reference",
    "taxi_reference",
}
_ALLOWED_UNPUBLISHED_ROLES = {"EPISODE_CONSTRUCTION", "TRAIN_LABEL", "EVAL_OUTCOME"}


def _source_columns(source: SourceAdapterDefinition) -> tuple[str, ...]:
    return tuple(dict.fromkeys(source.required_columns + source.projected_columns))


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def _function_strings(path: Path, function_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function_name
    )
    return {
        item.value
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def _canonicalizer_columns(source: SourceAdapterDefinition) -> set[str]:
    strings: set[str] = set()
    for relative_path, function_name in _CANONICALIZERS[source.adapter_id]:
        strings.update(_function_strings(ROOT / relative_path, function_name))
    return strings


def _column_accesses(path: Path, known_columns: set[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    findings: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            value = node.slice.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "pop", "setdefault"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            value = node.args[0].value
        if isinstance(value, str) and value in known_columns:
            findings.add((value, node.lineno))
    relative = path.relative_to(ROOT).as_posix()
    return [
        {"raw_column": column, "path": relative, "line": line}
        for column, line in sorted(findings)
    ]


def _downstream_raw_accesses(known_columns: set[str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    scannable = known_columns - _AMBIGUOUS_COLUMN_KEYS
    for root in _DOWNSTREAM_ROOTS:
        for path in sorted((ROOT / root).rglob("*.py")):
            if "__pycache__" not in path.parts:
                findings.extend(_column_accesses(path, scannable))
    return findings


def _runtime_rule_references() -> list[dict[str, Any]]:
    pattern = re.compile(r"^D[12]-[A-Z0-9-]+$")
    findings: set[tuple[str, str, int, str]] = set()
    for path in sorted((ROOT / "model" / "PRE").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if not isinstance(key, ast.Constant) or key.value not in {
                        "provenance_rule_id",
                        "declared_replay_rule_id",
                    }:
                        continue
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and pattern.fullmatch(value.value)
                    ):
                        findings.add(
                            (
                                value.value,
                                path.relative_to(ROOT).as_posix(),
                                value.lineno,
                                str(key.value),
                            )
                        )
            if (
                isinstance(node, ast.keyword)
                and node.arg == "provenance_rule_id"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and pattern.fullmatch(node.value.value)
            ):
                findings.add(
                    (
                        node.value.value,
                        path.relative_to(ROOT).as_posix(),
                        node.value.lineno,
                        node.arg,
                    )
                )
    return [
        {"rule_id": rule_id, "path": path, "line": line, "reference_kind": kind}
        for rule_id, path, line, kind in sorted(findings)
    ]


def _rule_index(bundle: RegistryBundle):
    by_source: dict[tuple[str, str], list[Any]] = defaultdict(list)
    by_column: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for rule in bundle.data_usage_rules:
        by_source[(rule.dataset_id, rule.logical_source)].append(rule)
        for column in rule.raw_columns + rule.projected_columns:
            by_column[(rule.dataset_id, rule.logical_source, column)].append(rule)
    return by_source, by_column


def _definition_index(bundle: RegistryBundle) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for definition in bundle.scientific_variables:
        for canonical_input in definition.canonical_inputs:
            result[canonical_input].append(definition)
    return result


def _rule_audit(
    bundle: RegistryBundle, sources: tuple[SourceAdapterDefinition, ...]
) -> list[dict[str, Any]]:
    source_index = {
        (item.dataset_instance_id, item.source_family): item for item in sources
    }
    definitions = _definition_index(bundle)
    rows = []
    for rule in bundle.data_usage_rules:
        source = source_index.get((rule.dataset_id, rule.logical_source))
        schema = set() if source is None else set(_source_columns(source))
        declared_columns = set(rule.raw_columns) | set(rule.projected_columns)
        missing_source_columns = sorted(declared_columns - schema)
        mapped = definitions.get(rule.canonical_variable, [])
        registry_conflicts = []
        semantic_conflicts = []
        if rule.source_kind != "DERIVED_ARTIFACT" and source is None:
            registry_conflicts.append("SOURCE_ADAPTER_MISSING")
        if missing_source_columns:
            registry_conflicts.append("RULE_COLUMN_NOT_IN_SOURCE_SCHEMA")
        if (
            not mapped
            and rule.decision_time_role.value not in _ALLOWED_UNPUBLISHED_ROLES
            and rule.source_kind == "RAW_SOURCE"
        ):
            registry_conflicts.append("CANONICAL_VARIABLE_NOT_IN_SCIENTIFIC_REGISTRY")
        if mapped and any(item.pre_family != rule.pre_family for item in mapped):
            semantic_conflicts.append("PRE_FAMILY_MISMATCH")
        if rule.rule_id == "D2-BTS-FACTUAL-REPLAY":
            expected = {
                "source_kind": "PROJECTION",
                "source_rule_id": "D2-BTS-ACTUAL",
                "projection_role": "DECLARED_RETROSPECTIVE_FACTUAL_REPLAY",
                "declared_lag_minutes": 0,
                "observed_message_arrival_claim": False,
                "production_availability_claim": False,
                "source_outcome_role_preserved": True,
            }
            for field, value in expected.items():
                if getattr(rule, field) != value:
                    semantic_conflicts.append(
                        f"FACTUAL_REPLAY_{field.upper()}_MISMATCH"
                    )
        status = (
            "ACTIVE_REGISTRY_CONFLICT"
            if registry_conflicts
            else "ACTIVE_SEMANTIC_CONFLICT" if semantic_conflicts else "COVERED_ACTIVE"
        )
        rows.append(
            {
                "rule_id": rule.rule_id,
                "dataset_instance_id": rule.dataset_id,
                "source_family": rule.logical_source,
                "canonical_variable": rule.canonical_variable,
                "scientific_variables": sorted(
                    item.scientific_variable for item in mapped
                ),
                "missing_source_columns": missing_source_columns,
                "source_kind": rule.source_kind,
                "status": status,
                "findings": registry_conflicts + semantic_conflicts,
            }
        )
    return rows


def _raw_column_audit(
    bundle: RegistryBundle,
    sources: tuple[SourceAdapterDefinition, ...],
    bypasses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    _, by_column = _rule_index(bundle)
    bypass_by_column: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in bypasses:
        bypass_by_column[finding["raw_column"]].append(finding)
    rows = []
    source_keys = {(item.dataset_instance_id, item.source_family) for item in sources}
    for source in sources:
        used = _canonicalizer_columns(source)
        required = set(source.required_columns)
        projected = set(source.projected_columns)
        primary_rules = set(source.rule_ids)
        for column in _source_columns(source):
            matches = by_column[
                (source.dataset_instance_id, source.source_family, column)
            ]
            matched_ids = {item.rule_id for item in matches}
            declared_role = source.column_roles.get(column)
            status, findings = classify_source_column(
                declared_role=declared_role,
                canonicalizer_accessed=column in used,
                matched_rule_ids=matched_ids,
                primary_rule_ids=primary_rules,
                pre_bypass=bool(bypass_by_column[column]),
            )
            rows.append(
                {
                    "dataset_instance_id": source.dataset_instance_id,
                    "adapter_id": source.adapter_id,
                    "source_family": source.source_family,
                    "raw_column": column,
                    "required": column in required,
                    "projected": column in projected,
                    "canonicalizer_accessed": column in used,
                    "declared_role": declared_role,
                    "rule_ids": sorted(matched_ids),
                    "primary_rule_ids": sorted(primary_rules & matched_ids),
                    "status": status,
                    "findings": findings,
                    "pre_bypass_locations": bypass_by_column[column],
                }
            )
    for rule in bundle.data_usage_rules:
        key = (rule.dataset_id, rule.logical_source)
        if key not in source_keys:
            continue
        source = next(
            item
            for item in sources
            if (item.dataset_instance_id, item.source_family) == key
        )
        schema = set(_source_columns(source))
        used = _canonicalizer_columns(source)
        declared_columns = set(rule.raw_columns) | set(rule.projected_columns)
        for column in sorted(declared_columns - schema):
            rows.append(
                {
                    "dataset_instance_id": rule.dataset_id,
                    "adapter_id": source.adapter_id,
                    "source_family": rule.logical_source,
                    "raw_column": column,
                    "required": False,
                    "projected": False,
                    "canonicalizer_accessed": column in used,
                    "rule_ids": [rule.rule_id],
                    "primary_rule_ids": [],
                    "declared_role": None,
                    "status": "ACTIVE_REGISTRY_CONFLICT",
                    "findings": ["REGISTRY_COLUMN_NOT_DECLARED_BY_SOURCE_ADAPTER"],
                    "pre_bypass_locations": bypass_by_column[column],
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["dataset_instance_id"],
            row["adapter_id"],
            row["raw_column"],
            row["rule_ids"],
        ),
    )


def _mapping_draft(
    bundle: RegistryBundle,
    sources: tuple[SourceAdapterDefinition, ...],
    raw_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rules = {item.rule_id: item for item in bundle.data_usage_rules}
    sources_by_id = {item.adapter_id: item for item in sources}
    result = []
    for row in raw_rows:
        source = sources_by_id[row["adapter_id"]]
        matched = [rules[rule_id] for rule_id in row["rule_ids"]]
        candidates: Iterable[Any] = matched or (None,)
        for rule in candidates:
            result.append(
                {
                    "authoritative": False,
                    "draft_status": row["status"],
                    "dataset_instance_id": row["dataset_instance_id"],
                    "adapter_id": row["adapter_id"],
                    "source": row["source_family"],
                    "raw_column": row["raw_column"],
                    "source_schema_declared": row["required"] or row["projected"],
                    "canonicalizer_accessed": row["canonicalizer_accessed"],
                    "candidate_rule_ids": (
                        ";".join(source.rule_ids) if rule is None else ""
                    ),
                    "rule_id": "" if rule is None else rule.rule_id,
                    "canonical_variable": (
                        "" if rule is None else rule.canonical_variable
                    ),
                    "owner": "PRE",
                    "role": "" if rule is None else rule.decision_time_role.value,
                    "raw_unit": (
                        "" if rule is None or rule.raw_unit is None else rule.raw_unit
                    ),
                    "unit": "" if rule is None else rule.canonical_unit,
                    "availability_rule": "" if rule is None else rule.availability_rule,
                    "transformation": "" if rule is None else rule.transformation_rule,
                    "missing_rule": "" if rule is None else rule.missing_rule,
                    "downstream_module": (
                        "" if rule is None else ";".join(rule.downstream_consumers)
                    ),
                    "provenance": (
                        "" if rule is None else f"{rule.rule_id}@{rule.rule_version}"
                    ),
                    "findings": ";".join(row["findings"]),
                }
            )
    return result


def _pre_output_audit(
    bundle: RegistryBundle, rule_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    conflict_variables = {
        row["canonical_variable"]
        for row in rule_rows
        if row["status"] in {"ACTIVE_SEMANTIC_CONFLICT", "ACTIVE_REGISTRY_CONFLICT"}
    }
    rows = []
    for definition in bundle.scientific_variables:
        variable = definition.scientific_variable
        if variable in _STATIC_PUBLICATION:
            publication = "PRE_STATIC_REFERENCE_PUBLICATION"
        elif variable == "realized_operational_event":
            publication = "POSTHOC_OUTCOME_WITH_SEPARATE_FACTUAL_REPLAY_PROJECTION"
        else:
            publication = "REGISTRY_PRE_MAPPER"
        conflicts = sorted(set(definition.canonical_inputs) & conflict_variables)
        rows.append(
            {
                "scientific_variable": variable,
                "pre_family": definition.pre_family,
                "canonical_inputs": list(definition.canonical_inputs),
                "publication_path": publication,
                "consumers": list(definition.consumers),
                "status": (
                    "ACTIVE_PRE_OUTPUT_CONFLICT" if conflicts else "COVERED_ACTIVE"
                ),
                "findings": (
                    []
                    if not conflicts
                    else ["UPSTREAM_RULE_CONFLICT:" + ",".join(conflicts)]
                ),
            }
        )
    return rows


def _feature_upstream(name: str) -> tuple[str, str]:
    if name.startswith("turnaround_reference_minutes"):
        return "turnaround_reference", "PRE_STATIC_REFERENCE_PUBLICATION"
    if name.startswith("taxi_reference_minutes"):
        return "taxi_reference", "PRE_STATIC_REFERENCE_PUBLICATION"
    if name.startswith(("weather.", "delta.weather.", "ar.weather.")):
        return "current_weather", "PRE_CURRENT_STATE"
    if name.startswith(("schedule.", "delta.schedule.")):
        return "schedule_reference", "PRE_SUCCESSOR_STATE"
    if name.startswith("state."):
        return "decision_node.operational_stage", "PRE_FACTUAL_REPLAY_STAGE"
    for variable in ("current_weather", "schedule_reference", "current_state"):
        if name.startswith(variable + "."):
            upstream = (
                "decision_node.operational_stage"
                if variable == "current_state"
                else variable
            )
            return upstream, "M1_EVIDENCE_SUPPORT_ENCODING"
    return "", ""


def _m1_feature_audit() -> list[dict[str, Any]]:
    rows = []
    for branch, names in (
        ("dynamic", FEATURE_NAMES_V2),
        ("static", STATIC_FEATURE_NAMES),
    ):
        for feature in names:
            upstream, path = _feature_upstream(feature)
            rows.append(
                {
                    "feature": feature,
                    "branch": branch,
                    "upstream_pre_variable": upstream,
                    "consumption_path": path,
                    "status": (
                        "COVERED_ACTIVE" if upstream else "RUNTIME_USED_NO_CONTRACT"
                    ),
                    "findings": [] if upstream else ["M1_FEATURE_UPSTREAM_UNRESOLVED"],
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        json.dumps(value, sort_keys=True)
                        if isinstance(value, (list, dict))
                        else value
                    )
                    for key, value in row.items()
                }
            )


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in ALL_STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    return counts


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def run(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    registry_root = ROOT / "registries"
    bundle = load_registry_bundle(registry_root)
    source_registry_path = registry_root / "source_adapter_registry.yaml"
    sources = SourceAdapterRegistry.load(source_registry_path).sources
    known_columns = {column for source in sources for column in _source_columns(source)}
    bypasses = _downstream_raw_accesses(known_columns)
    rule_rows = _rule_audit(bundle, sources)
    raw_rows = _raw_column_audit(bundle, sources, bypasses)
    mapping_rows = _mapping_draft(bundle, sources, raw_rows)
    pre_rows = _pre_output_audit(bundle, rule_rows)
    m1_rows = _m1_feature_audit()
    registered_rule_ids = {item.rule_id for item in bundle.data_usage_rules}
    runtime_refs = _runtime_rule_references()
    missing_runtime_rules = [
        item for item in runtime_refs if item["rule_id"] not in registered_rule_ids
    ]
    source_files = (
        "registries/source_adapter_registry.yaml",
        "registries/data_usage_rules.yaml",
        "registries/scientific_variables.yaml",
        "registries/dataset_capabilities.yaml",
        "configs/scientific/foundation.yaml",
        "model/M2/freeze.py",
        "model/PRE/adapters/registry.py",
        "model/PRE/canonical/data2_timestamps.py",
        "model/PRE/canonical/normalization_flights.py",
        "model/PRE/canonical/normalization_weather.py",
        "model/PRE/canonical/normalization_references.py",
        "model/PRE/contracts/training_artifacts.py",
        "model/PRE/feature_registry/models.py",
        "model/PRE/mapping.py",
        "model/PRE/publication/static_reference.py",
        "model/M1/data.py",
        "model/PRE/reference/data2_m2_train_fit.py",
        "docs/reconciliation/AIR_SLOT_DATA_USAGE_CONTRACT_V1.md",
        "validation/data_usage_classification.py",
        "validation/data_usage_contract_audit.py",
    )
    all_rows = [
        row for rows in (raw_rows, rule_rows, pre_rows, m1_rows) for row in rows
    ]
    failure_counts = zero_failure_counts()
    for row in all_rows:
        if row["status"] in failure_counts:
            failure_counts[row["status"]] += 1
    failure_counts["RUNTIME_USED_NO_CONTRACT"] += len(missing_runtime_rules)
    status = (
        "DATA_USAGE_CONTRACT_AUDIT_PASS"
        if all(count == 0 for count in failure_counts.values())
        else "DATA_USAGE_CONTRACT_REVIEW_REMAINS"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "mapping_draft": output_dir / "AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.csv",
        "mapping_draft_yaml": output_dir / "AIR_SLOT_DATA_USAGE_MAPPING_DRAFT.yaml",
        "raw_column_audit": output_dir / "AIR_SLOT_DATA_USAGE_RAW_COLUMN_AUDIT.csv",
        "pre_output_audit": output_dir / "AIR_SLOT_DATA_USAGE_PRE_OUTPUT_AUDIT.csv",
        "m1_feature_audit": output_dir / "AIR_SLOT_DATA_USAGE_M1_FEATURE_AUDIT.csv",
        "audit": output_dir / "AIR_SLOT_DATA_USAGE_CONTRACT_AUDIT.json",
    }
    _write_csv(paths["mapping_draft"], mapping_rows)
    _write_yaml(
        paths["mapping_draft_yaml"],
        {
            "schema_version": "AIR_SLOT_DATA_USAGE_MAPPING_DRAFT_V1",
            "authoritative": False,
            "status": (
                "PASS"
                if status == "DATA_USAGE_CONTRACT_AUDIT_PASS"
                else "REVIEW_REQUIRED"
            ),
            "generated_from": SCHEMA_VERSION,
            "mappings": mapping_rows,
        },
    )
    _write_csv(paths["raw_column_audit"], raw_rows)
    _write_csv(paths["pre_output_audit"], pre_rows)
    _write_csv(paths["m1_feature_audit"], m1_rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "authority": "CONTRACT_VALIDATION_AFTER_HUMAN_DECISIONS",
        "repository_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_hashes": {path: _file_hash(ROOT / path) for path in source_files},
        "scope": "READ_ONLY_REGISTRY_PRE_M1_STATIC_AUDIT",
        "status": status,
        "counts": {
            "source_adapters": len(sources),
            "data_usage_rules": len(bundle.data_usage_rules),
            "raw_column_rows": len(raw_rows),
            "raw_column_status": _counts(raw_rows),
            "rule_status": _counts(rule_rows),
            "pre_output_status": _counts(pre_rows),
            "m1_feature_status": _counts(m1_rows),
            "mapping_draft_rows": len(mapping_rows),
            "runtime_rule_references_missing_from_registry": len(missing_runtime_rules),
            **failure_counts,
        },
        "raw_column_audit": raw_rows,
        "rule_audit": rule_rows,
        "pre_output_audit": pre_rows,
        "m1_feature_audit": m1_rows,
        "pre_bypass_findings": bypasses,
        "runtime_rule_references": runtime_refs,
        "missing_runtime_rule_registrations": missing_runtime_rules,
        "artifacts": {
            key: path.relative_to(output_dir).as_posix() for key, path in paths.items()
        },
        "safety": {
            "M1_TRAINING_RUNS": 0,
            "TUNING_RUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
            "GATE_B_ENTERED": False,
        },
        "artifact_hash_basis": "JSON_SERIALIZED_PAYLOAD_WITHOUT_ARTIFACT_HASH",
    }
    payload["artifact_hash"] = _payload_hash(payload)
    paths["audit"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
