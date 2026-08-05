from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..input import object_hash, sha256_file
from .chain_validation import validate_chains
from .column_registry import validate_column_registry
from .contracts import (
    CONTRACT_ID,
    RESEARCH_CODE_REVISION,
    SCHEMA_VERSION,
    contract_hashes,
    frozen_config_hash,
    git_metadata,
    implementation_hash,
    schema_hash,
    stable_id,
)
from .event_validation import validate_events
from .membership_dataset import (
    MEMBERSHIP_PARTITION_MANIFEST_NAME,
    expected_empty_schema_fingerprint as membership_empty_schema_fingerprint,
)
from .membership_interval_join import MEMBERSHIP_COLUMNS
from .observation_dataset import (
    EMPTY_REASONS,
    VALIDATION_COLUMNS,
    expected_empty_schema_fingerprint as observation_empty_schema_fingerprint,
    schema_fingerprint,
)
from .observation_membership import validate_observation_membership
from .observation_validation import validate_observations
from .validation import core_statistics
from .writer import dataframe_hash


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parquet_metadata(path: Path) -> tuple[list[str], int, str]:
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    columns = list(schema.names)
    dtypes = [str(schema.field(name).type) for name in columns]
    return columns, int(parquet.metadata.num_rows), schema_fingerprint(columns, dtypes)


def _schema_and_keys(
    root: Path, cfg: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    failures: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}
    for name, spec in cfg["core_schema"]["tables"].items():
        if name in {"observations", "observation_membership"}:
            continue
        path = root / f"{name}.parquet"
        if not path.exists():
            failures[name] = {"missing_file": True}
            continue
        frame = pd.read_parquet(path)
        tables[name] = frame
        missing = sorted(set(spec.get("required", [])) - set(frame.columns))
        duplicate = int(frame.duplicated(spec.get("key", [])).sum()) if not missing else -1
        if missing or duplicate:
            failures[name] = {"missing_columns": missing, "duplicate_keys": duplicate}
    return failures, tables


def _dataset_file_audit(
    dataset_root: Path,
    partition_manifest: dict[str, Any],
) -> dict[str, list[str]]:
    partitions = partition_manifest.get("partitions", {})
    registered = {
        str(record["relative_path"])
        for record in partitions.values()
        if isinstance(record, dict)
        and record.get("status") == "PASS"
        and record.get("relative_path")
    }
    actual = {
        path.relative_to(dataset_root).as_posix()
        for path in dataset_root.rglob("*.parquet")
    } if dataset_root.exists() else set()
    files_by_partition: dict[str, list[str]] = {}
    for relative in sorted(actual):
        key = str(Path(relative).parent).replace("\\", "/")
        files_by_partition.setdefault(key, []).append(relative)
    duplicate_partition_files = sorted(
        key for key, files in files_by_partition.items() if len(files) > 1
    )
    pass_empty_conflicts = sorted(
        key
        for key, record in partitions.items()
        if isinstance(record, dict)
        and record.get("status") == "PASS_EMPTY"
        and files_by_partition.get(key)
    )
    return {
        "extra_unregistered_files": sorted(actual - registered),
        "missing_registered_files": sorted(registered - actual),
        "duplicate_partition_files": duplicate_partition_files,
        "pass_empty_file_conflicts": pass_empty_conflicts,
    }


def _observation_checks(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dataset_root = root / "observations"
    manifest_path = dataset_root / "observation_partition_manifest.json"
    try:
        partition_manifest = _read_json(manifest_path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "status": "FAIL",
            "reason": "OBSERVATION_PARTITION_MANIFEST_MISSING",
            "extra_unregistered_files": [],
            "missing_registered_files": [],
            "duplicate_partition_files": [],
            "pass_empty_file_conflicts": [],
        }
    file_audit = _dataset_file_audit(dataset_root, partition_manifest)
    failures: list[dict[str, Any]] = []
    rows = 0
    pass_empty = 0
    duplicate_ids = 0
    stable_id_errors = 0
    logical_hashes: dict[str, str] = {}
    for key, record in sorted(partition_manifest.get("partitions", {}).items()):
        status = str(record.get("status", ""))
        source = key.split("/", 1)[0].split("=", 1)[-1]
        observation_date = key.rsplit("=", 1)[-1]
        if status == "PASS_EMPTY":
            pass_empty += 1
            if record.get("empty_reason") not in EMPTY_REASONS:
                failures.append({"partition": key, "reason": "PASS_EMPTY_REASON_INVALID"})
            if record.get("schema_fingerprint") != observation_empty_schema_fingerprint(source):
                failures.append({"partition": key, "reason": "PASS_EMPTY_SCHEMA_MISMATCH"})
            if int(record.get("row_count", -1)) != 0 or record.get("relative_path"):
                failures.append({"partition": key, "reason": "PASS_EMPTY_RECORD_INVALID"})
            logical_hashes[key] = object_hash(record)
            continue
        if status != "PASS":
            failures.append({"partition": key, "reason": f"PARTITION_STATUS_{status or 'MISSING'}"})
            continue
        relative = record.get("relative_path")
        path = dataset_root / str(relative or "")
        if not relative or not path.exists():
            failures.append({"partition": key, "reason": "FILE_MISSING"})
            continue
        try:
            columns, metadata_rows, fingerprint = _parquet_metadata(path)
            missing = sorted(set(VALIDATION_COLUMNS) - set(columns))
            if missing:
                failures.append({"partition": key, "reason": "COLUMNS_MISSING", "columns": missing})
                continue
            frame = pd.read_parquet(path, columns=VALIDATION_COLUMNS)
        except Exception as exc:
            failures.append({"partition": key, "reason": f"READ_FAIL:{type(exc).__name__}"})
            continue
        rows += metadata_rows
        logical_hashes[key] = sha256_file(path)
        duplicate_ids += int(frame["observation_id"].duplicated().sum())
        expected_ids = [
            stable_id(source, source_record_id)
            for source_record_id in frame["source_record_id"]
        ]
        stable_id_errors += int(
            frame["observation_id"].astype("string").ne(
                pd.Series(expected_ids, index=frame.index, dtype="string")
            ).sum()
        )
        if logical_hashes[key] != record.get("file_hash"):
            failures.append({"partition": key, "reason": "FILE_HASH_MISMATCH"})
        if fingerprint != record.get("schema_fingerprint"):
            failures.append({"partition": key, "reason": "SCHEMA_FINGERPRINT_MISMATCH"})
        if metadata_rows != int(record.get("row_count", -1)):
            failures.append({"partition": key, "reason": "ROW_COUNT_MISMATCH"})
        if not frame["source"].astype("string").eq(source).all():
            failures.append({"partition": key, "reason": "SOURCE_IDENTITY_MISMATCH"})
        if not frame["observation_date"].astype("string").eq(observation_date).all():
            failures.append({"partition": key, "reason": "DATE_IDENTITY_MISMATCH"})
        event_dates = pd.to_datetime(
            frame["event_time"], utc=True, errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        if not event_dates.eq(observation_date).all():
            failures.append({"partition": key, "reason": "EVENT_DATE_IDENTITY_MISMATCH"})
        validation = validate_observations(frame)
        if validation.get("status") != "PASS":
            failures.append(
                {"partition": key, "reason": "PARTITION_VALIDATION_FAIL", "detail": validation}
            )
    if duplicate_ids or stable_id_errors:
        failures.append(
            {
                "reason": "OBSERVATION_KEY_VALIDATION_FAILED",
                "duplicate_observation_ids": duplicate_ids,
                "stable_id_errors": stable_id_errors,
            }
        )
    expected_rows = int(manifest.get("row_counts", {}).get("observations", rows))
    if rows != expected_rows:
        failures.append({"reason": "ROW_COUNT_MISMATCH", "expected": expected_rows, "actual": rows})
    if any(file_audit.values()):
        failures.append({"reason": "DATASET_FILE_AUDIT_FAILED"})
    partitions = len(partition_manifest.get("partitions", {}))
    return {
        "status": "PASS" if not failures else "FAIL",
        "partitions": partitions,
        "partition_count": partitions,
        "pass_empty_count": pass_empty,
        "observation_rows": rows,
        "rows": rows,
        "duplicate_observation_ids": duplicate_ids,
        "stable_id_errors": stable_id_errors,
        "failures": failures,
        "dataset_hash": object_hash(logical_hashes),
        "partition_manifest_hash": sha256_file(manifest_path),
        **file_audit,
    }


def _membership_checks(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    dataset_root = root / "observation_membership"
    manifest_path = dataset_root / MEMBERSHIP_PARTITION_MANIFEST_NAME
    try:
        partition_manifest = _read_json(manifest_path)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "status": "FAIL",
            "reason": "MEMBERSHIP_PARTITION_MANIFEST_MISSING",
            "membership_rows": 0,
            "partition_count": 0,
            "pass_empty": 0,
            "extra_unregistered_files": [],
            "missing_registered_files": [],
            "duplicate_partition_files": [],
            "pass_empty_file_conflicts": [],
        }
    file_audit = _dataset_file_audit(dataset_root, partition_manifest)
    try:
        observation_manifest = _read_json(
            root / "observations" / "observation_partition_manifest.json"
        )
    except (FileNotFoundError, json.JSONDecodeError):
        observation_manifest = {"partitions": {}}
    failures: list[dict[str, Any]] = []
    rows = 0
    pass_empty = 0
    duplicate_membership_ids = 0
    duplicate_relations = 0
    stable_id_errors = 0
    logical: dict[str, dict[str, Any]] = {}
    for key, record in sorted(partition_manifest.get("partitions", {}).items()):
        status = str(record.get("status", ""))
        source = key.split("/", 1)[0].split("=", 1)[-1]
        observation_date = key.rsplit("=", 1)[-1]
        if status == "PASS_EMPTY":
            pass_empty += 1
            if record.get("empty_reason") not in EMPTY_REASONS:
                failures.append({"partition": key, "reason": "PASS_EMPTY_REASON_INVALID"})
            if record.get("schema_fingerprint") != membership_empty_schema_fingerprint(source):
                failures.append({"partition": key, "reason": "PASS_EMPTY_SCHEMA_MISMATCH"})
            if int(record.get("row_count", -1)) != 0 or record.get("relative_path"):
                failures.append({"partition": key, "reason": "PASS_EMPTY_RECORD_INVALID"})
        elif status == "PASS":
            relative = record.get("relative_path")
            path = dataset_root / str(relative or "")
            if not relative or not path.exists():
                failures.append({"partition": key, "reason": "FILE_MISSING"})
                continue
            try:
                columns, metadata_rows, fingerprint = _parquet_metadata(path)
                missing = sorted(set(MEMBERSHIP_COLUMNS) - set(columns))
                if missing:
                    failures.append({"partition": key, "reason": "COLUMNS_MISSING", "columns": missing})
                    continue
                frame = pd.read_parquet(path, columns=MEMBERSHIP_COLUMNS)
            except Exception as exc:
                failures.append({"partition": key, "reason": f"READ_FAIL:{type(exc).__name__}"})
                continue
            rows += metadata_rows
            duplicate_membership_ids += int(frame["membership_id"].duplicated().sum())
            duplicate_relations += int(
                frame.duplicated(
                    ["chain_episode_id", "observation_id", "interval_type"]
                ).sum()
            )
            expected_ids = [
                stable_id(chain, observation, interval)
                for chain, observation, interval in frame[
                    ["chain_episode_id", "observation_id", "interval_type"]
                ].itertuples(index=False, name=None)
            ]
            stable_id_errors += int(
                frame["membership_id"].astype("string").ne(pd.Series(expected_ids, index=frame.index)).sum()
            )
            validation = validate_observation_membership(frame)
            if validation["status"] != "PASS":
                failures.append({"partition": key, "reason": "PARTITION_VALIDATION_FAIL", "detail": validation})
            if sha256_file(path) != record.get("file_hash"):
                failures.append({"partition": key, "reason": "FILE_HASH_MISMATCH"})
            if fingerprint != record.get("schema_fingerprint"):
                failures.append({"partition": key, "reason": "SCHEMA_FINGERPRINT_MISMATCH"})
            if metadata_rows != int(record.get("row_count", -1)):
                failures.append({"partition": key, "reason": "ROW_COUNT_MISMATCH"})
            if not frame["source"].astype("string").eq(source).all():
                failures.append({"partition": key, "reason": "SOURCE_IDENTITY_MISMATCH"})
            observation_record = observation_manifest.get("partitions", {}).get(key, {})
            observation_relative = observation_record.get("relative_path")
            observation_path = root / "observations" / str(observation_relative or "")
            if observation_record.get("status") == "PASS" and observation_path.exists():
                observation_ids = set(
                    pd.read_parquet(observation_path, columns=["observation_id"])[
                        "observation_id"
                    ].astype(str)
                )
                missing_observations = int(
                    (~frame["observation_id"].astype(str).isin(observation_ids)).sum()
                )
                if missing_observations:
                    failures.append(
                        {
                            "partition": key,
                            "reason": "OBSERVATION_PARTITION_IDENTITY_MISMATCH",
                            "count": missing_observations,
                        }
                    )
            elif metadata_rows:
                failures.append({"partition": key, "reason": "OBSERVATION_PARTITION_FILE_MISSING"})
        else:
            failures.append({"partition": key, "reason": f"PARTITION_STATUS_{status or 'MISSING'}"})
        logical[key] = {
            field: record.get(field)
            for field in (
                "status", "row_count", "relative_path", "file_hash",
                "schema_fingerprint", "empty_reason", "source", "observation_date",
            )
        }
    if duplicate_membership_ids or duplicate_relations or stable_id_errors:
        failures.append(
            {
                "reason": "MEMBERSHIP_KEY_VALIDATION_FAILED",
                "duplicate_membership_ids": duplicate_membership_ids,
                "duplicate_relations": duplicate_relations,
                "stable_id_errors": stable_id_errors,
            }
        )
    if any(file_audit.values()):
        failures.append({"reason": "DATASET_FILE_AUDIT_FAILED"})
    expected_rows = int(manifest.get("membership_row_count", rows))
    if rows != expected_rows:
        failures.append({"reason": "ROW_COUNT_MISMATCH", "expected": expected_rows, "actual": rows})
    expected_partitions = int(manifest.get("membership_partition_count", len(logical)))
    if len(logical) != expected_partitions:
        failures.append(
            {"reason": "PARTITION_COUNT_MISMATCH", "expected": expected_partitions, "actual": len(logical)}
        )
    dataset_hash = object_hash(logical)
    if manifest.get("membership_dataset_hash") != dataset_hash:
        failures.append({"reason": "MEMBERSHIP_DATASET_HASH_MISMATCH"})
    manifest_hash = sha256_file(manifest_path)
    if manifest.get("membership_partition_manifest_hash") != manifest_hash:
        failures.append({"reason": "MEMBERSHIP_PARTITION_MANIFEST_HASH_MISMATCH"})
    return {
        "status": "PASS" if not failures else "FAIL",
        "membership_rows": rows,
        "partition_count": len(logical),
        "pass_empty": pass_empty,
        "duplicate_membership_ids": duplicate_membership_ids,
        "duplicate_relations": duplicate_relations,
        "stable_id_errors": stable_id_errors,
        "dataset_hash": dataset_hash,
        "partition_manifest_hash": manifest_hash,
        "failures": failures,
        **file_audit,
    }


def _eligibility_checks(episodes: pd.DataFrame) -> dict[str, Any]:
    required = {
        "core_eligible", "engineering_eligible",
        "scientific_chain_eligible", "formal_eligible",
    }
    missing = sorted(required - set(episodes.columns))
    if missing:
        return {"status": "FAIL", "missing": missing}
    proxy = episodes["chain_support_level"].eq("OBSERVED_CHAIN_PROXY")
    errors = int(
        (~episodes["core_eligible"].astype(bool).ge(episodes["engineering_eligible"].astype(bool))).sum()
        + (~episodes["formal_eligible"].astype(bool).eq(episodes["engineering_eligible"].astype(bool))).sum()
        + (proxy & episodes["scientific_chain_eligible"].astype(bool)).sum()
    )
    return {
        "status": "PASS" if errors == 0 else "FAIL",
        "errors": errors,
        "observed_proxy_rows": int(proxy.sum()),
    }


def _leakage_checks(tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    events = tables.get("events", pd.DataFrame())
    episodes = tables.get("episodes", pd.DataFrame())
    evidence = tables.get("evidence_audit", pd.DataFrame())
    unsupported_event_nonnull = int(
        (
            events.get("support_level", pd.Series(dtype="string")).eq("UNSUPPORTED")
            & events.get("event_time", pd.Series(dtype="datetime64[ns]")).notna()
        ).sum()
    ) if not events.empty else 0
    unsupported_label_nonnull = 0
    target_identity_errors = 0
    if not episodes.empty:
        unsupported = episodes.get(
            "label_missing_reason", pd.Series("", index=episodes.index)
        ).ne("")
        unsupported_label_nonnull = int(
            episodes.loc[unsupported, ["y_ob", "y_tx", "y_to"]]
            .notna().any(axis=1).sum()
        )
        supported = episodes[["y_ob", "y_tx", "y_to"]].notna().all(axis=1)
        if supported.any():
            target_identity_errors = int(
                (~episodes.loc[supported, "y_to"].eq(
                    episodes.loc[supported, "y_ob"]
                    + episodes.loc[supported, "y_tx"]
                )).sum()
            )
    future_evidence = int(
        evidence.get(
            "future_information_used", pd.Series(dtype="boolean")
        ).fillna(False).astype(bool).sum()
    ) if not evidence.empty else 0
    evidence_missing_hash = int(
        evidence.get("source_hash", pd.Series(dtype="string"))
        .fillna("").astype(str).str.len().eq(0).sum()
    ) if not evidence.empty else 0
    errors = (
        unsupported_event_nonnull + unsupported_label_nonnull
        + target_identity_errors + future_evidence + evidence_missing_hash
    )
    return {
        "status": "PASS" if errors == 0 else "FAIL",
        "unsupported_event_nonnull": unsupported_event_nonnull,
        "unsupported_label_nonnull": unsupported_label_nonnull,
        "target_identity_errors": target_identity_errors,
        "future_information_used": future_evidence,
        "evidence_missing_source_hash": evidence_missing_hash,
    }


def validate_existing_bundle(
    root: Path,
    cfg: dict[str, Any],
    *,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        manifest = _read_json(root / "pre_manifest.json")
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL", "reason": "MANIFEST_UNREADABLE", "detail": str(exc)}
        if write_report:
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "reports" / "core_validation_recomputed.json").write_text(
                json.dumps(result, indent=2, default=str), encoding="utf-8"
            )
        return result

    required_manifest = set(cfg["core_schema"].get("manifest_required", []))
    missing_manifest = sorted(required_manifest - set(manifest))
    checks["manifest_required_fields"] = {
        "status": "PASS" if not missing_manifest else "FAIL",
        "missing": missing_manifest,
    }
    if missing_manifest:
        failures.append("manifest_required_fields")
    identity_failures = [
        field
        for field, expected in {
            "contract_id": CONTRACT_ID,
            "schema_version": SCHEMA_VERSION,
            "research_code_revision": RESEARCH_CODE_REVISION,
        }.items()
        if manifest.get(field) != expected
    ]
    checks["contract_identity"] = {
        "status": "PASS" if not identity_failures else "FAIL",
        "failures": identity_failures,
    }
    if identity_failures:
        failures.append("contract_identity")
    expected_contract_hashes = contract_hashes(cfg)
    contract_hash_failures = [
        name for name, expected in expected_contract_hashes.items()
        if manifest.get(name) != expected
    ]
    hard_hashes = {
        "core_schema_hash": schema_hash(cfg),
        "frozen_config_hash": frozen_config_hash(cfg),
        "source_schema_hash": object_hash(cfg.get("sources", {})),
    }
    contract_hash_failures.extend(
        name for name, expected in hard_hashes.items() if manifest.get(name) != expected
    )
    current_implementation = implementation_hash(cfg.get("project_root"))
    current_git = git_metadata(cfg.get("project_root"))
    provenance_warnings = []
    if manifest.get("implementation_hash") != current_implementation.get("hash"):
        provenance_warnings.append("IMPLEMENTATION_HASH_CHANGED_WARNING")
    if manifest.get("git_commit") != current_git.get("git_commit"):
        provenance_warnings.append("GIT_COMMIT_CHANGED_WARNING")
    if bool(manifest.get("git_dirty")) != bool(current_git.get("git_dirty")):
        provenance_warnings.append("GIT_DIRTY_STATUS_CHANGED_WARNING")
    checks["contract_hashes"] = {
        "status": "PASS" if not contract_hash_failures else "FAIL",
        "failures": sorted(set(contract_hash_failures)),
        "provenance_warnings": provenance_warnings,
    }
    if contract_hash_failures:
        failures.append("contract_hashes")

    table_failures, tables = _schema_and_keys(root, cfg)
    checks["table_schemas_and_keys"] = {
        "status": "PASS" if not table_failures else "FAIL",
        "failures": table_failures,
    }
    if table_failures:
        failures.append("table_schemas_and_keys")
    byte_hash_failures = []
    for name, expected_hash in manifest.get("file_hashes", {}).items():
        special = {
            "column_registry": root / "column_registry.yaml",
            "observation_partition_manifest": root / "observations" / "observation_partition_manifest.json",
            "membership_partition_manifest": root / "observation_membership" / MEMBERSHIP_PARTITION_MANIFEST_NAME,
        }
        path = special.get(name, root / f"{name}.parquet")
        if not path.exists() or sha256_file(path) != expected_hash:
            byte_hash_failures.append(name)
    checks["file_hashes"] = {
        "status": "PASS" if not byte_hash_failures else "FAIL",
        "failures": byte_hash_failures,
    }
    if byte_hash_failures:
        failures.append("file_hashes")

    checks["observations"] = _observation_checks(root, manifest)
    checks["membership_uniqueness"] = _membership_checks(root, manifest)
    if checks["observations"]["status"] != "PASS":
        failures.append("observations")
    if checks["membership_uniqueness"]["status"] != "PASS":
        failures.append("membership_uniqueness")

    if "events" in tables:
        checks["event_contract"] = validate_events(tables["events"])
        if checks["event_contract"].get("status") != "PASS":
            failures.append("event_contract")
    if "episodes" in tables:
        checks["chain_contract"] = validate_chains(tables["episodes"])
        checks["eligibility_semantics"] = _eligibility_checks(tables["episodes"])
        if checks["chain_contract"].get("status") != "PASS":
            failures.append("chain_contract")
        if checks["eligibility_semantics"].get("status") != "PASS":
            failures.append("eligibility_semantics")
    if "calibration" in tables:
        calibration = tables["calibration"]
        checks["reference_train_only"] = {
            "status": "PASS"
            if calibration["fit_split"].eq("train").all()
            and not pd.to_datetime(calibration["fit_end_time"], utc=True).gt(
                pd.Timestamp(cfg["splits"]["train"][1], tz="UTC")
            ).any()
            else "FAIL"
        }
        if checks["reference_train_only"]["status"] != "PASS":
            failures.append("reference_train_only")

    registry: list[dict[str, Any]] = []
    registry_path = root / "column_registry.yaml"
    if registry_path.exists():
        registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")).get("columns", [])
        checks["column_registry"] = validate_column_registry(registry, cfg)
        if checks["column_registry"].get("status") != "PASS":
            failures.append("column_registry")
    else:
        checks["column_registry"] = {"status": "FAIL", "reason": "FILE_MISSING"}
        failures.append("column_registry")

    checks["leakage"] = _leakage_checks(tables)
    if checks["leakage"]["status"] != "PASS":
        failures.append("leakage")
    logical_hash_failures = []
    for name, expected_hash in manifest.get("artifact_hashes", {}).items():
        if name in {"observations", "observation_membership"}:
            continue
        if name in tables and dataframe_hash(
            tables[name], list(cfg["core_schema"]["tables"].get(name, {}).get("key", []))
        ) != expected_hash:
            logical_hash_failures.append(name)
    checks["logical_table_hashes"] = {
        "status": "PASS" if not logical_hash_failures else "FAIL",
        "failures": logical_hash_failures,
    }
    if logical_hash_failures:
        failures.append("logical_table_hashes")

    recomputed_statistics = core_statistics(
        tables, checks["observations"], checks["membership_uniqueness"], registry
    )
    stored_path = root / "reports" / "core_validation.json"
    stored = _read_json(stored_path) if stored_path.exists() else {}
    stored_statistics = stored.get("statistics", {})
    statistics_mismatches = {
        key: {"stored": stored_statistics.get(key), "recomputed": value}
        for key, value in recomputed_statistics.items()
        if stored_statistics.get(key) != value
    }
    checks["statistics_recomputation"] = {
        "status": "PASS" if not statistics_mismatches else "FAIL",
        "stored": stored_statistics,
        "recomputed": recomputed_statistics,
        "mismatches": statistics_mismatches,
    }
    if statistics_mismatches:
        failures.append("statistics_recomputation")

    component_mapping = {
        "tables": "table_schemas_and_keys",
        "events": "event_contract",
        "chains": "chain_contract",
        "observations": "observations",
        "references": "reference_train_only",
        "leakage": "leakage",
        "column_registry": "column_registry",
        "membership": "membership_uniqueness",
    }
    component_mismatch = bool(stored) and stored.get("status") != (
        "PASS" if not failures else "FAIL"
    )
    for stored_name, recomputed_name in component_mapping.items():
        if stored_name in stored and recomputed_name in checks:
            component_mismatch = component_mismatch or (
                stored[stored_name].get("status")
                != checks[recomputed_name].get("status")
            )
    if component_mismatch:
        failures.append("stored_validation_mismatch")

    result = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": sorted(set(failures)),
        "extra_unregistered_files": {
            "observations": checks["observations"]["extra_unregistered_files"],
            "observation_membership": checks["membership_uniqueness"]["extra_unregistered_files"],
        },
        "missing_registered_files": {
            "observations": checks["observations"]["missing_registered_files"],
            "observation_membership": checks["membership_uniqueness"]["missing_registered_files"],
        },
        "duplicate_partition_files": {
            "observations": checks["observations"]["duplicate_partition_files"],
            "observation_membership": checks["membership_uniqueness"]["duplicate_partition_files"],
        },
        "pass_empty_file_conflicts": {
            "observations": checks["observations"]["pass_empty_file_conflicts"],
            "observation_membership": checks["membership_uniqueness"]["pass_empty_file_conflicts"],
        },
    }
    if statistics_mismatches:
        result["reason"] = "STORED_AND_RECOMPUTED_STATISTICS_MISMATCH"
    elif component_mismatch:
        result["reason"] = "STORED_AND_RECOMPUTED_VALIDATION_MISMATCH"
    if write_report:
        reports = root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "core_validation_recomputed.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
    return result
