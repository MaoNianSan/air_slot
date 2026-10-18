"""Train-frozen expected downstream exposure for data1 (flightlist chain).

Frozen rule: EXPECTED_DOWNSTREAM_EXPOSURE@1.0.0 (user-approved 2026-08-13,
D1-10 option A, data1 scope).
Scientific object: expected number of same-aircraft downstream legs within a
360-minute horizon, estimated on the train partition (data1 has no true
schedule, so this is a train-frozen expected reference, never decision-time
realized chain records).

Construction rule (data1):
    N_down(H=360) for train flight f =
        #{chain successors s of f: first_seen(s) - first_seen(f) <= 360 min}
    Chain semantics inherited from SAME_AIRCRAFT_AIRPORT_GAP@1.0.0 (same
    aircraft, airport continuity, positive gap <= 360); each flight has at
    most one immediate successor; successors are followed transitively.
    Statistic: MEDIAN per connection airport (the airport where the current
    leg arrives and downstream legs depart, consistent with D1-8 grouping).
    Minimum support: min cell 50 at every fallback level.
    Fallback: AIRPORT_CELL -> GLOBAL. Zero-coverage airport -> ABSTAIN.
    Evidence: EMPIRICAL_REFERENCE from realized archive chains -> DEGRADED
    support (flightlist is a posthoc archive, never online evidence).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Literal

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import SupportedValue
from model.PRE.episode.builder import build_episode_records
from model.PRE.transformation import (
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
)
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT

RULE_ID = "EXPECTED_DOWNSTREAM_EXPOSURE"
RULE_VERSION = "1.0.0"
STATISTIC_ID = "MEDIAN"
MINIMUM_SUPPORT_RULE = "MIN_CELL_SIZE_50"
FALLBACK_HIERARCHY = ("AIRPORT_CELL", "GLOBAL")
APPLICABILITY_SCOPE = "CONNECTION_AIRPORT_GROUP"
HORIZON_MINUTES = int(
    load_config_layers(PROJECT_ROOT / "configs")
    .scientific.parameters["downstream_exposure_horizon_minutes"]
    .value
)

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
    "first_seen_utc",
    "split",
)


@dataclass(frozen=True)
class ExposureReferenceCell:
    airport_id: str
    value_legs: float
    sample_count: int
    fallback_level: Literal["AIRPORT_CELL", "GLOBAL"]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class ExposureReference:
    reference_id: str
    dataset_instance_id: str
    rule_id: str
    rule_version: str
    fit_period: str
    statistic_id: str
    minimum_support_rule: str
    fallback_hierarchy: tuple[str, ...]
    applicability_scope: str
    horizon_minutes: int
    global_value_legs: float
    global_sample_count: int
    cells: tuple[ExposureReferenceCell, ...]
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
                unit="legs",
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
                support_state=SupportState.ABSTAIN,
                reason_code="NO_DOWNSTREAM_CHAIN_EVIDENCE",
                quality_flags=("REFERENCE_SOURCE_TRAIN_CHAIN",),
            )
        if cell.fallback_level == _LEVEL_CELL:
            return SupportedValue(
                value=cell.value_legs,
                unit="legs",
                evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
                support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
                support_state=SupportState.DEGRADED,
                reason_code="TRAIN_CHAIN_EXPECTED_EXPOSURE;CELL_MEDIAN",
                quality_flags=tuple(
                    sorted(
                        (
                            "REFERENCE_LEVEL_CELL",
                            "REFERENCE_SOURCE_TRAIN_CHAIN",
                            f"REFERENCE_CELL_N={cell.sample_count}",
                        )
                    )
                ),
            )
        return SupportedValue(
            value=self.global_value_legs,
            unit="legs",
            evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
            support_ceiling=EvidenceClass.EMPIRICAL_REFERENCE,
            support_state=SupportState.DEGRADED,
            reason_code="TRAIN_CHAIN_EXPECTED_EXPOSURE;FALLBACK_GLOBAL",
            quality_flags=tuple(
                sorted(
                    (
                        "REFERENCE_LEVEL_GLOBAL",
                        "REFERENCE_SOURCE_TRAIN_CHAIN",
                        "REFERENCE_CELL_MIN_SUPPORT_FALLBACK",
                        f"REFERENCE_CELL_N={cell.sample_count}",
                    )
                )
            ),
        )


def _row_fingerprint(row: dict[str, Any]) -> str:
    explicit = row.get("source_fingerprint")
    if explicit:
        return str(explicit)
    return content_id(
        {
            "flight_id": row["flight_id"],
            "aircraft_id": row["aircraft_id"],
            "first_seen_utc": row["first_seen_utc"].isoformat(),
            "origin_airport_id": row["origin_airport_id"],
            "destination_airport_id": row["destination_airport_id"],
        }
    )


def _flight_id(row: dict[str, Any]) -> str:
    return str(row.get("canonical_record_id") or row["flight_id"])


def build_downstream_exposure(
    flights: list[dict[str, Any]],
    *,
    fit_period: str,
    dataset_instance_id: str = "data1_2019",
    horizon_minutes: int = HORIZON_MINUTES,
    min_cell_size: int = 50,
    statistic_id: str = STATISTIC_ID,
) -> ExposureReference:
    """Fit the data1 train-frozen expected downstream exposure.

    Rows must be FlightRecord-shaped dicts (as produced by D1-OPENSKY-FLIGHT)
    plus a "split" key. Only split == "train" rows are used; the chain is
    constructed with the frozen SAME_AIRCRAFT_AIRPORT_GAP@1.0.0 semantics.
    """
    for row in flights:
        for key in _REQUIRED_ROW_KEYS:
            if key not in row or row[key] in (None, ""):
                raise ContractError(f"REFERENCE_ROW_MISSING:{key}")
    if {row["dataset_instance_id"] for row in flights} != {dataset_instance_id}:
        raise ContractError("REFERENCE_DATASET_MISMATCH")

    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")

    training_rows = [row for row in flights if row["split"] == "train"]
    if not training_rows:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")
    episodes = build_episode_records(
        training_rows
    )  # chain rule max_gap=360 (D1-1); horizon is a separate window

    by_flight_id = {row["flight_id"]: row for row in training_rows}
    successor_of = {
        episode.predecessor_flight_id: episode.successor_flight_id
        for episode in episodes
    }

    counts: list[tuple[int, str]] = []
    manifest_records: list[dict[str, Any]] = []
    for flight in sorted(training_rows, key=lambda row: row["flight_id"]):
        downstream = 0
        current = flight
        while current["flight_id"] in successor_of:
            successor = by_flight_id[successor_of[current["flight_id"]]]
            if (
                successor["first_seen_utc"] - flight["first_seen_utc"]
            ).total_seconds() / 60.0 > horizon_minutes:
                break
            downstream += 1
            current = successor
        counts.append((downstream, flight["destination_airport_id"]))
        manifest_records.append(
            {
                "record_id": _flight_id(flight),
                "source_fingerprint": _row_fingerprint(flight),
                "split": "train",
            }
        )

    global_value = median(value for value, _airport in counts)
    global_count = len(counts)
    if global_count < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")

    cells: dict[str, list[int]] = {}
    for value, airport in counts:
        cells.setdefault(airport, []).append(value)

    cell_records: list[ExposureReferenceCell] = []
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
            ExposureReferenceCell(
                airport_id=airport,
                value_legs=cell_value,
                sample_count=cell_count,
                fallback_level=level,
                provenance=(
                    f"airport={airport}",
                    f"n={cell_count}",
                    f"fallback_level={level}",
                    f"horizon_minutes={horizon_minutes}",
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
            "horizon_minutes": horizon_minutes,
            "minimum_support_rule": manifest.minimum_support_rule,
            "fallback_hierarchy": FALLBACK_HIERARCHY,
            "global_value_legs": global_value,
            "global_sample_count": global_count,
            "cells": [
                {
                    "airport_id": item.airport_id,
                    "value_legs": item.value_legs,
                    "sample_count": item.sample_count,
                    "fallback_level": item.fallback_level,
                }
                for item in cell_records
            ],
            "freeze_id": manifest.freeze_id,
        }
    )

    return ExposureReference(
        reference_id=reference_id,
        dataset_instance_id=dataset_instance_id,
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        fit_period=fit_period,
        statistic_id=statistic_id,
        minimum_support_rule=manifest.minimum_support_rule,
        fallback_hierarchy=FALLBACK_HIERARCHY,
        applicability_scope=APPLICABILITY_SCOPE,
        horizon_minutes=horizon_minutes,
        global_value_legs=global_value,
        global_sample_count=global_count,
        cells=tuple(cell_records),
        manifest_freeze_id=manifest.freeze_id,
        support_state=SupportState.DEGRADED,
        reason_code="TRAIN_CHAIN_EXPECTED_EXPOSURE",
    )
