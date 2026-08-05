from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..input import load_aircraft, load_airports, load_eurostat, load_metar, object_hash
from ..inventory import complete_state_dates, state_coverage_calendar
from ..progress import stage_message
from .chain_builder import build_chains
from .column_registry import build_column_registry
from .contracts import (
    CONTRACT_ID,
    SCHEMA_VERSION,
    contract_hashes,
    core_output_root,
    implementation_hash,
    schema_hash,
)
from .event_builder import build_events
from .evidence_builder import build_evidence_audit
from .observation_dataset import write_observation_dataset
from .inventory_reuse import load_verified_inventory
from .observation_requests import build_observation_requests
from .reference_builder import build_references
from .report import build_run_report
from .source_loader import load_core_flights
from .state_cache import prepare_state_cache
from .validation import build_readiness, validate_core
from .writer import begin_staging, dataframe_hash, publish_staging, write_core_metadata, write_core_tables


@dataclass(frozen=True)
class CoreBuildResult:
    output_root: Path
    manifest: dict[str, Any]
    validation: dict[str, Any]
    readiness: dict[str, Any]
    publication_status: str


def _source_hashes(raw_inventory: pd.DataFrame) -> dict[str, str]:
    return {
        str(Path(row.absolute_path).resolve()): str(row.sha256)
        for row in raw_inventory.itertuples(index=False)
        if bool(row.readable)
    }


def _selected_dates(
    cfg: dict[str, Any], available_dates: set[pd.Timestamp]
) -> set[pd.Timestamp]:
    manifest_value = cfg.get("runtime", {}).get("adapt_manifest_path")
    if not manifest_value:
        return available_dates
    manifest_path = Path(manifest_value)
    if not manifest_path.is_absolute():
        manifest_path = (cfg["project_root"] / manifest_path).resolve()
    requested = {
        pd.Timestamp(value).normalize()
        for value in pd.read_csv(manifest_path)["anchor_date"]
    }
    smoke = bool(cfg.get("runtime", {}).get("smoke_subset", False))
    mismatch = not requested.issubset(available_dates) if smoke else requested != available_dates
    if mismatch:
        missing = sorted(str(value.date()) for value in requested - available_dates)
        extra = sorted(str(value.date()) for value in available_dates - requested)
        raise ValueError(f"CORE_ADAPT_MANIFEST_MISMATCH:missing={missing};unregistered={extra}")
    cfg["core_adapt_manifest_path"] = manifest_path
    return requested


def _merge_aircraft(flights: pd.DataFrame, aircraft: pd.DataFrame) -> pd.DataFrame:
    if aircraft.empty:
        return flights
    metadata = aircraft[[column for column in ["icao24", "typecode", "registration"] if column in aircraft]].drop_duplicates("icao24")
    output = flights.merge(metadata, on="icao24", how="left", suffixes=("", "_metadata"))
    for column in ["typecode", "registration"]:
        other = f"{column}_metadata"
        if other in output:
            if column not in output:
                output[column] = output[other]
            else:
                output[column] = output[column].fillna(output[other])
            output = output.drop(columns=other)
    return output


def _manifest(
    cfg: dict[str, Any],
    raw_inventory: pd.DataFrame,
    registry_hash: str,
    table_hashes: dict[str, str],
    observation_hash: str,
    row_counts: dict[str, int],
    partition_counts: dict[str, Any],
) -> dict[str, Any]:
    artifact_hashes = {**table_hashes, "observations": observation_hash}
    source_records = raw_inventory[["source", "relative_path", "sha256", "size_bytes"]].astype(str).to_dict("records")
    return {
        "contract_id": CONTRACT_ID,
        "schema_version": SCHEMA_VERSION,
        "source_manifest_hash": object_hash(source_records),
        "source_schema_hash": object_hash(cfg["sources"]),
        "column_registry_hash": registry_hash,
        **contract_hashes(cfg),
        "pre_code_hash": implementation_hash(),
        "created_at": str(pd.Timestamp.now(tz="UTC")),
        "mode": cfg["mode"],
        "row_counts": row_counts,
        "partition_counts": partition_counts,
        "artifact_hashes": artifact_hashes,
        "core_data_hash": object_hash(artifact_hashes),
        "core_schema_hash": schema_hash(cfg),
    }


def build_core(
    cfg: dict[str, Any], output_override: str | Path | None = None
) -> CoreBuildResult:
    output = core_output_root(cfg, output_override)
    staging = begin_staging(output, resume=True)
    stage_message("[Core 1/7] Inventory and source normalization", level=cfg["runtime"]["progress_level"])
    raw_inventory, inventory_status = load_verified_inventory(cfg)
    coverage = state_coverage_calendar(raw_inventory, cfg)
    dates = _selected_dates(cfg, complete_state_dates(coverage, cfg))
    cfg["raw_hashes"] = _source_hashes(raw_inventory)
    flights = _merge_aircraft(load_core_flights(cfg, dates), load_aircraft(cfg))
    airports = load_airports(cfg)
    metar = load_metar(cfg)
    passengers = load_eurostat(cfg, "eurostat_passengers")
    commercial = load_eurostat(cfg, "eurostat_flights")

    stage_message("[Core 2/7] Events and chain episodes", level=cfg["runtime"]["progress_level"])
    episodes = build_chains(flights, cfg)
    events = build_events(flights, episodes, cfg)
    requests = build_observation_requests(episodes, cfg)
    if requests.empty:
        raise ValueError("CORE_OBSERVATION_REQUESTS_EMPTY")

    stage_message("[Core 3/7] Contract-hashed state cache", level=cfg["runtime"]["progress_level"])
    state_store, extraction, cache_manifest = prepare_state_cache(
        cfg, requests, airports, coverage
    )
    cache_manifest["inventory_status"] = inventory_status
    stage_message("[Core 4/7] Native observation partitions", level=cfg["runtime"]["progress_level"])
    observation_result = write_observation_dataset(
        staging / "observations",
        requests,
        state_store,
        metar,
        raw_inventory,
        cfg["runtime"]["progress_level"],
    )

    stage_message("[Core 5/7] Train-only references and evidence", level=cfg["runtime"]["progress_level"])
    calibration = build_references(
        episodes, flights, staging / "observations", passengers, commercial, cfg
    )
    evidence = build_evidence_audit(
        events, episodes, calibration, observation_result.evidence_rows
    )
    tables = {
        "episodes": episodes,
        "events": events,
        "calibration": calibration,
        "evidence_audit": evidence,
    }
    registry = build_column_registry(tables, cfg)

    stage_message("[Core 6/7] Validate and freeze hashes", level=cfg["runtime"]["progress_level"])
    validation = validate_core(tables, observation_result.validation, registry, cfg)
    readiness = build_readiness(validation, episodes)
    if validation["status"] != "PASS":
        raise ValueError("PRE_CORE_VALIDATION_FAILED=" + json.dumps(validation, default=str))
    table_hashes = write_core_tables(staging, tables, registry, cfg["core_schema"])
    row_counts = {name: len(frame) for name, frame in tables.items()}
    row_counts["observations"] = sum(observation_result.row_counts.values())
    manifest = _manifest(
        cfg,
        raw_inventory,
        table_hashes["column_registry"],
        table_hashes,
        observation_result.content_hash,
        row_counts,
        {"observations": observation_result.partition_counts},
    )
    report = build_run_report(manifest, validation, readiness, cache_manifest)
    write_core_metadata(
        staging, manifest, validation, readiness, cache_manifest, extraction, report
    )

    stage_message("[Core 7/7] Publish", level=cfg["runtime"]["progress_level"])
    publication = publish_staging(staging, output, manifest["core_data_hash"])
    return CoreBuildResult(output, manifest, validation, readiness, publication)


def _read_existing(cfg: dict[str, Any], output_override: str | Path | None = None):
    root = core_output_root(cfg, output_override)
    manifest = json.loads((root / "pre_manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((root / "reports" / "core_validation.json").read_text(encoding="utf-8"))
    readiness = json.loads((root / "reports" / "core_readiness.json").read_text(encoding="utf-8"))
    return root, manifest, validation, readiness


def core_validate_existing(cfg: dict[str, Any], output_override: str | Path | None = None) -> dict[str, Any]:
    _, manifest, validation, _ = _read_existing(cfg, output_override)
    return {"manifest_core_data_hash": manifest["core_data_hash"], **validation}


def core_readiness_existing(cfg: dict[str, Any], output_override: str | Path | None = None) -> dict[str, Any]:
    _, _, _, readiness = _read_existing(cfg, output_override)
    return readiness


def core_report_existing(cfg: dict[str, Any], output_override: str | Path | None = None) -> str:
    root, _, _, _ = _read_existing(cfg, output_override)
    return (root / "reports" / "PRE_CORE_RUN_REPORT.md").read_text(encoding="utf-8")
