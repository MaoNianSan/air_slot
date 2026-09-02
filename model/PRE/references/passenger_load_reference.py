"""Train-frozen expected passengers-per-performed-flight reference.

The reference is deliberately an expected value at a frozen T-100 grain,
never an observed passenger count for an individual flight.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterable

from model.common.enums import EvidenceClass, SupportState
from model.common.identity import content_id

REFERENCE_UNIT = "passengers_per_flight"
SOURCE = "T100"
FIT_PARTITION = "TRAIN"
FALLBACK_HIERARCHY = (
    "carrier-route-month",
    "carrier-route",
    "route-month",
    "route",
    "carrier",
    "global",
)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
        upper_name = name.upper()
        if upper_name in row:
            return row[upper_name]
    upper = {str(k).upper(): v for k, v in row.items()}
    for name in names:
        if name.upper() in upper:
            return upper[name.upper()]
    return None


def _carrier(row: dict[str, Any]) -> str | None:
    value = _field(row, "CARRIER", "UNIQUE_CARRIER", "REPORTING_AIRLINE")
    text = "" if value is None else str(value).strip()
    return text or None


def _month(row: dict[str, Any]) -> str | None:
    value = _field(row, "MONTH")
    if value in (None, ""):
        return None
    try:
        return f"{int(float(value)):02d}"
    except (TypeError, ValueError):
        return str(value).strip() or None


@dataclass(frozen=True)
class ExpectedPassengersReferenceCell:
    key: tuple[str, ...]
    reference_value: float
    grain: str
    fallback_level: str
    numerator_passengers: float
    denominator_departures_performed: float
    sample_size: int
    support_state: SupportState
    reference_id: str
    lineage_hash: str


@dataclass(frozen=True)
class ExpectedPassengersReference:
    reference_id: str
    reference_unit: str
    grain: str
    fallback_hierarchy: tuple[str, ...]
    fit_partition: str
    source: str
    cells: tuple[ExpectedPassengersReferenceCell, ...]
    support_state: SupportState
    evidence_class: EvidenceClass
    lineage_hash: str
    excluded_rows: int = 0

    @cached_property
    def _cells_by_key(self) -> dict[tuple[str, tuple[str, ...]], ExpectedPassengersReferenceCell]:
        return {(cell.fallback_level, cell.key): cell for cell in self.cells}

    def lookup(
        self,
        carrier: str | None,
        origin: str,
        destination: str,
        month: str | int | None = None,
    ) -> ExpectedPassengersReferenceCell | None:
        month_text = None if month in (None, "") else f"{int(month):02d}" if str(month).isdigit() else str(month)
        candidates = [
            ((carrier or "", origin, destination, month_text or ""), "carrier-route-month"),
            ((carrier or "", origin, destination), "carrier-route"),
            ((origin, destination, month_text or ""), "route-month"),
            ((origin, destination), "route"),
            ((carrier or "",), "carrier"),
            ((), "global"),
        ]
        for key, level in candidates:
            cell = self._cells_by_key.get((level, key))
            if cell is not None and cell.support_state is not SupportState.ABSTAIN:
                return cell
        return None


def _make_cell(level: str, key: tuple[str, ...], values: tuple[float, float, int], grain: str) -> ExpectedPassengersReferenceCell | None:
    numerator, denominator, sample_size = values
    if not (_finite(numerator) and _finite(denominator) and denominator > 0 and numerator >= 0):
        return None
    value = numerator / denominator
    if not (_finite(value) and value >= 0):
        return None
    lineage = content_id({"level": level, "key": key, "numerator": numerator, "denominator": denominator, "sample_size": sample_size})
    return ExpectedPassengersReferenceCell(
        key=key,
        reference_value=value,
        grain=grain,
        fallback_level=level,
        numerator_passengers=numerator,
        denominator_departures_performed=denominator,
        sample_size=sample_size,
        support_state=SupportState.SUPPORTED,
        reference_id=f"sha256:{lineage[7:]}",
        lineage_hash=lineage,
    )


def build_expected_passengers_reference(
    rows: Iterable[dict[str, Any]],
    *,
    fit_partition: str = FIT_PARTITION,
    source: str = SOURCE,
) -> ExpectedPassengersReference:
    """Build a T-100 reference using only rows from the declared fit partition."""
    groups: dict[tuple[str, tuple[str, ...]], list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    excluded = 0
    for row in rows:
        split = str(_field(row, "SPLIT", "FIT_PARTITION") or fit_partition).upper()
        if split != fit_partition.upper():
            continue
        passengers = _field(row, "PASSENGERS")
        departures = _field(row, "DEPARTURES_PERFORMED")
        origin = str(_field(row, "ORIGIN", "ORIGIN_AIRPORT") or "").strip()
        destination = str(_field(row, "DEST", "DESTINATION", "DEST_AIRPORT") or "").strip()
        carrier = _carrier(row)
        month = _month(row)
        if not origin or not destination or not (_finite(passengers) and _finite(departures)) or float(departures) <= 0 or float(passengers) < 0:
            excluded += 1
            continue
        base = (float(passengers), float(departures))
        keys = [
            ("carrier-route-month", (carrier or "", origin, destination, month or "")),
            ("carrier-route", (carrier or "", origin, destination)),
            ("route-month", (origin, destination, month or "")),
            ("route", (origin, destination)),
            ("carrier", (carrier or "",)),
            ("global", ()),
        ]
        for level, key in keys:
            stats = groups[(level, key)]
            stats[0] += base[0]; stats[1] += base[1]; stats[2] += 1
    cells = []
    for (level, key), values in sorted(groups.items()):
        cell = _make_cell(level, key, (values[0], values[1], int(values[2])), level)
        if cell is not None:
            cells.append(cell)
    payload = {
        "source": source,
        "fit_partition": fit_partition,
        "reference_unit": REFERENCE_UNIT,
        "fallback_hierarchy": FALLBACK_HIERARCHY,
        "cells": [cell.__dict__ for cell in cells],
        "excluded_rows": excluded,
    }
    digest = content_id(payload)
    return ExpectedPassengersReference(
        reference_id=digest,
        reference_unit=REFERENCE_UNIT,
        grain="carrier+origin+destination+month",
        fallback_hierarchy=FALLBACK_HIERARCHY,
        fit_partition=fit_partition,
        source=source,
        cells=tuple(cells),
        support_state=SupportState.SUPPORTED if cells else SupportState.ABSTAIN,
        evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
        lineage_hash=digest,
        excluded_rows=excluded,
    )


def expected_passengers_reference_from_payload(payload: dict[str, Any]) -> ExpectedPassengersReference:
    cells = tuple(
        ExpectedPassengersReferenceCell(
            key=tuple(item["key"]),
            reference_value=float(item["reference_value"]),
            grain=str(item["grain"]),
            fallback_level=str(item["fallback_level"]),
            numerator_passengers=float(item["numerator_passengers"]),
            denominator_departures_performed=float(item["denominator_departures_performed"]),
            sample_size=int(item["sample_size"]),
            support_state=SupportState(item["support_state"]),
            reference_id=str(item["reference_id"]),
            lineage_hash=str(item["lineage_hash"]),
        )
        for item in payload["cells"]
    )
    return ExpectedPassengersReference(
        reference_id=str(payload["reference_id"]),
        reference_unit=str(payload["reference_unit"]),
        grain=str(payload["grain"]),
        fallback_hierarchy=tuple(payload["fallback_hierarchy"]),
        fit_partition=str(payload["fit_partition"]),
        source=str(payload["source"]),
        cells=cells,
        support_state=SupportState(payload["support_state"]),
        evidence_class=EvidenceClass(payload["evidence_class"]),
        lineage_hash=str(payload["lineage_hash"]),
        excluded_rows=int(payload.get("excluded_rows", 0)),
    )


__all__ = ["ExpectedPassengersReference", "ExpectedPassengersReferenceCell", "build_expected_passengers_reference", "expected_passengers_reference_from_payload"]
