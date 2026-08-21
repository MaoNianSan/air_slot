from typing import Any

from model.common.errors import ContractError
from model.PRE.contracts.canonical import AggregateReference, AirportReference

from .normalization_common import deterministic_id, missing, number, provenance


def canonicalize_airport_row(
    row: dict[str, Any], *, dataset_instance_id: str = "data1_2019",
    rule_id: str = "D1-OURAIRPORTS", logical_source: str = "ourairports",
) -> AirportReference:
    ident = str(row.get("ident", "")).strip().upper()
    iata = None if missing(row.get("iata_code")) else str(row["iata_code"]).strip().upper()
    if not ident:
        raise ContractError("AIRPORT_IDENTITY_MISSING")
    raw_id = deterministic_id("raw", {"source": logical_source, "ident": ident})
    value = {
        "canonical_object_type": "AirportReference",
        "dataset_instance_id": dataset_instance_id,
        "canonical_record_id": deterministic_id(
            "airport", {"dataset": dataset_instance_id, "ident": ident}
        ),
        "airport_id": ident,
        "airport_id_namespace": "ICAO_OR_LOCAL",
        "icao_code": ident if len(ident) == 4 else None,
        "iata_code": iata,
        "latitude_deg": number(row.get("latitude_deg")),
        "longitude_deg": number(row.get("longitude_deg")),
        "elevation_m": None if missing(row.get("elevation_ft"))
        else float(row["elevation_ft"]) * 0.3048,
        "airport_type": row.get("type"),
        "event_time": None,
        "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD",
        "provenance_rule_id": rule_id,
        "quality_flags": (),
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance": provenance(dataset_instance_id, logical_source, raw_id, rule_id),
    }
    return AirportReference.model_validate(value)


def canonicalize_timezone_row(row: dict[str, Any]) -> AirportReference:
    iata = str(row.get("iata", "")).strip().upper()
    ident = str(row.get("ident", "")).strip().upper()
    if not iata or not row.get("timezone"):
        raise ContractError("TIMEZONE_REFERENCE_IDENTITY_MISSING")
    raw_id = deterministic_id(
        "raw", {"source": "timezone_reference", "iata": iata, "timezone": row["timezone"]}
    )
    return AirportReference.model_validate({
        "canonical_object_type": "AirportReference",
        "dataset_instance_id": "data2_2019",
        "canonical_record_id": deterministic_id(
            "timezone", {"iata": iata, "timezone": row["timezone"]}
        ),
        "airport_id": iata,
        "airport_id_namespace": "IATA",
        "icao_code": ident or None,
        "iata_code": iata,
        "timezone": row["timezone"],
        "event_time": None,
        "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD",
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance_rule_id": "D2-TIMEZONE",
        "provenance": provenance(
            "data2_2019", "timezone_reference", raw_id, "D2-TIMEZONE"
        ),
        "quality_flags": (),
    })


def canonicalize_aggregate_row(
    row: dict[str, Any], *, dataset_instance_id: str, source_family: str
) -> AggregateReference:
    normalized = {str(key): value for key, value in row.items()}
    upper = {key.upper(): value for key, value in normalized.items()}
    if source_family == "bts_db1b":
        origin = str(upper.get("ORIGIN", "")).strip()
        dest = str(upper.get("DEST", "")).strip()
        value = number(upper.get("PASSENGERS"))
        unit = "passengers"
        period = "2019"
        join = {"origin": origin, "destination": dest}
    elif source_family == "bts_t100":
        origin = str(upper.get("ORIGIN", "")).strip()
        dest = str(upper.get("DEST", "")).strip()
        service_class = str(upper.get("CLASS", "")).strip() or None
        value = {
            "passengers": number(upper.get("PASSENGERS")),
            "seats": number(upper.get("SEATS")),
            "service_class": service_class,
        }
        unit = "counts"
        period = f"{upper.get('YEAR', '')}-{str(upper.get('MONTH', '')).zfill(2)}"
        join = {"origin": origin, "destination": dest}
    else:
        raise ContractError("AGGREGATE_SOURCE_UNSUPPORTED")
    record_id = deterministic_id(
        "aggregate", {"source": source_family, "period": period, "join": join, "value": value}
    )
    rule_id = f"D2-{source_family.split('_')[-1].upper()}"
    raw_id = deterministic_id(
        "raw", {"source": source_family, "period": period, "join": join, "value": value}
    )
    return AggregateReference.model_validate({
        "canonical_object_type": "AggregateReference",
        "dataset_instance_id": dataset_instance_id,
        "canonical_record_id": record_id,
        "reference_name": source_family,
        "grain": "origin_destination_period",
        "join_key": join,
        "reference_period": period,
        "value": value,
        "unit": unit,
        "event_time": None,
        "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD",
        "provenance_rule_id": rule_id,
        "quality_flags": (),
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance": provenance(dataset_instance_id, source_family, raw_id, rule_id),
    })


def canonicalize_eurostat_payload(payload: dict[str, Any]) -> AggregateReference:
    if payload.get("class") != "dataset" or "value" not in payload:
        raise ContractError("EUROSTAT_JSON_STAT_SCHEMA_MISMATCH")
    period = next(
        iter(payload.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})),
        "UNKNOWN",
    )
    record_id = deterministic_id(
        "aggregate",
        {"source": payload.get("source"), "period": period, "updated": payload.get("updated")},
    )
    raw_id = deterministic_id(
        "raw", {"source": "eurostat", "period": period, "updated": payload.get("updated")}
    )
    return AggregateReference.model_validate({
        "canonical_object_type": "AggregateReference",
        "dataset_instance_id": "data1_2019",
        "canonical_record_id": record_id,
        "reference_name": payload.get("extension", {}).get(
            "id", payload.get("label", "EUROSTAT")
        ),
        "grain": "json_stat_cube",
        "join_key": {"dataset": payload.get("extension", {}).get("id", "UNKNOWN")},
        "reference_period": period,
        "value": {
            "observations": len(payload.get("value", {})),
            "source_updated": payload.get("updated"),
        },
        "unit": "source_defined_counts",
        "event_time": None,
        "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD",
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance_rule_id": "D1-EUROSTAT",
        "provenance": provenance("data1_2019", "eurostat", raw_id, "D1-EUROSTAT"),
        "quality_flags": (),
    })


_EUROSTAT_PASSENGER_SLICE = {
    "freq": "M",
    "unit": "PAS",
    "tra_meas": "PAS_BRD",
    "schedule": "TOT",
    "tra_cov": "TOTAL",
}


def _eurostat_airport_month_record(
    airport: str, period: str, value: Any
) -> AggregateReference:
    join = {
        "rep_airp": airport,
        "time": period,
        "measure": "PAS_BRD",
        "schedule": "TOT",
        "tra_cov": "TOTAL",
    }
    raw_id = deterministic_id(
        "raw",
        {
            "source": "eurostat",
            "period": period,
            "airport": airport,
            "measure": "PAS_BRD",
            "schedule": "TOT",
            "tra_cov": "TOTAL",
        },
    )
    record_id = deterministic_id(
        "aggregate",
        {
            "source": "eurostat",
            "period": period,
            "airport": airport,
            "measure": "PAS_BRD",
            "schedule": "TOT",
            "tra_cov": "TOTAL",
            "value": value,
        },
    )
    return AggregateReference.model_validate({
        "canonical_object_type": "AggregateReference",
        "dataset_instance_id": "data1_2019",
        "canonical_record_id": record_id,
        "reference_name": "passenger_reference",
        "grain": "airport_month",
        "join_key": join,
        "reference_period": period,
        "value": value,
        "unit": "passengers",
        "event_time": None,
        "availability_time": None,
        "availability_basis": "REFERENCE_PERIOD",
        "decision_time_role": "FROZEN_REFERENCE",
        "provenance_rule_id": "D1-EUROSTAT",
        "provenance": provenance("data1_2019", "eurostat", raw_id, "D1-EUROSTAT"),
        "quality_flags": (),
    })


def canonicalize_eurostat_passengers_payload(
    payload: dict[str, Any]
) -> tuple[AggregateReference, ...]:
    """Materialize the frozen monthly airport passenger slice."""
    if payload.get("class") != "dataset" or "value" not in payload:
        raise ContractError("EUROSTAT_JSON_STAT_SCHEMA_MISMATCH")
    dim_ids = tuple(payload.get("id") or ())
    sizes = tuple(payload.get("size") or ())
    if len(dim_ids) != len(sizes) or "rep_airp" not in dim_ids or "time" not in dim_ids:
        raise ContractError("EUROSTAT_JSON_STAT_DIMENSIONS_MISMATCH")
    dimensions = payload.get("dimension", {})
    slice_positions: dict[str, int] = {}
    for dim_id, label in _EUROSTAT_PASSENGER_SLICE.items():
        position = dimensions.get(dim_id, {}).get("category", {}).get("index", {}).get(label)
        if position is None:
            raise ContractError(f"EUROSTAT_SLICE_MISSING:{dim_id}:{label}")
        slice_positions[dim_id] = position

    def labels(dim_id: str) -> dict[int, str]:
        return {
            position: label
            for label, position in dimensions.get(dim_id, {})
            .get("category", {})
            .get("index", {})
            .items()
        }

    airport_labels = labels("rep_airp")
    time_labels = labels("time")
    raw_cells = payload["value"]
    cells = (
        ((int(key), value) for key, value in raw_cells.items())
        if isinstance(raw_cells, dict)
        else enumerate(raw_cells)
    )
    records: list[AggregateReference] = []
    for index, raw_value in cells:
        decoded: dict[str, int] = {}
        remaining = index
        for position, dim_id in enumerate(dim_ids):
            stride = 1
            for size in sizes[position + 1:]:
                stride *= size
            decoded[dim_id] = remaining // stride
            remaining %= stride
        if any(
            decoded[dim_id] != position
            for dim_id, position in slice_positions.items()
        ):
            continue
        airport = airport_labels.get(decoded["rep_airp"])
        period = time_labels.get(decoded["time"])
        if airport is None or period is None:
            continue
        records.append(_eurostat_airport_month_record(airport, period, raw_value))
    return tuple(sorted(
        records,
        key=lambda record: (
            record.reference_period,
            record.join_key.get("rep_airp", ""),
        ),
    ))
