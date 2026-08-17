"""Train-frozen DIRECT taxi-out reference for data2 (BTS 2019 official TaxiOut).

Frozen rule: DATA2_TAXI_REFERENCE@1.0.0 (user-approved 2026-08-14, D2-4
option A, data2 scope; "有官方肯定用官方" -> official BTS TaxiOut column).
Scientific object: empirical taxi-out time reference per origin airport.

Construction rule (data2):
    taxi_out = official BTS TaxiOut minutes (per completed, non-diverted flight;
    POSTHOC_ONLY with D2-BTS-ACTUAL, date offset restored by delay minutes).
    Fit partition: train rows only -> train-frozen reference (freeze_id).
    Statistic: MEDIAN per origin_airport_id.
    Minimum support: min cell size 50 at every fallback level.
    Fallback hierarchy: AIRPORT_CELL -> GLOBAL.
    Zero-coverage airports (no train row with a legal TaxiOut value) -> ABSTAIN
    (NO_TAXI_DIRECT_EVIDENCE), mirroring data1 option A semantics.
    Evidence: DIRECT (official BTS TaxiOut), support SUPPORTED (unlike the
    data1 trajectory-pair proxy basis, which stays DEGRADED).

Lineage: RAW BTS On-Time rows -> OperationalEventRecord (D2-BTS-ACTUAL) ->
DATA2_TAXI_REFERENCE@1.0.0 -> taxi_reference (FROZEN_REFERENCE) ->
M2 (reference), M1 (floor boundary). data1 TAXI_REFERENCE@1.0.0 is untouched.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from typing import Any, Literal

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import SupportedValue
from model.PRE.canonical.normalization_common import deterministic_id, missing, number
from model.PRE.canonical.timezone import infer_rollover, local_hhmm_to_utc
from model.PRE.transformation import (
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
)

RULE_ID = "DATA2_TAXI_REFERENCE"
RULE_VERSION = "1.0.0"
STATISTIC_ID = "MEDIAN"
MINIMUM_SUPPORT_RULE = "MIN_CELL_SIZE_50"
FALLBACK_HIERARCHY = ("AIRPORT_CELL", "GLOBAL")
APPLICABILITY_SCOPE = "ORIGIN_AIRPORT_GROUP"

_LEVEL_CELL = "AIRPORT_CELL"
_LEVEL_GLOBAL = "GLOBAL"

_REQUIRED_FLIGHT_KEYS = (
    "dataset_instance_id",
    "aircraft_id",
    "flight_id",
    "origin_airport_id",
    "taxi_out_minutes",
    "split",
)


@dataclass(frozen=True)
class Data2TaxiReferenceCell:
    airport_id: str
    value_minutes: float
    sample_count: int
    fallback_level: Literal["AIRPORT_CELL", "GLOBAL"]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class Data2TaxiReference:
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
    cells: tuple[Data2TaxiReferenceCell, ...]
    manifest_freeze_id: str
    support_state: SupportState
    reason_code: str

    def lookup(self, airport_id: str) -> SupportedValue:
        """Frozen-reference lookup at decision time.

        Airports with min-support met resolve to the cell median; airports with
        a cell below min support fall back to the global median. Airports with
        no train evidence at all ABSTAIN (value None), never fabricated.
        """
        cell = next((item for item in self.cells if item.airport_id == airport_id), None)
        if cell is None:
            return SupportedValue(
                value=None,
                unit="minutes",
                evidence_class=EvidenceClass.UNSUPPORTED,
                support_ceiling=EvidenceClass.DIRECT,
                support_state=SupportState.ABSTAIN,
                reason_code="NO_TAXI_DIRECT_EVIDENCE",
                quality_flags=("REFERENCE_SOURCE_DIRECT_TAXI_OUT",),
            )
        if cell.fallback_level == _LEVEL_CELL:
            return SupportedValue(
                value=cell.value_minutes,
                unit="minutes",
                evidence_class=EvidenceClass.DIRECT,
                support_ceiling=EvidenceClass.DIRECT,
                support_state=SupportState.SUPPORTED,
                reason_code="DIRECT_TAXI_OUT_REFERENCE;CELL_MEDIAN",
                quality_flags=tuple(
                    sorted(
                        (
                            "REFERENCE_LEVEL_CELL",
                            "REFERENCE_SOURCE_DIRECT_TAXI_OUT",
                            f"REFERENCE_CELL_N={cell.sample_count}",
                        )
                    )
                ),
            )
        return SupportedValue(
            value=self.global_value_minutes,
            unit="minutes",
            evidence_class=EvidenceClass.DIRECT,
            support_ceiling=EvidenceClass.DIRECT,
            support_state=SupportState.SUPPORTED,
            reason_code="DIRECT_TAXI_OUT_REFERENCE;FALLBACK_GLOBAL",
            quality_flags=tuple(
                sorted(
                    (
                        "REFERENCE_LEVEL_GLOBAL",
                        "REFERENCE_SOURCE_DIRECT_TAXI_OUT",
                        "REFERENCE_CELL_MIN_SUPPORT_FALLBACK",
                        f"REFERENCE_CELL_N={cell.sample_count}",
                    )
                )
            ),
        )


def _flight_id(flight: dict[str, Any]) -> str:
    return str(flight.get("canonical_record_id") or flight["flight_id"])


def _row_fingerprint(row: dict[str, Any]) -> str:
    explicit = row.get("source_fingerprint")
    if explicit:
        return str(explicit)
    return content_id(
        {
            "flight_id": row["flight_id"],
            "aircraft_id": row["aircraft_id"],
            "origin_airport_id": row["origin_airport_id"],
            "taxi_out_minutes": row["taxi_out_minutes"],
        }
    )


def _taxi_minutes(row: dict[str, Any]) -> float:
    value = row.get("taxi_out_minutes")
    try:
        minutes = float(value)
    except (TypeError, ValueError):
        raise ContractError(f"TAXI_VALUE_OUT_OF_DOMAIN:{value!r}")
    if minutes <= 0:
        raise ContractError(f"TAXI_VALUE_OUT_OF_DOMAIN:{value!r}")
    return minutes


def build_data2_taxi_reference(
    flights: list[dict[str, Any]],
    *,
    fit_period: str,
    dataset_instance_id: str = "data2_2019",
    min_cell_size: int = 50,
    statistic_id: str = STATISTIC_ID,
) -> Data2TaxiReference:
    """Fit the data2 train-frozen DIRECT taxi-out reference from flight rows.

    Rows must be OperationalEventRecord-shaped dicts (as produced by
    D2-BTS-ACTUAL) carrying official taxi_out_minutes, plus a "split" key.
    Only split == "train" rows are used for fitting; the reference is
    reproducible and row-order invariant.
    """
    for row in flights:
        for key in _REQUIRED_FLIGHT_KEYS:
            if key not in row or row[key] in (None, ""):
                raise ContractError(f"REFERENCE_FLIGHT_MISSING:{key}")
    datasets = {row["dataset_instance_id"] for row in flights}
    if datasets != {dataset_instance_id}:
        raise ContractError("REFERENCE_DATASET_MISMATCH")

    rule = current_transformation_registry().get(RULE_ID, RULE_VERSION)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")

    training = [row for row in flights if row["split"] == "train"]
    if not training:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")

    durations: list[tuple[float, str]] = []
    manifest_records: list[dict[str, Any]] = []
    for row in training:
        try:
            minutes = _taxi_minutes(row)
        except ContractError:
            continue
        durations.append((minutes, row["origin_airport_id"]))
        manifest_records.append(
            {
                "record_id": _flight_id(row),
                "source_fingerprint": _row_fingerprint(row),
                "split": "train",
            }
        )

    if not durations:
        raise ContractError("REFERENCE_TRAIN_PARTITION_NO_LEGAL_TAXI_VALUES")
    global_value = median(value for value, _airport in durations)
    global_count = len(durations)
    if global_count < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")

    cells: dict[str, list[float]] = {}
    for value, airport in durations:
        cells.setdefault(airport, []).append(value)

    cell_records: list[Data2TaxiReferenceCell] = []
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
            Data2TaxiReferenceCell(
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

    return Data2TaxiReference(
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
        reason_code="DIRECT_TAXI_OUT_REFERENCE",
    )


def data2_taxi_reference_payload(reference: Data2TaxiReference) -> dict[str, Any]:
    return {
        "schema_version": "DATA2_TAXI_REFERENCE_ARTIFACT_V1",
        "reference_id": reference.reference_id,
        "dataset_instance_id": reference.dataset_instance_id,
        "rule_id": reference.rule_id,
        "rule_version": reference.rule_version,
        "fit_period": reference.fit_period,
        "statistic_id": reference.statistic_id,
        "minimum_support_rule": reference.minimum_support_rule,
        "fallback_hierarchy": list(reference.fallback_hierarchy),
        "applicability_scope": reference.applicability_scope,
        "global_value_minutes": reference.global_value_minutes,
        "global_sample_count": reference.global_sample_count,
        "cells": [
            {
                "airport_id": item.airport_id,
                "value_minutes": item.value_minutes,
                "sample_count": item.sample_count,
                "fallback_level": item.fallback_level,
                "provenance": list(item.provenance),
            }
            for item in reference.cells
        ],
        "manifest_freeze_id": reference.manifest_freeze_id,
        "support_state": reference.support_state.value,
        "reason_code": reference.reason_code,
    }


def data2_taxi_reference_from_payload(payload: dict[str, Any]) -> Data2TaxiReference:
    return Data2TaxiReference(
        reference_id=payload["reference_id"],
        dataset_instance_id=payload["dataset_instance_id"],
        rule_id=payload["rule_id"],
        rule_version=payload["rule_version"],
        fit_period=payload["fit_period"],
        statistic_id=payload["statistic_id"],
        minimum_support_rule=payload["minimum_support_rule"],
        fallback_hierarchy=tuple(payload["fallback_hierarchy"]),
        applicability_scope=payload["applicability_scope"],
        global_value_minutes=float(payload["global_value_minutes"]),
        global_sample_count=int(payload["global_sample_count"]),
        cells=tuple(Data2TaxiReferenceCell(
            airport_id=item["airport_id"],
            value_minutes=float(item["value_minutes"]),
            sample_count=int(item["sample_count"]),
            fallback_level=item["fallback_level"],
            provenance=tuple(item["provenance"]),
        ) for item in payload["cells"]),
        manifest_freeze_id=payload["manifest_freeze_id"],
        support_state=SupportState(payload["support_state"]),
        reason_code=payload["reason_code"],
    )


def build_data2_taxi_reference_streaming(
    csv_paths: tuple[Path, ...],
    timezones: dict[str, str],
    *,
    fit_period: str = "2019-01..2019-06",
    min_cell_size: int = 50,
) -> tuple[Data2TaxiReference, dict[str, Any]]:
    """Fit the frozen reference without materializing row-shaped dictionaries."""
    values_by_airport: dict[str, list[float]] = {}
    input_rows = accepted_rows = 0
    source_hashes = {}
    projected = (
        "FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline",
        "Origin", "Dest", "CRSDepTime", "CRSArrTime", "Tail_Number",
        "TaxiOut", "Cancelled", "Diverted",
    )
    for path in csv_paths:
        source_hashes[str(path)] = f"sha256:{sha256(path.read_bytes()).hexdigest()}"
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as stream:
            for raw in csv.DictReader(stream):
                input_rows += 1
                row = {name: raw.get(name, "") for name in projected}
                try:
                    day = date.fromisoformat(str(row["FlightDate"])[:10])
                    origin, destination = str(row["Origin"]), str(row["Dest"])
                    if origin not in timezones or destination not in timezones \
                            or missing(row["Tail_Number"]):
                        continue
                    scheduled_departure = local_hhmm_to_utc(
                        day, row["CRSDepTime"], timezones[origin])
                    scheduled_arrival = local_hhmm_to_utc(
                        day, row["CRSArrTime"], timezones[destination])
                    if scheduled_departure is None or scheduled_arrival is None:
                        continue
                    infer_rollover(scheduled_departure, scheduled_arrival)
                    if bool(number(row["Cancelled"]) or 0) or bool(number(row["Diverted"]) or 0):
                        continue
                    taxi = number(row["TaxiOut"])
                    if taxi is None or float(taxi) <= 0:
                        continue
                except (TypeError, ValueError):
                    continue
                values_by_airport.setdefault(origin, []).append(float(taxi))
                accepted_rows += 1
    all_values = [value for values in values_by_airport.values() for value in values]
    if len(all_values) < min_cell_size:
        raise ContractError("REFERENCE_MINIMUM_SUPPORT_UNMET:GLOBAL")
    global_value = float(median(all_values))
    cells = []
    for airport in sorted(values_by_airport):
        values = values_by_airport[airport]
        if len(values) >= min_cell_size:
            value, level = float(median(values)), _LEVEL_CELL
        else:
            value, level = global_value, _LEVEL_GLOBAL
        cells.append(Data2TaxiReferenceCell(
            airport_id=airport,
            value_minutes=value,
            sample_count=len(values),
            fallback_level=level,
            provenance=(
                f"airport={airport}", f"n={len(values)}", f"fallback_level={level}",
                f"{RULE_ID}@{RULE_VERSION}",
            ),
        ))
    freeze_payload = {
        "rule": f"{RULE_ID}@{RULE_VERSION}",
        "fit_period": fit_period,
        "min_cell_size": min_cell_size,
        "source_hashes": source_hashes,
        "accepted_rows": accepted_rows,
        "global_value_minutes": global_value,
        "cells": [
            [item.airport_id, item.value_minutes, item.sample_count, item.fallback_level]
            for item in cells
        ],
    }
    freeze_id = content_id(freeze_payload)
    reference_id = content_id({**freeze_payload, "freeze_id": freeze_id})
    reference = Data2TaxiReference(
        reference_id=reference_id,
        dataset_instance_id="data2_2019",
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        fit_period=fit_period,
        statistic_id=STATISTIC_ID,
        minimum_support_rule=f"MIN_CELL_SIZE_{min_cell_size}",
        fallback_hierarchy=FALLBACK_HIERARCHY,
        applicability_scope=APPLICABILITY_SCOPE,
        global_value_minutes=global_value,
        global_sample_count=accepted_rows,
        cells=tuple(cells),
        manifest_freeze_id=freeze_id,
        support_state=SupportState.SUPPORTED,
        reason_code="DIRECT_TAXI_OUT_REFERENCE",
    )
    return reference, {
        **data2_taxi_reference_payload(reference),
        "input_rows": input_rows,
        "accepted_rows": accepted_rows,
        "source_hashes": source_hashes,
        "final_test_access_count": 0,
    }
