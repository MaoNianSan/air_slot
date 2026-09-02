"""Train-frozen historical continuation share from DB1B Coupon."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterable

from model.common.enums import EvidenceClass, SupportState
from model.common.identity import content_id


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


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ConnectionShareReferenceCell:
    key: tuple[str, ...]
    connection_share: float
    total_passenger_weight: float
    connecting_passenger_weight: float
    grain: str
    fallback_level: str
    sample_size: int
    support_state: SupportState
    reference_id: str
    lineage_hash: str


@dataclass(frozen=True)
class ConnectionShareReference:
    reference_id: str
    connection_share: float | None
    total_passenger_weight: float
    connecting_passenger_weight: float
    grain: str
    fallback_hierarchy: tuple[str, ...]
    fit_partition: str
    source: str
    cells: tuple[ConnectionShareReferenceCell, ...]
    support_state: SupportState
    evidence_class: EvidenceClass
    lineage_hash: str
    excluded_rows: int = 0

    @cached_property
    def _cells_by_key(self) -> dict[tuple[str, tuple[str, ...]], ConnectionShareReferenceCell]:
        return {(cell.fallback_level, cell.key): cell for cell in self.cells}

    def lookup(self, origin: str, destination: str, quarter: str | int | None = None) -> ConnectionShareReferenceCell | None:
        q = None if quarter in (None, "") else str(int(float(quarter)))
        candidates = [
            ((origin, destination, q or ""), "route-quarter"),
            ((origin, destination), "route"),
            ((q or "",), "quarter"),
            ((), "global"),
        ]
        for key, level in candidates:
            cell = self._cells_by_key.get((level, key))
            if cell is not None and cell.support_state is not SupportState.ABSTAIN:
                return cell
        return None


@dataclass(frozen=True)
class ExpectedConnectingPassengerReference:
    expected_connecting_passengers: float | None
    expected_passenger_reference_id: str
    connection_share_reference_id: str
    support_state: SupportState
    evidence_class: EvidenceClass
    lineage_hash: str


def build_connection_share_reference(
    rows: Iterable[dict[str, Any]], *, fit_partition: str = "TRAIN", source: str = "DB1B_COUPON"
) -> ConnectionShareReference:
    hierarchy = ("route-quarter", "route", "quarter", "global")
    groups: dict[tuple[str, tuple[str, ...]], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    excluded = 0
    for row in rows:
        split = str(_field(row, "SPLIT", "FIT_PARTITION") or fit_partition).upper()
        if split != fit_partition.upper():
            continue
        pax = _field(row, "PASSENGERS", "PASSENGER_WEIGHT")
        origin = str(_field(row, "ORIGIN") or "").strip()
        destination = str(_field(row, "DEST") or "").strip()
        quarter = _field(row, "QUARTER", "QTR")
        if not origin or not destination or not _finite(pax) or float(pax) < 0:
            excluded += 1
            continue
        q = "" if quarter in (None, "") else str(int(float(quarter)))
        continuation = _field(row, "TRIPBREAK", "TRIP_BREAK", "BREAK")
        is_connecting = str(continuation or "").strip() == ""
        weight = float(pax)
        for level, key in (
            ("route-quarter", (origin, destination, q)),
            ("route", (origin, destination)),
            ("quarter", (q,)),
            ("global", ()),
        ):
            stats = groups[(level, key)]
            stats[0] += weight
            stats[1] += weight if is_connecting else 0.0
            stats[2] += 1
    cells = []
    total_weight = 0.0
    connecting_weight = 0.0
    for (level, key), values in sorted(groups.items()):
        total, connecting, sample_size = values
        if not (_finite(total) and _finite(connecting) and total > 0 and 0 <= connecting <= total):
            continue
        share = connecting / total
        if not (_finite(share) and 0 <= share <= 1):
            continue
        lineage = content_id({"level": level, "key": key, "total": total, "connecting": connecting, "sample_size": int(sample_size)})
        cells.append(ConnectionShareReferenceCell(
            key=key, connection_share=share, total_passenger_weight=total,
            connecting_passenger_weight=connecting, grain=level,
            fallback_level=level, sample_size=int(sample_size),
            support_state=SupportState.SUPPORTED,
            reference_id=lineage, lineage_hash=lineage,
        ))
        if level == "global":
            total_weight, connecting_weight = total, connecting
    payload = {"source": source, "fit_partition": fit_partition, "fallback_hierarchy": hierarchy, "cells": [cell.__dict__ for cell in cells], "excluded_rows": excluded}
    digest = content_id(payload)
    return ConnectionShareReference(
        reference_id=digest,
        connection_share=(connecting_weight / total_weight if total_weight > 0 else None),
        total_passenger_weight=total_weight,
        connecting_passenger_weight=connecting_weight,
        grain="origin+destination+quarter",
        fallback_hierarchy=hierarchy,
        fit_partition=fit_partition,
        source=source,
        cells=tuple(cells),
        support_state=SupportState.SUPPORTED if cells else SupportState.ABSTAIN,
        evidence_class=EvidenceClass.EMPIRICAL_REFERENCE,
        lineage_hash=digest,
        excluded_rows=excluded,
    )


def derive_expected_connecting_passengers(
    expected_pax: Any, connection_share: Any,
) -> ExpectedConnectingPassengerReference:
    pax_value = getattr(expected_pax, "reference_value", expected_pax)
    share_value = getattr(connection_share, "connection_share", connection_share)
    pax_id = getattr(expected_pax, "reference_id", "")
    share_id = getattr(connection_share, "reference_id", "")
    support = getattr(expected_pax, "support_state", SupportState.SUPPORTED)
    share_support = getattr(connection_share, "support_state", SupportState.SUPPORTED)
    if support is SupportState.ABSTAIN or share_support is SupportState.ABSTAIN or pax_value is None or share_value is None:
        return ExpectedConnectingPassengerReference(None, pax_id, share_id, SupportState.ABSTAIN, EvidenceClass.UNSUPPORTED, content_id({"pax": pax_id, "share": share_id, "status": "ABSTAIN"}))
    pax = float(pax_value); share = float(share_value)
    if not (math.isfinite(pax) and pax >= 0 and math.isfinite(share) and 0 <= share <= 1):
        return ExpectedConnectingPassengerReference(None, pax_id, share_id, SupportState.ABSTAIN, EvidenceClass.UNSUPPORTED, content_id({"pax": pax_id, "share": share_id, "status": "INVALID"}))
    lineage = content_id({"expected_pax_reference_id": pax_id, "connection_share_reference_id": share_id, "value": pax * share})
    return ExpectedConnectingPassengerReference(pax * share, pax_id, share_id, SupportState.SUPPORTED, EvidenceClass.DERIVED, lineage)


def connection_share_reference_from_payload(payload: dict[str, Any]) -> ConnectionShareReference:
    cells = tuple(
        ConnectionShareReferenceCell(
            key=tuple(item["key"]),
            connection_share=float(item["connection_share"]),
            total_passenger_weight=float(item["total_passenger_weight"]),
            connecting_passenger_weight=float(item["connecting_passenger_weight"]),
            grain=str(item["grain"]),
            fallback_level=str(item["fallback_level"]),
            sample_size=int(item["sample_size"]),
            support_state=SupportState(item["support_state"]),
            reference_id=str(item["reference_id"]),
            lineage_hash=str(item["lineage_hash"]),
        )
        for item in payload["cells"]
    )
    return ConnectionShareReference(
        reference_id=str(payload["reference_id"]),
        connection_share=(None if payload.get("connection_share") is None else float(payload["connection_share"])),
        total_passenger_weight=float(payload["total_passenger_weight"]),
        connecting_passenger_weight=float(payload["connecting_passenger_weight"]),
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


__all__ = ["ConnectionShareReference", "ConnectionShareReferenceCell", "ExpectedConnectingPassengerReference", "build_connection_share_reference", "derive_expected_connecting_passengers", "connection_share_reference_from_payload"]
