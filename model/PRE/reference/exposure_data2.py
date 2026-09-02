"""Train-frozen expected downstream exposure for data2 (CRS schedule counts).

Frozen rule: DATA2_DOWNSTREAM_EXPOSURE@1.0.0 (user-approved 2026-08-14,
D2-5 option A, data2 scope; "接受").
Scientific object: expected number of same-aircraft downstream legs within a
360-minute horizon, estimated on the train partition. Unlike data1 (posthoc
flightlist chain counts), data2 counts the CRS schedule, which is visible at
decision time (FROZEN_REFERENCE) and never leaks POSTHOC event evidence.

Construction rule (data2):
    N_down(H=360) for train flight f =
        #{schedule rows g of the same aircraft: g.origin == f.destination AND
          f.scheduled_arrival_utc < g.scheduled_departure_utc
              <= f.scheduled_arrival_utc + 360 min}
    Count basis is the CRS schedule only (event_start_time = CRSDep,
    event_end_time = CRSArr, UTC). The anchor t_0 = pred.CRSArr is the same
    as the D2-2 decision-node grid start. Multiple scheduled departures within
    the window are counted without deduplication (option A: no slot merging).
    Statistic: MEDIAN per connection airport (the airport where the current
    leg arrives and downstream legs depart, consistent with D2-3 grouping).
    Minimum support: min cell 50 at every fallback level.
    Fallback: AIRPORT_CELL -> GLOBAL. Zero-coverage airport -> ABSTAIN.
    Evidence: DERIVED from CRS schedule counts (online-visible inputs),
    support SUPPORTED (unlike the data1 flightlist-chain basis, DEGRADED).

Lineage: RAW BTS On-Time rows -> FlightRecord (D2-BTS-SCHEDULE) ->
DATA2_DOWNSTREAM_EXPOSURE@1.0.0 -> expected_downstream_exposure
(FROZEN_REFERENCE) -> M2 (reference), M1 (floor boundary). data1
EXPECTED_DOWNSTREAM_EXPOSURE@1.0.0 is untouched.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
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
from model.common.config import load_config_layers
from model.common.paths import PROJECT_ROOT

RULE_ID = "DATA2_DOWNSTREAM_EXPOSURE"
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
    "split",
)


@dataclass(frozen=True)
class Data2ExposureReferenceCell:
    airport_id: str
    value_legs: float
    sample_count: int
    fallback_level: Literal["AIRPORT_CELL", "GLOBAL"]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class Data2ExposureReference:
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
    cells: tuple[Data2ExposureReferenceCell, ...]
    manifest_freeze_id: str
    support_state: SupportState
    reason_code: str

    def lookup(self, airport_id: str) -> SupportedValue:
        """Frozen-reference lookup at decision time.

        Airports with min-support met resolve to the cell median; airports with
        a cell below min support fall back to the global median. Airports with
        no train evidence at all ABSTAIN (value None), never fabricated.
        """
        cell = next(
            (item for item in self.cells if item.airport_id == airport_id), None
        )
        if cell is None:
            return SupportedValue(
                value=None,
                unit="legs",
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.DERIVED,
                support_state=SupportState.ABSTAIN,
                reason_code="NO_DOWNSTREAM_SCHEDULE_EVIDENCE",
                quality_flags=("REFERENCE_SOURCE_CRS_SCHEDULE",),
            )
        if cell.fallback_level == _LEVEL_CELL:
            return SupportedValue(
                value=cell.value_legs,
                unit="legs",
                evidence_class=EvidenceClass.DERIVED,
                support_ceiling=EvidenceClass.DERIVED,
                support_state=SupportState.SUPPORTED,
                reason_code="CRS_SCHEDULE_EXPECTED_EXPOSURE;CELL_MEDIAN",
                quality_flags=tuple(
                    sorted(
                        (
                            "REFERENCE_LEVEL_CELL",
                            "REFERENCE_SOURCE_CRS_SCHEDULE",
                            f"REFERENCE_CELL_N={cell.sample_count}",
                        )
                    )
                ),
            )
        return SupportedValue(
            value=self.global_value_legs,
            unit="legs",
            evidence_class=EvidenceClass.DERIVED,
            support_ceiling=EvidenceClass.DERIVED,
            support_state=SupportState.SUPPORTED,
            reason_code="CRS_SCHEDULE_EXPECTED_EXPOSURE;FALLBACK_GLOBAL",
            quality_flags=tuple(
                sorted(
                    (
                        "REFERENCE_LEVEL_GLOBAL",
                        "REFERENCE_SOURCE_CRS_SCHEDULE",
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
            "event_start_time": row["event_start_time"].isoformat(),
            "event_end_time": row["event_end_time"].isoformat(),
            "origin_airport_id": row["origin_airport_id"],
            "destination_airport_id": row["destination_airport_id"],
        }
    )


def _flight_id(row: dict[str, Any]) -> str:
    return str(row.get("canonical_record_id") or row["flight_id"])


def _schedule_groups(
    training_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Rows grouped by (namespace, aircraft), each sorted by CRS departure."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in training_rows:
        groups[(row["aircraft_id_namespace"], row["aircraft_id"])].append(row)
    for key in groups:
        groups[key].sort(key=lambda row: (row["event_start_time"], row["flight_id"]))
    return dict(groups)


def _count_downstream(
    flight: dict[str, Any],
    group: list[dict[str, Any]],
    starts: list[Any],
    horizon_minutes: int,
) -> int:
    """Same-aircraft scheduled departures from the connection airport in
    (t_0, t_0 + H] with t_0 = CRSArr of the current leg (D2-2 anchor)."""
    t0 = flight["event_end_time"]
    lo = bisect_right(starts, t0)
    hi = bisect_right(starts, t0 + timedelta(minutes=horizon_minutes))
    return sum(
        1
        for row in group[lo:hi]
        if row["origin_airport_id"] == flight["destination_airport_id"]
    )


def build_data2_downstream_exposure(
    flights: list[dict[str, Any]],
    *,
    fit_period: str,
    dataset_instance_id: str = "data2_2019",
    horizon_minutes: int = HORIZON_MINUTES,
    min_cell_size: int = 50,
    statistic_id: str = STATISTIC_ID,
) -> Data2ExposureReference:
    """Fit the data2 train-frozen CRS-schedule expected downstream exposure.

    Rows must be FlightRecord-shaped dicts (as produced by D2-BTS-SCHEDULE)
    plus a "split" key; only split == "train" rows are used. Counting uses the
    CRS schedule times only (event_start_time/event_end_time, UTC); actual
    event fields are neither required nor read.
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

    groups = _schedule_groups(training_rows)
    group_starts = {
        key: [row["event_start_time"] for row in group] for key, group in groups.items()
    }

    counts: list[tuple[int, str]] = []
    manifest_records: list[dict[str, Any]] = []
    for flight in sorted(training_rows, key=lambda row: row["flight_id"]):
        key = (flight["aircraft_id_namespace"], flight["aircraft_id"])
        downstream = 0
        if key in groups:
            downstream = _count_downstream(
                flight, groups[key], group_starts[key], horizon_minutes
            )
        counts.append((downstream, flight["destination_airport_id"]))
        manifest_records.append(
            {
                "record_id": _flight_id(flight),
                "source_fingerprint": _row_fingerprint(flight),
                "split": "train",
            }
        )

    if not counts:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")
    global_value = median(value for value, _airport in counts)
    global_count = len(counts)
    if global_count < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")

    cells: dict[str, list[int]] = {}
    for value, airport in counts:
        cells.setdefault(airport, []).append(value)

    cell_records: list[Data2ExposureReferenceCell] = []
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
            Data2ExposureReferenceCell(
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

    return Data2ExposureReference(
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
        support_state=SupportState.SUPPORTED,
        reason_code="CRS_SCHEDULE_EXPECTED_EXPOSURE",
    )


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise ContractError(f"REFERENCE_PAYLOAD_MISSING:{key}")
    return payload[key]


def data2_downstream_exposure_from_payload(
    payload: dict[str, Any],
) -> Data2ExposureReference:
    """Reuse an existing train-frozen exposure payload without refitting."""
    cells = tuple(
        Data2ExposureReferenceCell(
            airport_id=item["airport_id"],
            value_legs=float(item["value_legs"]),
            sample_count=int(item["sample_count"]),
            fallback_level=item["fallback_level"],
            provenance=tuple(item.get("provenance", ())),
        )
        for item in _require(payload, "cells")
    )
    cells_count = payload.get("cells_count")
    if cells_count is not None and int(cells_count) != len(cells):
        raise ContractError("REFERENCE_PAYLOAD_CELL_COUNT_MISMATCH")
    return Data2ExposureReference(
        reference_id=_require(payload, "reference_id"),
        dataset_instance_id=payload.get("dataset_instance_id", "data2_2019"),
        rule_id=_require(payload, "rule_id"),
        rule_version=_require(payload, "rule_version"),
        fit_period=_require(payload, "fit_period"),
        statistic_id=payload.get("statistic_id", STATISTIC_ID),
        minimum_support_rule=payload.get("minimum_support_rule", MINIMUM_SUPPORT_RULE),
        fallback_hierarchy=tuple(payload.get("fallback_hierarchy", FALLBACK_HIERARCHY)),
        applicability_scope=payload.get("applicability_scope", APPLICABILITY_SCOPE),
        horizon_minutes=int(payload.get("horizon_minutes", HORIZON_MINUTES)),
        global_value_legs=float(_require(payload, "global_value_legs")),
        global_sample_count=int(_require(payload, "global_sample_count")),
        cells=cells,
        manifest_freeze_id=_require(payload, "manifest_freeze_id"),
        support_state=SupportState(_require(payload, "support_state")),
        reason_code=payload.get("reason_code", "CRS_SCHEDULE_EXPECTED_EXPOSURE"),
    )
