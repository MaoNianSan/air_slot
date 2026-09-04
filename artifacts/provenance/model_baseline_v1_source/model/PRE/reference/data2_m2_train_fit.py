"""Data2 M2 train-fit helpers (PRE-owned raw preprocessing boundary).

All raw BTS On-Time CSV reading, row canonicalization, reference fitting,
and train-scale computation for the frozen M2 Data2 formal estimand lives
here so that raw schema tokens and episode construction never leak into
downstream model/M2 code (PRE ownership gate V2).

The fit rules are the frozen D2-1..D2-10 contracts:
- train partition 2019-01..06 (On-Time monthly CSVs), canonical rows only
- turnaround / downstream-exposure / H1 passenger (Q1+Q2 DB1B) / taxi
  references, fit_period 2019-H1
- train scales = positive Train-period medians of the frozen native
  quantities, with dict-indexed lookups byte-identical to the frozen
  reference lookup() methods
- Final Test months are never read here (months 01..06 only).
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from model.common.errors import ContractError
from model.common.identity import content_id
from model.PRE.canonical.normalization import canonicalize_ontime_row
from model.PRE.contracts.training_artifacts import (
    Data2M2CanonicalTrainRow,
    Data2M2TrainPreparationArtifact,
)
from model.PRE.episode.builder import build_data2_episode_records
from model.PRE.reference.exposure_data2 import (
    Data2ExposureReference,
    build_data2_downstream_exposure,
)
from model.PRE.reference.passenger_data2 import (
    Data2PassengerReference,
    H1_RULE_ID as DATA2_PASSENGER_REFERENCE_H1,
    build_data2_passenger_reference,
)
from model.PRE.reference.taxi_data2 import (
    Data2TaxiReference,
    data2_taxi_reference_from_payload,
)
from model.PRE.reference.turnaround_data2 import (
    Data2TurnaroundReference,
    build_data2_turnaround_reference,
)
from model.PRE.streaming.data2 import load_timezones
from model.PRE.references.passenger_load_reference import build_expected_passengers_reference
from model.PRE.references.connection_share_reference import build_connection_share_reference
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.native_formulas import (
    d_to_from_components,
    d_tx_realized,
    p_itinerary_native,
    p_service_native,
    p_time_native,
)


def ontime_paths(root: Path, months: tuple[int, ...]) -> tuple[Path, ...]:
    paths = []
    for month in months:
        directory = (
            root / "data2" / "raw" / "bts" / "ontime" / "2019" / f"month={month:02d}"
        )
        matches = sorted(directory.glob("*.csv"))
        if len(matches) != 1:
            raise ContractError(f"M2_ONTIME_MONTH_FILE_COUNT:{month}")
        paths.append(matches[0])
    return tuple(paths)


def iter_train_rows(paths: tuple[Path, ...], timezones: dict[str, str]):
    """Stream compact canonical train row dicts (schedule + outcome fields)."""
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="", errors="replace") as handle:
            for raw in csv.DictReader(handle):
                try:
                    schedule, outcome = canonicalize_ontime_row(
                        {key: raw.get(key, "") for key in ONTIME_PROJECTED_FIELDS},
                        timezones,
                    )
                except Exception:
                    continue
                if (
                    schedule.aircraft_id is None
                    or outcome.cancelled
                    or outcome.diverted
                ):
                    continue
                yield {
                    "dataset_instance_id": schedule.dataset_instance_id,
                    "aircraft_id_namespace": schedule.aircraft_id_namespace,
                    "aircraft_id": schedule.aircraft_id,
                    "flight_id": schedule.flight_id,
                    "canonical_record_id": schedule.canonical_record_id,
                    "origin_airport_id": schedule.origin_airport_id,
                    "destination_airport_id": schedule.destination_airport_id,
                    "event_start_time": schedule.event_start_time,
                    "event_end_time": schedule.event_end_time,
                    "actual_arrival_utc": outcome.actual_arrival_utc,
                    "actual_departure_utc": outcome.actual_departure_utc,
                    "taxi_out_minutes": outcome.taxi_out_minutes,
                    "carrier_id": getattr(schedule, "carrier_id", None),
                    "month": int(raw.get("FlightDate", "").split("-")[1]) if raw.get("FlightDate", "").count("-") == 2 else None,
                    "split": "train",
                }


def collect_train_rows(
    paths: tuple[Path, ...], timezones: dict[str, str]
) -> list[Data2M2CanonicalTrainRow]:
    return list(iter_train_rows(paths, timezones))


def build_data2_m2_train_preparation(
    *,
    root: Path,
    months: tuple[int, ...] = tuple(range(1, 7)),
    fit_period: str = "2019-H1",
) -> Data2M2TrainPreparationArtifact:
    """Read and canonicalize the frozen M2 Train partition inside PRE."""
    paths = ontime_paths(root, months)
    timezones = load_timezones(root / "data2" / "refs" / "us_airport_timezones.csv")
    return Data2M2TrainPreparationArtifact(
        rows=collect_train_rows(paths, timezones),
        source_paths=paths,
        months=months,
        fit_period=fit_period,
    )


__all__ = [
    "ONTIME_PROJECTED_FIELDS",
    "build_data2_m2_train_preparation",
    "collect_train_rows",
    "compute_train_scales",
    "fit_train_references",
    "iter_train_rows",
    "ontime_paths",
    "stream_passenger_routes",
    "stream_t100_rows",
    "stream_db1b_coupon_rows",
    "fit_passenger_consequence_references",
    "compute_passenger_consequence_train_scales",
]

ONTIME_PROJECTED_FIELDS = [
    "FlightDate",
    "Reporting_Airline",
    "Tail_Number",
    "Flight_Number_Reporting_Airline",
    "Origin",
    "Dest",
    "CRSDepTime",
    "CRSArrTime",
    "DepTime",
    "ArrTime",
    "WheelsOff",
    "WheelsOn",
    "TaxiOut",
    "TaxiIn",
    "DepDelay",
    "ArrDelay",
    "DepDelayMinutes",
    "ArrDelayMinutes",
    "Cancelled",
    "Diverted",
]

M2_FORMAL_SCOPE = CONSEQUENCE_COMPONENTS

M2_NATIVE_DEFINITIONS = {
    "F_continuity": {
        "quantity": "Z_turn",
        "definition": "max(0, R_IB - turnaround_reference(connection_airport))",
        "unit": "minutes",
        "driver": "turnaround_compression",
    },
    "F_execution": {
        "quantity": "Z_exec",
        "definition": "D_OB",
        "unit": "minutes",
        "driver": "additional_off_block_wait",
    },
    "F_propagation": {
        "quantity": "Z_takeoff * E_down",
        "definition": "D_TO * expected_downstream_exposure(origin)",
        "unit": "exposure_minutes",
        "driver": "takeoff_delay_x_expected_downstream_exposure",
    },
    "P_time": {
        "quantity": "Nbar_pax * D_TO",
        "definition": "expected_passengers_per_flight * D_TO",
        "unit": "passenger_minutes",
        "driver": "expected_passengers_per_flight_x_delay",
    },
    "P_itinerary": {
        "quantity": "Nbar_pax * r_conn * I[D_TO > 45]",
        "definition": "expected_passengers_per_flight * connection_share * I[D_TO > 45 minutes]",
        "unit": "expected_disrupted_connecting_passenger_exposure",
        "driver": "expected_passengers_x_connecting_share_x_itinerary_threshold",
    },
    "P_service": {
        "quantity": "Nbar_pax * I[D_TO >= 180]",
        "definition": "expected_passengers_per_flight * I[D_TO >= 180 minutes]",
        "unit": "expected_long_delay_passenger_service_exposure",
        "driver": "expected_passengers_x_service_threshold",
    },
    "R_operating": {
        "quantity": "D_TX",
        "definition": "D_TX",
        "unit": "excess_taxi_minutes",
        "driver": "excess_taxi",
    },
}


def stream_passenger_routes(coupon_paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    sums: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for path in coupon_paths:
        with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            idx_pax = header.index("Passengers")
            idx_origin = header.index("Origin")
            idx_dest = header.index("Dest")
            for raw in reader:
                if not raw or len(raw) <= max(idx_pax, idx_origin, idx_dest):
                    continue
                origin = raw[idx_origin].strip()
                destination = raw[idx_dest].strip()
                if not origin or not destination:
                    continue
                try:
                    pax = float(raw[idx_pax])
                except ValueError:
                    continue
                key = (origin, destination)
                sums[key] += pax
                counts[key] += 1
    return [
        {
            "dataset_instance_id": "data2_2019",
            "canonical_record_id": content_id(
                {"source": "bts_db1b", "origin": origin, "destination": destination}
            ),
            "join_key": {"origin": origin, "destination": destination},
            "reference_period": "2019",
            "value": total,
            "record_count": counts[(origin, destination)],
            "split": "train",
        }
        for (origin, destination), total in sorted(sums.items())
    ]


def _parse_month(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer() or not 1 <= int(numeric) <= 12:
        return None
    return int(numeric)


def _resolve_required_field(fieldnames: list[str], candidates: tuple[str, ...], *, error_code: str) -> str:
    by_upper = {str(name).strip().upper(): name for name in fieldnames if name is not None}
    for candidate in candidates:
        if candidate.upper() in by_upper:
            return by_upper[candidate.upper()]
    raise ContractError(error_code)


class _T100Stream:
    def __init__(self, path: Path, *, fit_partition: str, allowed_months: tuple[int, ...]):
        self.path = path
        self.fit_partition = fit_partition
        self.allowed_months = tuple(allowed_months)
        self.audit = {
            "rows_seen": 0,
            "rows_used": 0,
            "rows_excluded_outside_fit_period": 0,
            "rows_excluded_invalid_month": 0,
            "used_months": [],
        }

    def __iter__(self):
        with self.path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            month_field = _resolve_required_field(list(reader.fieldnames or []), ("MONTH",), error_code="T100_MONTH_FIELD_MISSING")
            for row in reader:
                self.audit["rows_seen"] += 1
                month = _parse_month(row.get(month_field))
                if month is None:
                    self.audit["rows_excluded_invalid_month"] += 1
                    continue
                if month not in self.allowed_months:
                    self.audit["rows_excluded_outside_fit_period"] += 1
                    continue
                self.audit["rows_used"] += 1
                if month not in self.audit["used_months"]:
                    self.audit["used_months"].append(month)
                yield {**row, "MONTH": month, "split": self.fit_partition}


def stream_t100_rows(
    path: Path,
    *,
    fit_partition: str = "TRAIN",
    allowed_months: tuple[int, ...] = (1, 2, 3, 4, 5, 6),
):
    return _T100Stream(path, fit_partition=fit_partition, allowed_months=allowed_months)


class _DB1BStream:
    def __init__(self, paths: tuple[Path, ...], *, fit_partition: str, allowed_quarters: tuple[int, ...]):
        self.paths = paths
        self.fit_partition = fit_partition
        self.allowed_quarters = tuple(allowed_quarters)
        self.audit = {
            "rows_seen": 0,
            "rows_used": 0,
            "rows_excluded_outside_fit_period": 0,
            "rows_excluded_invalid_schema": 0,
            "quarters_used": [],
            "trip_break_fields": [],
        }

    def __iter__(self):
        for path in self.paths:
            with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                tripbreak_field = _resolve_required_field(
                    fieldnames, ("Break", "TripBreak", "TRIPBREAK", "TRIP_BREAK"),
                    error_code="DB1B_COUPON_TRIP_BREAK_FIELD_MISSING",
                )
                passengers_field = _resolve_required_field(fieldnames, ("Passengers",), error_code="DB1B_COUPON_PASSENGERS_FIELD_MISSING")
                origin_field = _resolve_required_field(fieldnames, ("Origin",), error_code="DB1B_COUPON_ORIGIN_FIELD_MISSING")
                dest_field = _resolve_required_field(fieldnames, ("Dest",), error_code="DB1B_COUPON_DEST_FIELD_MISSING")
                quarter_field = next((name for name in fieldnames if str(name).strip().upper() in {"QUARTER", "QTR"}), None)
                inferred = None
                if quarter_field is None:
                    match = re.search(r"DB1BCoupon_2019_([1-4])\.csv$", path.name, flags=re.IGNORECASE)
                    if match:
                        inferred = int(match.group(1))
                    else:
                        raise ContractError("DB1B_COUPON_QUARTER_UNRESOLVED")
                if tripbreak_field not in self.audit["trip_break_fields"]:
                    self.audit["trip_break_fields"].append(tripbreak_field)
                for row in reader:
                    self.audit["rows_seen"] += 1
                    if quarter_field is not None:
                        quarter = _parse_month(row.get(quarter_field))
                        if quarter is None or quarter not in (1, 2, 3, 4):
                            raise ContractError("DB1B_COUPON_QUARTER_UNRESOLVED")
                    else:
                        quarter = inferred
                    if quarter not in self.allowed_quarters:
                        self.audit["rows_excluded_outside_fit_period"] += 1
                        continue
                    self.audit["rows_used"] += 1
                    if quarter not in self.audit["quarters_used"]:
                        self.audit["quarters_used"].append(quarter)
                    yield {
                        **row,
                        "Passengers": row.get(passengers_field),
                        "Origin": row.get(origin_field),
                        "Dest": row.get(dest_field),
                        "TRIPBREAK": row.get(tripbreak_field),
                        "Quarter": quarter,
                        "split": self.fit_partition,
                    }


def stream_db1b_coupon_rows(
    paths: tuple[Path, ...],
    *,
    fit_partition: str = "TRAIN",
    allowed_quarters: tuple[int, ...] = (1, 2),
):
    return _DB1BStream(paths, fit_partition=fit_partition, allowed_quarters=allowed_quarters)


def fit_passenger_consequence_references(*, root: Path, fit_period: str = "2019-H1") -> dict[str, Any]:
    """Build T-100 expected load and DB1B continuation references."""
    t100_path = root / "data2" / "raw" / "bts" / "t100" / "2019" / "T_T100_SEGMENT_ALL_CARRIER.csv"
    coupon_paths = tuple(sorted((root / "data2" / "raw" / "bts" / "db1b" / "2019" / "coupon").glob("Origin_and_Destination_Survey_DB1BCoupon_2019_[12].csv")))
    t100_stream = stream_t100_rows(t100_path, fit_partition="TRAIN", allowed_months=(1, 2, 3, 4, 5, 6))
    coupon_stream = stream_db1b_coupon_rows(coupon_paths, fit_partition="TRAIN", allowed_quarters=(1, 2))
    pax = build_expected_passengers_reference(t100_stream, fit_partition="TRAIN")
    conn = build_connection_share_reference(coupon_stream, fit_partition="TRAIN")
    return {
        "expected_pax": pax,
        "connection_share": conn,
        "fit_period": fit_period,
        "fit_year": 2019,
        "t100_fit_months": [1, 2, 3, 4, 5, 6],
        "db1b_fit_quarters": [1, 2],
        "t100_audit": t100_stream.audit,
        "db1b_audit": coupon_stream.audit,
        "source_paths": (t100_path, *coupon_paths),
    }


def compute_passenger_consequence_train_scales(rows: list[dict[str, Any]], *, expected_pax_reference, connection_share_reference, itinerary_threshold_minutes: float = 45.0, service_threshold_minutes: float = 180.0) -> dict[str, dict[str, Any]]:
    """Compute positive TRAIN medians for all passenger components."""
    values = {"P_time": [], "P_itinerary": [], "P_service": []}
    populations = {name: 0 for name in values}
    for row in rows:
        d_to = row.get("d_to_minutes")
        if d_to is None:
            continue
        cell = expected_pax_reference.lookup(row.get("carrier_id"), row["origin_airport_id"], row["destination_airport_id"], row.get("month"))
        share_cell = connection_share_reference.lookup(row["origin_airport_id"], row["destination_airport_id"], row.get("quarter"))
        if cell is None or share_cell is None:
            continue
        pax = float(cell.reference_value)
        conn = pax * float(share_cell.connection_share)
        delay = float(d_to)
        if delay > 0:
            values["P_time"].append(p_time_native(pax, delay))
        if p_itinerary_native(pax, float(share_cell.connection_share), delay, itinerary_threshold_minutes) > 0:
            values["P_itinerary"].append(conn)
        if p_service_native(pax, delay, service_threshold_minutes) > 0:
            values["P_service"].append(pax)
        for name in values:
            populations[name] += 1
    output = {}
    units = {"P_time": "passenger-minutes", "P_itinerary": "expected_disrupted_connecting_passenger_exposure", "P_service": "expected_long_delay_passenger_service_exposure"}
    for name, positive in values.items():
        if not positive:
            raise ContractError(f"M2_TRAIN_SCALE_NO_POSITIVE_POPULATION:{name}")
        output[name] = {"median": median(positive), "positive_n": len(positive), "population_rows": populations[name], "unit": units[name]}
    return output


def _artifact_hash(payload: dict) -> str:
    return content_id(payload)


def reference_to_payload(reference) -> dict:
    """Serialize a frozen Data2 reference dataclass to its payload form.

    Mirrors the exact keys expected by the corresponding
    data2_*_reference_from_payload loaders (round-trip stable).
    """
    if isinstance(reference, Data2TurnaroundReference):
        return {
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
                    "airport_id": cell.airport_id,
                    "value_minutes": cell.value_minutes,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2ExposureReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "horizon_minutes": reference.horizon_minutes,
            "global_value_legs": reference.global_value_legs,
            "global_sample_count": reference.global_sample_count,
            "cells": [
                {
                    "airport_id": cell.airport_id,
                    "value_legs": cell.value_legs,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2TaxiReference):
        return {
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
                    "airport_id": cell.airport_id,
                    "value_minutes": cell.value_minutes,
                    "sample_count": cell.sample_count,
                    "fallback_level": cell.fallback_level,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    if isinstance(reference, Data2PassengerReference):
        return {
            "reference_id": reference.reference_id,
            "dataset_instance_id": reference.dataset_instance_id,
            "rule_id": reference.rule_id,
            "rule_version": reference.rule_version,
            "fit_period": reference.fit_period,
            "statistic_id": reference.statistic_id,
            "scale_factor": reference.scale_factor,
            "minimum_support_rule": reference.minimum_support_rule,
            "fallback_hierarchy": list(reference.fallback_hierarchy),
            "applicability_scope": reference.applicability_scope,
            "total_passengers": reference.total_passengers,
            "total_sample_count": reference.total_sample_count,
            "route_count": reference.route_count,
            "cells": [
                {
                    "origin": cell.origin_airport_id,
                    "destination": cell.destination_airport_id,
                    "value_passengers": cell.value_passengers,
                    "sample_count": cell.sample_count,
                    "provenance": list(cell.provenance),
                }
                for cell in reference.cells
            ],
            "cells_count": len(reference.cells),
            "manifest_freeze_id": reference.manifest_freeze_id,
            "support_state": reference.support_state.value,
            "reason_code": reference.reason_code,
        }
    raise ContractError("M2_REFERENCE_SERIALIZATION_UNSUPPORTED")


def fit_train_references(
    rows: list[dict[str, Any]],
    *,
    root: Path,
    fit_period: str = "2019-H1",
) -> dict[str, dict[str, Any]]:
    turnaround = build_data2_turnaround_reference(rows, fit_period=fit_period)
    exposure = build_data2_downstream_exposure(rows, fit_period=fit_period)
    coupon_paths = tuple(
        sorted(
            (root / "data2" / "raw" / "bts" / "db1b" / "2019" / "coupon").glob(
                "Origin_and_Destination_Survey_DB1BCoupon_2019_[12].csv"
            )
        )
    )
    passenger_rows = stream_passenger_routes(coupon_paths)
    passenger = build_data2_passenger_reference(
        passenger_rows,
        fit_period=fit_period,
        rule_id=DATA2_PASSENGER_REFERENCE_H1,
    )
    taxi_path = (
        root
        / "artifacts"
        / "diagnostics"
        / "v5_development_freeze"
        / "DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json"
    )
    taxi_payload = json.loads(taxi_path.read_text(encoding="utf-8"))
    taxi = data2_taxi_reference_from_payload(taxi_payload)

    def payload_for(reference, extra: dict | None = None) -> dict:
        payload = reference_to_payload(reference)
        if extra:
            payload.update(extra)
        payload["artifact_hash"] = _artifact_hash(payload)
        return payload

    return {
        "turnaround": payload_for(turnaround),
        "downstream_exposure": payload_for(exposure),
        "passenger": payload_for(passenger),
        "taxi": dict(taxi_payload),
    }


def _supported_value(reference, *args) -> float | None:
    value = reference.lookup(*args)
    if value.value is None or str(value.support_state.value) == "ABSTAIN":
        return None
    return float(value.value)


def _turnaround_taxi_value(
    index, airport, reference, *, abstain_if_missing=False
) -> float | None:
    """Same resolution as Data2Turnaround/TaxiReference.lookup (cell or global).

    Turnaround always has a global fallback; taxi ABSTAINs for airports with
    no direct taxi evidence (``abstain_if_missing=True``).
    """
    cell = index.get(airport)
    if cell is None:
        return None if abstain_if_missing else float(reference.global_value_minutes)
    if cell.fallback_level == "AIRPORT_CELL":
        return float(cell.value_minutes)
    return float(reference.global_value_minutes)


def _exposure_value(index, airport, reference) -> float | None:
    """Same resolution as Data2ExposureReference.lookup (cell/global/ABSTAIN)."""
    cell = index.get(airport)
    if cell is None:
        return None
    if cell.fallback_level == "AIRPORT_CELL":
        return float(cell.value_legs)
    return float(reference.global_value_legs)


def _passenger_value(index, origin, destination) -> float | None:
    """Same resolution as Data2PassengerReference.lookup (route cell or ABSTAIN)."""
    cell = index.get((origin, destination))
    return None if cell is None else float(cell.value_passengers)


def compute_train_scales(
    rows: list[dict[str, Any]],
    references: Mapping[str, Any],
    *,
    turnaround_ref,
    taxi_ref,
    exposure_ref,
    passenger_ref=None,
    expected_pax_reference=None,
    connection_share_reference=None,
    itinerary_threshold_minutes: float = 45.0,
    service_threshold_minutes: float = 180.0,
) -> dict[str, dict[str, Any]]:
    """Positive Train-period medians of the active seven V4 quantities.

    The active passenger path requires the T-100 expected-passenger and DB1B
    continuation-share references.  The older route-sum passenger reference
    is retained only for historical registry replay and is never substituted
    here, because it is not an expected-passengers-per-performed-flight
    reference.
    """
    from model.PRE.episode.builder import build_data2_episode_records

    expected_pax_reference = expected_pax_reference or references.get("expected_pax")
    connection_share_reference = connection_share_reference or references.get("connection_share")
    if expected_pax_reference is None or not hasattr(expected_pax_reference, "lookup"):
        raise ContractError("M2_V4_EXPECTED_PASSENGER_REFERENCE_REQUIRED")
    if connection_share_reference is None or not hasattr(connection_share_reference, "lookup"):
        raise ContractError("M2_V4_CONNECTION_SHARE_REFERENCE_REQUIRED")

    turnaround_index = {cell.airport_id: cell for cell in turnaround_ref.cells}
    taxi_index = {cell.airport_id: cell for cell in taxi_ref.cells}
    exposure_index = {cell.airport_id: cell for cell in exposure_ref.cells}
    values: dict[str, list[float]] = {name: [] for name in M2_FORMAL_SCOPE}
    population: dict[str, dict[str, int]] = {
        name: {"rows": 0, "positive": 0} for name in M2_FORMAL_SCOPE
    }

    episodes = build_data2_episode_records(rows, max_gap_minutes=360)
    by_flight = {row["flight_id"]: row for row in rows}
    for episode in episodes:
        predecessor = by_flight[episode.predecessor_flight_id]
        airport = episode.connection_airport_id
        reference = _turnaround_taxi_value(turnaround_index, airport, turnaround_ref)
        if reference is None:
            continue
        r_ib = max(
            0.0,
            (
                predecessor["actual_arrival_utc"] - predecessor["event_end_time"]
            ).total_seconds()
            / 60.0,
        )
        quantity = max(0.0, r_ib - reference)
        population["F_continuity"]["rows"] += 1
        if quantity > 0:
            values["F_continuity"].append(quantity)
            population["F_continuity"]["positive"] += 1

    for row in rows:
        taxi_out = row.get("taxi_out_minutes")
        if taxi_out is None:
            continue
        origin = row["origin_airport_id"]
        destination = row["destination_airport_id"]
        taxi_reference = _turnaround_taxi_value(
            taxi_index, origin, taxi_ref, abstain_if_missing=True
        )
        if taxi_reference is None:
            continue
        delta_ob = (
            row["actual_departure_utc"] - row["event_start_time"]
        ).total_seconds() / 60.0
        z_exec = max(0.0, delta_ob)
        z_taxi = max(0.0, float(taxi_out) - taxi_reference)
        d_to = d_to_from_components(z_exec, z_taxi)

        population["F_execution"]["rows"] += 1
        if z_exec > 0:
            values["F_execution"].append(z_exec)
            population["F_execution"]["positive"] += 1

        population["R_operating"]["rows"] += 1
        if z_taxi > 0:
            values["R_operating"].append(z_taxi)
            population["R_operating"]["positive"] += 1

        exposure = _exposure_value(exposure_index, origin, exposure_ref)
        if exposure is not None:
            quantity = d_to * exposure
            population["F_propagation"]["rows"] += 1
            if quantity > 0:
                values["F_propagation"].append(quantity)
                population["F_propagation"]["positive"] += 1

        month = row.get("month")
        quarter = row.get("quarter")
        if quarter in (None, "") and month not in (None, ""):
            try:
                month_number = int(month)
                quarter = (month_number - 1) // 3 + 1 if 1 <= month_number <= 12 else None
            except (TypeError, ValueError):
                quarter = None
        passenger_cell = expected_pax_reference.lookup(
            row.get("carrier_id"), origin, destination, month
        )
        if passenger_cell is not None:
            passenger = float(passenger_cell.reference_value)
            population["P_time"]["rows"] += 1
            q_time = p_time_native(passenger, d_to)
            if q_time > 0:
                values["P_time"].append(q_time)
                population["P_time"]["positive"] += 1

            share_cell = connection_share_reference.lookup(origin, destination, quarter)
            if share_cell is not None:
                population["P_itinerary"]["rows"] += 1
                q_itinerary = p_itinerary_native(
                    passenger,
                    float(share_cell.connection_share),
                    d_to,
                    itinerary_threshold_minutes,
                )
                if q_itinerary > 0:
                    values["P_itinerary"].append(q_itinerary)
                    population["P_itinerary"]["positive"] += 1

            population["P_service"]["rows"] += 1
            q_service = p_service_native(
                passenger,
                d_to,
                service_threshold_minutes,
            )
            if q_service > 0:
                values["P_service"].append(q_service)
                population["P_service"]["positive"] += 1

    output = {}
    for name in M2_FORMAL_SCOPE:
        positive = values[name]
        if not positive:
            raise ContractError(f"M2_V4_TRAIN_SCALE_NO_POSITIVE_POPULATION:{name}")
        output[name] = {
            "median": median(positive),
            "positive_n": len(positive),
            "population_rows": population[name]["rows"],
            "unit": M2_NATIVE_DEFINITIONS[name]["unit"],
            "definition": M2_NATIVE_DEFINITIONS[name]["definition"],
        }
    return output
