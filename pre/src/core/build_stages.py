from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..input import (
    load_aircraft,
    load_airports,
    load_eurostat,
    load_metar,
    write_parquet,
)
from ..inventory import complete_state_dates, state_coverage_calendar
from ..progress import stage_message
from .build_context import BuildContext
from .chain_builder import build_chains
from .column_registry import build_column_registry
from .event_builder import build_events
from .evidence_builder import build_evidence_audit
from .finalization import finalize_and_publish
from .inventory_reuse import load_verified_inventory
from .membership import MEMBERSHIP_COLUMNS, write_membership_dataset
from .observations import write_observation_dataset
from .observation_requests import build_observation_requests
from .reference_builder import build_references
from .resume_contract import build_resume_contract, write_resume_manifest
from .source_loader import load_core_flights
from .state_cache import prepare_state_cache
from .validation import build_readiness, validate_core
from .writer import begin_staging


def _selected_dates(
    cfg: dict, available_dates: set[pd.Timestamp]
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
    mismatch = (
        not requested.issubset(available_dates)
        if smoke
        else requested != available_dates
    )
    if mismatch:
        missing = sorted(str(value.date()) for value in requested - available_dates)
        extra = sorted(str(value.date()) for value in available_dates - requested)
        raise ValueError(
            f"CORE_ADAPT_MANIFEST_MISMATCH:missing={missing};unregistered={extra}"
        )
    cfg["core_adapt_manifest_path"] = manifest_path
    return requested


def _merge_aircraft(
    flights: pd.DataFrame, aircraft: pd.DataFrame
) -> pd.DataFrame:
    if aircraft.empty:
        return flights
    columns = [
        column
        for column in ["icao24", "typecode", "registration"]
        if column in aircraft
    ]
    metadata = aircraft[columns].drop_duplicates("icao24")
    output = flights.merge(metadata, on="icao24", how="left", suffixes=("", "_metadata"))
    for column in ["typecode", "registration"]:
        other = f"{column}_metadata"
        if other in output:
            output[column] = (
                output[other]
                if column not in output
                else output[column].fillna(output[other])
            )
            output = output.drop(columns=other)
    return output


def inventory(context: BuildContext) -> None:
    cfg = context.cfg
    stage_message("[Core 1/8] Inventory and source normalization", level=cfg["runtime"]["progress_level"])
    context.raw_inventory, context.inventory_status = load_verified_inventory(cfg)
    context.coverage = state_coverage_calendar(context.raw_inventory, cfg)
    dates = _selected_dates(cfg, complete_state_dates(context.coverage, cfg))
    cfg["raw_hashes"] = {
        str(Path(row.absolute_path).resolve()): str(row.sha256)
        for row in context.raw_inventory.itertuples(index=False)
        if bool(row.readable)
    }
    context.flights = _merge_aircraft(
        load_core_flights(cfg, dates), load_aircraft(cfg)
    )
    context.airports = load_airports(cfg)
    context.metar = load_metar(cfg)
    context.passengers = load_eurostat(cfg, "eurostat_passengers")
    context.commercial = load_eurostat(cfg, "eurostat_flights")


def events_and_chains(context: BuildContext) -> None:
    cfg = context.cfg
    stage_message("[Core 2/8] Events and chain episodes", level=cfg["runtime"]["progress_level"])
    context.episodes = build_chains(context.flights, cfg)
    context.events = build_events(context.flights, context.episodes, cfg)


def requests_and_resume_identity(context: BuildContext) -> None:
    cfg = context.cfg
    stage_message("[Core 3/8] Requests, cache, and Resume identity", level=cfg["runtime"]["progress_level"])
    context.requests = build_observation_requests(context.episodes, cfg)
    if context.requests.empty:
        raise ValueError("CORE_OBSERVATION_REQUESTS_EMPTY")
    context.state_store, context.extraction, context.cache_manifest = prepare_state_cache(
        cfg, context.requests, context.airports, context.coverage
    )
    context.cache_manifest["inventory_status"] = context.inventory_status
    context.resume_contract = build_resume_contract(
        cfg,
        context.raw_inventory,
        context.requests,
        cache_key=str(context.cache_manifest.get("base_cache_key", "")),
    )
    context.staging = begin_staging(
        context.output,
        resume=True,
        resume_contract=context.resume_contract,
        audit_root=context.output.parent / "reports",
    )
    write_resume_manifest(context.staging, context.resume_contract)


def observations(context: BuildContext) -> None:
    assert context.staging is not None and context.resume_contract is not None
    cfg = context.cfg
    stage_message("[Core 4/8] Native observation partitions", level=cfg["runtime"]["progress_level"])
    context.observation_result = write_observation_dataset(
        context.staging / "observations",
        context.requests,
        context.state_store,
        context.metar,
        context.raw_inventory,
        cfg["runtime"]["progress_level"],
        resume_contract=context.resume_contract,
    )


def membership(context: BuildContext) -> None:
    assert context.staging is not None and context.resume_contract is not None
    cfg = context.cfg
    stage_message("[Core 5/8] Partitioned observation Membership", level=cfg["runtime"]["progress_level"])
    context.membership_result = write_membership_dataset(
        context.staging / "observation_membership",
        context.staging / "observations",
        context.requests,
        cfg,
        cfg["runtime"]["progress_level"],
        resume_contract=context.resume_contract,
    )


def references_and_evidence(context: BuildContext) -> None:
    assert context.staging is not None
    cfg = context.cfg
    stage_message("[Core 6/8] Train-only references and evidence", level=cfg["runtime"]["progress_level"])
    context.calibration = build_references(
        context.episodes,
        context.flights,
        context.staging / "observations",
        context.passengers,
        context.commercial,
        cfg,
        context.staging / "observation_membership",
    )
    context.evidence = build_evidence_audit(
        context.events,
        context.episodes,
        context.calibration,
        context.observation_result.evidence_rows,
    )
    context.tables = {
        "episodes": context.episodes,
        "events": context.events,
        "calibration": context.calibration,
        "evidence_audit": context.evidence,
    }
    context.registry = build_column_registry(
        {
            **context.tables,
            "observation_membership": pd.DataFrame(columns=MEMBERSHIP_COLUMNS),
        },
        cfg,
        raw_inventory=context.raw_inventory,
        source_columns=context.observation_result.source_columns,
    )


def validation(context: BuildContext) -> None:
    assert context.staging is not None
    cfg = context.cfg
    stage_message("[Core 7/8] Independent validation", level=cfg["runtime"]["progress_level"])
    context.validation = validate_core(
        context.tables,
        context.observation_result.validation,
        context.registry,
        cfg,
        membership_validation=context.membership_result.validation,
    )
    context.readiness = build_readiness(context.validation, context.episodes)
    if context.validation["status"] != "PASS":
        raise ValueError(
            "PRE_CORE_VALIDATION_FAILED="
            + json.dumps(context.validation, default=str)
        )
    rejection_audit = context.episodes.attrs.get(
        "candidate_rejections", pd.DataFrame()
    )
    if isinstance(rejection_audit, pd.DataFrame):
        write_parquet(
            rejection_audit,
            context.staging / "reports" / "chain_candidate_rejections.parquet",
        )


def publication(context: BuildContext) -> None:
    stage_message("[Core 8/8] Finalize and publish", level=context.cfg["runtime"]["progress_level"])
    finalize_and_publish(context)
