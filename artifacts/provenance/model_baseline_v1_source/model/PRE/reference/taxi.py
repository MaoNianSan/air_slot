"""Train-frozen empirical taxi-out reference for data1 (trajectory event pairs).

Frozen rule: TAXI_REFERENCE@1.0.0 (user-approved 2026-08-13, D1-9 option A, data1 scope).
Scientific object: empirical taxi-out time reference per origin airport.

Construction rule (data1):
    taxi_out = TRAJECTORY_TAKEOFF.event_time - TRAJECTORY_OUT_BLOCK_PROXY.event_time  [minutes]
    Events must fall inside the flight interval [first_seen_utc, last_seen_utc]
    (D1-7 window rule); latest event per type is the deterministic tie-break;
    strict takeoff > out_block required.
    Fit partition: train rows only -> train-frozen reference (freeze_id).
    Statistic: MEDIAN per origin_airport_id (H3 approval).
    Minimum support: min cell size 50 at every fallback level (H1 approval).
    Fallback hierarchy: AIRPORT_CELL -> GLOBAL (H4 approval).
    Zero-coverage airports (no legal trajectory pair in train) -> ABSTAIN
    (NO_TAXI_TRAJECTORY_EVIDENCE) per approved option A.
    Evidence: EMPIRICAL_REFERENCE from trajectory-derived pairs; out-block is a
    proxy-named detector event (never BTS DIRECT equivalent, D1-3/D1-4 closure),
    so support is DEGRADED with an explicit reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import SupportedValue
from model.PRE.transformation import (
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
)

RULE_ID = "TAXI_REFERENCE"
RULE_VERSION = "1.0.0"
STATISTIC_ID = "MEDIAN"
MINIMUM_SUPPORT_RULE = "MIN_CELL_SIZE_50"
FALLBACK_HIERARCHY = ("AIRPORT_CELL", "GLOBAL")
APPLICABILITY_SCOPE = "ORIGIN_AIRPORT_GROUP"

OUT_BLOCK_EVENT = "TRAJECTORY_OUT_BLOCK_PROXY"
TAKEOFF_EVENT = "TRAJECTORY_TAKEOFF"

_LEVEL_CELL = "AIRPORT_CELL"
_LEVEL_GLOBAL = "GLOBAL"

_REQUIRED_FLIGHT_KEYS = (
    "dataset_instance_id",
    "aircraft_id",
    "flight_id",
    "origin_airport_id",
    "first_seen_utc",
    "last_seen_utc",
    "split",
)


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


@dataclass(frozen=True)
class TaxiReferenceCell:
    airport_id: str
    value_minutes: float
    sample_count: int
    fallback_level: Literal["AIRPORT_CELL", "GLOBAL"]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class TaxiReference:
    reference_id: str
    dataset_instance_id: str
    rule_id: str
    rule_version: str
    fit_period: str
    statistic_id: str
    minimum_support_rule: str
    fallback_hierarchy: tuple[str, ...]
    applicability_scope: str
    global_value_minutes: float
    global_sample_count: int
    cells: tuple[TaxiReferenceCell, ...]
    manifest_freeze_id: str
    support_state: SupportState
    reason_code: str

    def lookup(self, airport_id: str) -> SupportedValue:
        cell = next(
            (item for item in self.cells if item.airport_id == airport_id), None
        )
        if cell is None:
            return SupportedValue(
                value=None,
                unit="minutes",
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
                support_state=SupportState.ABSTAIN,
                reason_code="NO_TAXI_TRAJECTORY_EVIDENCE",
                quality_flags=("REFERENCE_SOURCE_TRAJECTORY_PAIR",),
            )
        if cell.fallback_level == _LEVEL_CELL:
            return SupportedValue(
                value=cell.value_minutes,
                unit="minutes",
                evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
                support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
                support_state=SupportState.DEGRADED,
                reason_code="TRAJECTORY_PAIR_TAXI_REFERENCE;CELL_MEDIAN",
                quality_flags=tuple(
                    sorted(
                        (
                            "REFERENCE_LEVEL_CELL",
                            "REFERENCE_SOURCE_TRAJECTORY_PAIR",
                            f"REFERENCE_CELL_N={cell.sample_count}",
                        )
                    )
                ),
            )
        return SupportedValue(
            value=self.global_value_minutes,
            unit="minutes",
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            support_state=SupportState.DEGRADED,
            reason_code="TRAJECTORY_PAIR_TAXI_REFERENCE;FALLBACK_GLOBAL",
            quality_flags=tuple(
                sorted(
                    (
                        "REFERENCE_LEVEL_GLOBAL",
                        "REFERENCE_SOURCE_TRAJECTORY_PAIR",
                        "REFERENCE_CELL_MIN_SUPPORT_FALLBACK",
                        f"REFERENCE_CELL_N={cell.sample_count}",
                    )
                )
            ),
        )


def _event_id(event: Any) -> str:
    value = _get(event, "canonical_record_id")
    if value:
        return str(value)
    return content_id(
        {
            "event_type": _get(event, "event_type"),
            "event_time": _get(event, "event_time").isoformat(),
            "aircraft_id": _get(event, "aircraft_id"),
        }
    )


def _flight_id(flight: dict[str, Any]) -> str:
    return str(flight.get("canonical_record_id") or flight["flight_id"])


def _taxi_minutes(out_block: Any, takeoff: Any) -> float:
    minutes = (
        _get(takeoff, "event_time") - _get(out_block, "event_time")
    ).total_seconds() / 60.0
    if minutes <= 0:
        raise ContractError("TAXI_PAIR_EVENT_ORDER_INVALID")
    return minutes


def build_taxi_reference(
    flights: list[dict[str, Any]],
    events: list[Any],
    *,
    fit_period: str,
    dataset_instance_id: str = "data1_2019",
    min_cell_size: int = 50,
    statistic_id: str = STATISTIC_ID,
) -> TaxiReference:
    """Fit the data1 train-frozen taxi-out reference from flight rows + events.

    Flights must be FlightRecord-shaped dicts plus a "split" key; events must be
    OperationalEventRecord objects (or equivalent dicts). Only train flights
    contribute; dev/calibration/test rows are excluded before any aggregation.
    """
    for flight in flights:
        for key in _REQUIRED_FLIGHT_KEYS:
            if key not in flight or flight[key] in (None, ""):
                raise ContractError(f"REFERENCE_FLIGHT_MISSING:{key}")
    if {flight["dataset_instance_id"] for flight in flights} != {dataset_instance_id}:
        raise ContractError("REFERENCE_DATASET_MISMATCH")
    for event in events:
        if _get(event, "dataset_instance_id") != dataset_instance_id:
            raise ContractError("REFERENCE_DATASET_MISMATCH")

    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")

    training = [flight for flight in flights if flight["split"] == "train"]
    if not training:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")

    durations: list[tuple[float, str]] = []
    manifest_records: list[dict[str, Any]] = []
    for flight in training:
        aircraft = flight["aircraft_id"]
        start = flight["first_seen_utc"]
        end = flight["last_seen_utc"]
        out_blocks = [
            event
            for event in events
            if _get(event, "event_type") == OUT_BLOCK_EVENT
            and _get(event, "aircraft_id") == aircraft
            and _get(event, "event_time") is not None
            and start <= _get(event, "event_time") <= end
        ]
        takeoffs = [
            event
            for event in events
            if _get(event, "event_type") == TAKEOFF_EVENT
            and _get(event, "aircraft_id") == aircraft
            and _get(event, "event_time") is not None
            and start <= _get(event, "event_time") <= end
        ]
        if not out_blocks or not takeoffs:
            continue
        out_block = max(out_blocks, key=lambda event: _get(event, "event_time"))
        takeoff = max(takeoffs, key=lambda event: _get(event, "event_time"))
        try:
            minutes = _taxi_minutes(out_block, takeoff)
        except ContractError:
            continue
        durations.append((minutes, flight["origin_airport_id"]))
        manifest_records.append(
            {
                "record_id": _flight_id(flight),
                "source_fingerprint": content_id(
                    {"out_block": _event_id(out_block), "takeoff": _event_id(takeoff)}
                ),
                "split": "train",
            }
        )

    if not durations:
        raise ContractError("REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_PAIRS")
    global_value = median(value for value, _airport in durations)
    global_count = len(durations)
    if global_count < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")

    cells: dict[str, list[float]] = {}
    for value, airport in durations:
        cells.setdefault(airport, []).append(value)

    cell_records: list[TaxiReferenceCell] = []
    for airport in sorted(cells):
        cell_values = cells[airport]
        cell_count = len(cell_values)
        if cell_count >= min_cell_size:
            cell_value = median(cell_values)
            level: Literal["AIRPORT_CELL", "GLOBAL"] = _LEVEL_CELL
        else:
            cell_value = global_value
            level = _LEVEL_GLOBAL
        cell_records.append(
            TaxiReferenceCell(
                airport_id=airport,
                value_minutes=cell_value,
                sample_count=cell_count,
                fallback_level=level,
                provenance=(
                    f"airport={airport}",
                    f"n={cell_count}",
                    f"fallback_level={level}",
                    f"{RULE_ID}@{RULE_VERSION}",
                ),
            )
        )

    manifest = build_reference_fit_manifest(
        manifest_records,
        rule=rule,
        fit_period=fit_period,
        grouping_keys=("origin_airport_id",),
        statistic_id=statistic_id,
        minimum_support_rule=f"MIN_CELL_SIZE_{min_cell_size}",
        fallback_hierarchy=FALLBACK_HIERARCHY,
        applicability_scope=APPLICABILITY_SCOPE,
    )

    reference_id = content_id(
        {
            "rule": f"{RULE_ID}@{RULE_VERSION}",
            "dataset_instance_id": dataset_instance_id,
            "fit_period": fit_period,
            "statistic_id": statistic_id,
            "minimum_support_rule": manifest.minimum_support_rule,
            "fallback_hierarchy": FALLBACK_HIERARCHY,
            "global_value_minutes": global_value,
            "global_sample_count": global_count,
            "cells": [
                {
                    "airport_id": item.airport_id,
                    "value_minutes": item.value_minutes,
                    "sample_count": item.sample_count,
                    "fallback_level": item.fallback_level,
                }
                for item in cell_records
            ],
            "freeze_id": manifest.freeze_id,
        }
    )

    return TaxiReference(
        reference_id=reference_id,
        dataset_instance_id=dataset_instance_id,
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        fit_period=fit_period,
        statistic_id=statistic_id,
        minimum_support_rule=manifest.minimum_support_rule,
        fallback_hierarchy=FALLBACK_HIERARCHY,
        applicability_scope=APPLICABILITY_SCOPE,
        global_value_minutes=global_value,
        global_sample_count=global_count,
        cells=tuple(cell_records),
        manifest_freeze_id=manifest.freeze_id,
        support_state=SupportState.DEGRADED,
        reason_code="TRAJECTORY_PAIR_TAXI_REFERENCE",
    )
