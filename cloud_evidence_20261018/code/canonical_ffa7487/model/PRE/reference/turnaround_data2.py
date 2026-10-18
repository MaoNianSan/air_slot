"""Train-frozen DIRECT gate turnaround reference for data2 (BTS 2019).

Frozen rule: DATA2_TURNAROUND_REFERENCE@1.0.0 (user-approved 2026-08-14,
D2-3, data2 scope; "有官方肯定用官方" -> official BTS gate actuals).
Scientific object: empirical turnaround time reference per connection airport.

Construction rule (data2):
    direct_gap = successor.actual_departure_utc - predecessor.actual_arrival_utc
    Chain semantics are inherited from DATA2_SAME_AIRCRAFT_AIRPORT_GAP@1.0.0
    (D2-1): same aircraft (registration), airport continuity, strictly positive
    actual gate gap, gap <= 360 minutes; D2-2 episode anchors on the CRS
    turnaround window [pred.CRSArr, succ.CRSDep] exclude schedule-inverted pairs.
    Fit partition: train rows only (train-frozen reference, reproducible freeze_id).
    Statistic: MEDIAN per connection_airport_id.
    Minimum support: min cell size 50 at every fallback level.
    Fallback hierarchy: AIRPORT_CELL -> GLOBAL.
    Evidence: DIRECT (official BTS DepTime/ArrTime gate actuals), support
    SUPPORTED (unlike the data1 flightlist-proxy basis, which stays DEGRADED).

Lineage: RAW BTS On-Time rows -> OperationalEventRecord (D2-BTS-ACTUAL) ->
EpisodeRecord (DATA2_SAME_AIRCRAFT_AIRPORT_GAP@1.0.0) ->
DATA2_TURNAROUND_REFERENCE@1.0.0 -> turnaround_reference (FROZEN_REFERENCE)
-> M2 (reference), M1 (floor boundary). data1 TURNAROUND_REFERENCE@1.0.0
is untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import SupportedValue
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.transformation import (
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
)

RULE_ID = "DATA2_TURNAROUND_REFERENCE"
RULE_VERSION = "1.0.0"
STATISTIC_ID = "MEDIAN"
MINIMUM_SUPPORT_RULE = "MIN_CELL_SIZE_50"
FALLBACK_HIERARCHY = ("AIRPORT_CELL", "GLOBAL")
APPLICABILITY_SCOPE = "AIRPORT_GROUP"
MAX_GAP_MINUTES = 360  # D2-1 freeze: same bound as the data2 chain rule

_LEVEL_CELL = "AIRPORT_CELL"
_LEVEL_GLOBAL = "GLOBAL"

_REQUIRED_ROW_KEYS = (
    "dataset_instance_id",
    "aircraft_id_namespace",
    "aircraft_id",
    "flight_id",
    "origin_airport_id",
    "destination_airport_id",
    "event_start_time",
    "event_end_time",
    "actual_arrival_utc",
    "actual_departure_utc",
    "split",
)


@dataclass(frozen=True)
class Data2TurnaroundReferenceCell:
    airport_id: str
    value_minutes: float
    sample_count: int
    fallback_level: Literal["AIRPORT_CELL", "GLOBAL"]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class Data2TurnaroundReference:
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
    cells: tuple[Data2TurnaroundReferenceCell, ...]
    manifest_freeze_id: str
    support_state: SupportState
    reason_code: str

    def lookup(self, airport_id: str) -> SupportedValue:
        """Frozen-reference lookup at decision time.

        Every airport resolves to at least the global fallback; a cell with
        min-support met resolves to the cell median. data2 basis is DIRECT
        official gate actuals, so support stays SUPPORTED (never fabricated).
        """
        cell = next(
            (item for item in self.cells if item.airport_id == airport_id), None
        )
        if cell is not None and cell.fallback_level == _LEVEL_CELL:
            value, level, count, reason = (
                cell.value_minutes,
                _LEVEL_CELL,
                cell.sample_count,
                ("DIRECT_GATE_TURNAROUND_REFERENCE;CELL_MEDIAN"),
            )
            flags = ("REFERENCE_LEVEL_CELL", "REFERENCE_SOURCE_DIRECT_GATE_ACTUALS")
        else:
            value, level, count = (
                self.global_value_minutes,
                _LEVEL_GLOBAL,
                self.global_sample_count,
            )
            reason = "DIRECT_GATE_TURNAROUND_REFERENCE;FALLBACK_GLOBAL"
            flags = ("REFERENCE_LEVEL_GLOBAL", "REFERENCE_SOURCE_DIRECT_GATE_ACTUALS")
            if cell is not None:
                flags += ("REFERENCE_CELL_MIN_SUPPORT_FALLBACK",)
        return SupportedValue(
            value=value,
            unit="minutes",
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            support_state=SupportState.SUPPORTED,
            reason_code=reason,
            quality_flags=tuple(sorted(flags + (f"REFERENCE_CELL_N={count}",))),
        )


def _row_fingerprint(row: dict[str, Any]) -> str:
    explicit = row.get("source_fingerprint")
    if explicit:
        return str(explicit)
    return content_id(
        {
            "flight_id": row["flight_id"],
            "aircraft_id": row["aircraft_id"],
            "actual_arrival_utc": row["actual_arrival_utc"].isoformat(),
            "actual_departure_utc": row["actual_departure_utc"].isoformat(),
            "origin_airport_id": row["origin_airport_id"],
            "destination_airport_id": row["destination_airport_id"],
        }
    )


def _gap_minutes(predecessor: dict[str, Any], successor: dict[str, Any]) -> float:
    pred_arrival = predecessor["actual_arrival_utc"]
    succ_departure = successor["actual_departure_utc"]
    gap = (succ_departure - pred_arrival).total_seconds() / 60.0
    if gap <= 0 or gap > MAX_GAP_MINUTES:
        raise ContractError(f"REFERENCE_ACTUAL_GAP_OUT_OF_DOMAIN:{gap}")
    return gap


def build_data2_turnaround_reference(
    flights: list[dict[str, Any]],
    *,
    fit_period: str,
    dataset_instance_id: str = "data2_2019",
    min_cell_size: int = 50,
    statistic_id: str = STATISTIC_ID,
) -> Data2TurnaroundReference:
    """Fit the data2 train-frozen DIRECT gate turnaround reference.

    Rows must be FlightRecord/OperationalEventRecord-shaped dicts (as produced
    by D2-BTS-SCHEDULE/D2-BTS-ACTUAL) plus a "split" key. Only split ==
    "train" rows are used for fitting; the reference is reproducible and
    row-order invariant.
    """
    for row in flights:
        for key in _REQUIRED_ROW_KEYS:
            if key not in row or row[key] in (None, ""):
                raise ContractError(f"REFERENCE_ROW_MISSING:{key}")
    datasets = {row["dataset_instance_id"] for row in flights}
    if datasets != {dataset_instance_id}:
        raise ContractError("REFERENCE_DATASET_MISMATCH")

    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")

    training_rows = [row for row in flights if row["split"] == "train"]
    if not training_rows:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")
    episodes = build_data2_episode_records(
        training_rows, max_gap_minutes=MAX_GAP_MINUTES
    )

    by_flight_id = {row["flight_id"]: row for row in training_rows}
    gaps: list[tuple[float, str]] = []
    manifest_records: list[dict[str, Any]] = []
    for episode in episodes:
        predecessor = by_flight_id[episode.predecessor_flight_id]
        successor = by_flight_id[episode.successor_flight_id]
        gap = _gap_minutes(predecessor, successor)
        gaps.append((gap, episode.connection_airport_id))
        manifest_records.append(
            {
                "record_id": episode.episode_id,
                "source_fingerprint": content_id(
                    {
                        "predecessor": _row_fingerprint(predecessor),
                        "successor": _row_fingerprint(successor),
                    }
                ),
                "split": "train",
            }
        )

    if not gaps:
        raise ContractError("REFERENCE_TRAIN_PARTITION_NO_LEGAL_GAPS")
    global_value = median(gap for gap, _airport in gaps)
    global_count = len(gaps)
    if global_count < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")

    cells: dict[str, list[float]] = {}
    for gap, airport in gaps:
        cells.setdefault(airport, []).append(gap)

    cell_records: list[Data2TurnaroundReferenceCell] = []
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
            Data2TurnaroundReferenceCell(
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
        grouping_keys=("connection_airport_id",),
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

    return Data2TurnaroundReference(
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
        support_state=SupportState.SUPPORTED,
        reason_code="DIRECT_GATE_TURNAROUND_REFERENCE",
    )


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise ContractError(f"REFERENCE_PAYLOAD_MISSING:{key}")
    return payload[key]


def data2_turnaround_reference_from_payload(
    payload: dict[str, Any],
) -> Data2TurnaroundReference:
    """Reuse an existing train-frozen turnaround payload without refitting."""
    cells = tuple(
        Data2TurnaroundReferenceCell(
            airport_id=item["airport_id"],
            value_minutes=float(item["value_minutes"]),
            sample_count=int(item["sample_count"]),
            fallback_level=item["fallback_level"],
            provenance=tuple(item.get("provenance", ())),
        )
        for item in _require(payload, "cells")
    )
    cells_count = payload.get("cells_count")
    if cells_count is not None and int(cells_count) != len(cells):
        raise ContractError("REFERENCE_PAYLOAD_CELL_COUNT_MISMATCH")
    return Data2TurnaroundReference(
        reference_id=_require(payload, "reference_id"),
        dataset_instance_id=payload.get("dataset_instance_id", "data2_2019"),
        rule_id=_require(payload, "rule_id"),
        rule_version=_require(payload, "rule_version"),
        fit_period=_require(payload, "fit_period"),
        statistic_id=payload.get("statistic_id", STATISTIC_ID),
        minimum_support_rule=payload.get("minimum_support_rule", MINIMUM_SUPPORT_RULE),
        fallback_hierarchy=tuple(payload.get("fallback_hierarchy", FALLBACK_HIERARCHY)),
        applicability_scope=payload.get("applicability_scope", APPLICABILITY_SCOPE),
        global_value_minutes=float(_require(payload, "global_value_minutes")),
        global_sample_count=int(_require(payload, "global_sample_count")),
        cells=cells,
        manifest_freeze_id=_require(payload, "manifest_freeze_id"),
        support_state=SupportState(_require(payload, "support_state")),
        reason_code=payload.get("reason_code", "DIRECT_GATE_TURNAROUND_REFERENCE"),
    )
