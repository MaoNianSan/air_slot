"""Train-frozen route-level passenger reference for data2 (DB1B Coupon Q1 x10).

Frozen rule: DATA2_PASSENGER_REFERENCE@1.0.0 (user-approved 2026-08-14,
D2-7 option A, data2 scope; "接受推荐"). The H1 variant (D2-10,
user-approved 2026-08-14) is the same construction over the 2019-H1
train window (Q1+Q2 coupon files), registered as
DATA2_PASSENGER_REFERENCE_H1@1.0.0 / D2-PASSENGER-REFERENCE-H1@1.0.0;
the Q1 default is unchanged.
Scientific object: expected number of passengers on a directed route
(origin, destination), estimated from the official BTS DB1B 10% coupon
sample for 2019-Q1. The BTS DB1B program declares a 10% ticket sample;
the registry entry D2-DB1B@1.0.0 records the declared ten-percent scaling
(transformation_rule=declared_ten_percent_scaling) and the local BTS
readme defines the Passengers field as "Number of Passengers".

Construction rule (data2):
    value(route) = SUM(raw Passengers over coupon rows of the route) x 10
    Route key = (Origin, Dest), directed. The reference key never reads
    carrier columns, so the DB1B placeholder carriers `--` / `99` (which
    appear in OpCarrier/TkCarrier, Market OpCarrier 21.5%) do not affect
    route-level aggregation; RPCarrier is clean if carrier-level work is
    ever needed later.
    Statistic: SUM over the official Q1 sample, scaled by the official
    factor 10. No min-cell fallback: the official sample for the quarter
    IS the complete reference (a route absent from the sample has no
    evidence and ABSTAINs; the global median is never used to fabricate a
    route value).
    Evidence: DOMAIN_PROXY (input is the official ticket sample, an
    aggregate proxy for true passenger counts), same ceiling as D2-DB1B.

Lineage: RAW DB1B Coupon rows -> AggregateReference (D2-DB1B) ->
DATA2_PASSENGER_REFERENCE@1.0.0 -> passenger_reference
(FROZEN_REFERENCE) -> M2 (reference), M1 (floor boundary). data1
passenger references are untouched; cross_dataset_reference_overlay=false.

Freeze semantics: the fit manifest freezes the fitted route-level
aggregate table (one record per route: route id + fingerprint over the
route aggregate). The raw coupon files themselves are pinned by
data2/manifests/data2_bts_2019_sha256.csv and the canonical rule D2-DB1B.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import SupportedValue
from model.PRE.transformation import (
    TransformationStatus,
    build_reference_fit_manifest,
    current_transformation_registry,
)

RULE_ID = "DATA2_PASSENGER_REFERENCE"
RULE_VERSION = "1.0.0"
H1_RULE_ID = "DATA2_PASSENGER_REFERENCE_H1"  # D2-10 H1 variant (Q1+Q2 files)
STATISTIC_ID = "SUM_PASSENGERS_X10"
SCALE_FACTOR = 10  # BTS-declared 10% ticket sample -> full-scale proxy
MINIMUM_SUPPORT_RULE = "OFFICIAL_QUARTER_SAMPLE_NO_MIN_CELL"
FALLBACK_HIERARCHY: tuple[str, ...] = ()
APPLICABILITY_SCOPE = "ROUTE_LEVEL"
EXPECTED_REFERENCE_PERIOD_PREFIX = "2019"  # D2-DB1B canonical period

_REQUIRED_ROW_KEYS = (
    "dataset_instance_id",
    "canonical_record_id",
    "join_key",
    "reference_period",
    "value",
    "split",
)


@dataclass(frozen=True)
class Data2PassengerReferenceCell:
    origin_airport_id: str
    destination_airport_id: str
    value_passengers: float
    sample_count: int
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class Data2PassengerReference:
    reference_id: str
    dataset_instance_id: str
    rule_id: str
    rule_version: str
    fit_period: str
    statistic_id: str
    scale_factor: int
    minimum_support_rule: str
    fallback_hierarchy: tuple[str, ...]
    applicability_scope: str
    total_passengers: float
    total_sample_count: int
    route_count: int
    cells: tuple[Data2PassengerReferenceCell, ...]
    manifest_freeze_id: str
    support_state: SupportState
    reason_code: str

    def _period_label(self) -> str:
        """Fit-window label for quality flags: H1 for the D2-10 variant, Q1 otherwise."""
        return "H1" if self.rule_id == H1_RULE_ID else "Q1"

    def lookup(self, origin_airport_id: str, destination_airport_id: str) -> SupportedValue:
        """Frozen-reference lookup at decision time by directed route.

        Routes present in the official sample (Q1 or H1/Q1+Q2 fit window,
        D2-PASSENGER-REFERENCE / D2-PASSENGER-REFERENCE-H1) resolve to the
        scaled sum; routes with no DB1B coupon evidence ABSTAIN (value None),
        never fabricated from a global statistic.
        """
        cell = next(
            (item for item in self.cells
             if item.origin_airport_id == origin_airport_id
             and item.destination_airport_id == destination_airport_id),
            None,
        )
        period = self._period_label()
        if cell is None:
            return SupportedValue(
                value=None,
                unit="passengers",
                evidence_class=EvidenceClass.DOMAIN_PROXY,
                support_ceiling=EvidenceClass.DOMAIN_PROXY,
                support_state=SupportState.ABSTAIN,
                reason_code="NO_DB1B_COUPON_ROUTE_EVIDENCE",
                quality_flags=(f"REFERENCE_SOURCE_DB1B_COUPON_{period}",),
            )
        sum_label = "QUARTER" if period == "Q1" else "H1"
        return SupportedValue(
            value=cell.value_passengers,
            unit="passengers",
            evidence_class=EvidenceClass.DOMAIN_PROXY,
            support_ceiling=EvidenceClass.DOMAIN_PROXY,
            support_state=SupportState.SUPPORTED,
            reason_code=f"DB1B_COUPON_OFFICIAL_10PCT_X10;ROUTE_{sum_label}_SUM",
            quality_flags=tuple(
                sorted(
                    (
                        "REFERENCE_LEVEL_ROUTE",
                        f"REFERENCE_SOURCE_DB1B_COUPON_{period}",
                        f"REFERENCE_ROUTE_N={cell.sample_count}",
                    )
                )
            ),
        )


def _route_key(row: dict[str, Any]) -> tuple[str, str]:
    join_key = row.get("join_key")
    if not isinstance(join_key, dict):
        raise ContractError("REFERENCE_ROW_MISSING:join_key")
    origin = str(join_key.get("origin", "")).strip()
    destination = str(join_key.get("destination", "")).strip()
    if not origin or not destination:
        raise ContractError("REFERENCE_ROW_MISSING:join_key")
    return origin, destination


def build_data2_passenger_reference(
    rows: list[dict[str, Any]],
    *,
    fit_period: str,
    dataset_instance_id: str = "data2_2019",
    scale_factor: int = SCALE_FACTOR,
    statistic_id: str = STATISTIC_ID,
    rule_id: str = RULE_ID,
    rule_version: str = RULE_VERSION,
) -> Data2PassengerReference:
    """Fit the data2 train-frozen route-level passenger reference.

    Rows must be AggregateReference-shaped dicts as produced by D2-DB1B
    (join_key={"origin": ..., "destination": ...}, value=raw Passengers,
    reference_period="2019", canonical_record_id) plus a "split" key; only
    split == "train" rows are used. Carrier columns are never read, so
    DB1B placeholder carriers do not affect the route reference. Rows may
    carry an optional "record_count" (number of coupon rows aggregated
    into this row) so the full-Q1 probe can pre-aggregate per route
    without materialising millions of row dicts; default is 1.
    """
    for row in rows:
        for key in _REQUIRED_ROW_KEYS:
            if key not in row or row[key] in (None, ""):
                raise ContractError(f"REFERENCE_ROW_MISSING:{key}")
        if not isinstance(row.get("value"), (int, float)):
            raise ContractError("REFERENCE_ROW_MISSING:value")
        period = str(row["reference_period"])
        if not period.startswith(EXPECTED_REFERENCE_PERIOD_PREFIX):
            raise ContractError("REFERENCE_PERIOD_MISMATCH")
    datasets = {row["dataset_instance_id"] for row in rows}
    if datasets != {dataset_instance_id}:
        raise ContractError("REFERENCE_DATASET_MISMATCH")

    rule = current_transformation_registry().get(rule_id, rule_version)
    if rule.status is not TransformationStatus.FROZEN:
        raise ContractError("CONSTRUCTION_RULE_NOT_FROZEN")

    training_rows = [row for row in rows if row["split"] == "train"]
    if not training_rows:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")

    aggregates: dict[tuple[str, str], list[float]] = defaultdict(list)
    record_counts: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in training_rows:
        origin, destination = _route_key(row)
        aggregates[(origin, destination)].append(float(row["value"]))
        count = row.get("record_count", 1)
        if not isinstance(count, int) or count < 1:
            raise ContractError("REFERENCE_ROW_MISSING:record_count")
        record_counts[(origin, destination)].append(count)

    if not aggregates:
        raise ContractError("REFERENCE_TRAIN_PARTITION_EMPTY")

    cell_records: list[Data2PassengerReferenceCell] = []
    manifest_records: list[dict[str, Any]] = []
    total_passengers = 0.0
    total_sample_count = 0
    for (origin, destination) in sorted(aggregates):
        raw_sum = sum(aggregates[(origin, destination)])
        scaled = raw_sum * scale_factor
        n = sum(record_counts[(origin, destination)])
        total_passengers += scaled
        total_sample_count += n
        cell_records.append(
            Data2PassengerReferenceCell(
                origin_airport_id=origin,
                destination_airport_id=destination,
                value_passengers=scaled,
                sample_count=n,
                provenance=(
                    f"route={origin}|{destination}",
                    f"n_coupon_records={n}",
                    f"raw_passenger_sum={raw_sum:g}",
                    f"scale_factor={scale_factor}",
                    f"{RULE_ID}@{RULE_VERSION}",
                ),
            )
        )
        manifest_records.append(
            {
                "record_id": content_id({"origin": origin, "destination": destination}),
                "source_fingerprint": content_id(
                    {
                        "origin": origin,
                        "destination": destination,
                        "raw_passenger_sum": raw_sum,
                        "record_count": n,
                    }
                ),
                "split": "train",
            }
        )

    manifest = build_reference_fit_manifest(
        manifest_records,
        rule=rule,
        fit_period=fit_period,
        grouping_keys=("origin_airport_id", "destination_airport_id"),
        statistic_id=statistic_id,
        minimum_support_rule=MINIMUM_SUPPORT_RULE,
        fallback_hierarchy=FALLBACK_HIERARCHY,
        applicability_scope=APPLICABILITY_SCOPE,
    )

    reference_id = content_id(
        {
            "rule": f"{rule_id}@{rule_version}",
            "dataset_instance_id": dataset_instance_id,
            "fit_period": fit_period,
            "statistic_id": statistic_id,
            "scale_factor": scale_factor,
            "minimum_support_rule": manifest.minimum_support_rule,
            "fallback_hierarchy": FALLBACK_HIERARCHY,
            "total_passengers": total_passengers,
            "total_sample_count": total_sample_count,
            "cells": [
                {
                    "origin": item.origin_airport_id,
                    "destination": item.destination_airport_id,
                    "value_passengers": item.value_passengers,
                    "sample_count": item.sample_count,
                }
                for item in cell_records
            ],
            "freeze_id": manifest.freeze_id,
        }
    )

    return Data2PassengerReference(
        reference_id=reference_id,
        dataset_instance_id=dataset_instance_id,
        rule_id=rule_id,
        rule_version=rule_version,
        fit_period=fit_period,
        statistic_id=statistic_id,
        scale_factor=scale_factor,
        minimum_support_rule=manifest.minimum_support_rule,
        fallback_hierarchy=manifest.fallback_hierarchy,
        applicability_scope=APPLICABILITY_SCOPE,
        total_passengers=total_passengers,
        total_sample_count=total_sample_count,
        route_count=len(cell_records),
        cells=tuple(cell_records),
        manifest_freeze_id=manifest.freeze_id,
        support_state=SupportState.SUPPORTED,
        reason_code="DB1B_COUPON_OFFICIAL_10PCT_X10",
    )


def _require(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise ContractError(f"REFERENCE_PAYLOAD_MISSING:{key}")
    return payload[key]


def data2_passenger_reference_from_payload(
    payload: dict[str, Any],
) -> Data2PassengerReference:
    """Reuse an existing train-frozen passenger payload without refitting."""
    cells = tuple(
        Data2PassengerReferenceCell(
            origin_airport_id=item["origin"],
            destination_airport_id=item["destination"],
            value_passengers=float(item["value_passengers"]),
            sample_count=int(item["sample_count"]),
            provenance=tuple(item.get("provenance", ())),
        )
        for item in _require(payload, "cells")
    )
    cells_count = payload.get("cells_count")
    if cells_count is not None and int(cells_count) != len(cells):
        raise ContractError("REFERENCE_PAYLOAD_CELL_COUNT_MISMATCH")
    return Data2PassengerReference(
        reference_id=_require(payload, "reference_id"),
        dataset_instance_id=payload.get("dataset_instance_id", "data2_2019"),
        rule_id=_require(payload, "rule_id"),
        rule_version=_require(payload, "rule_version"),
        fit_period=_require(payload, "fit_period"),
        statistic_id=payload.get("statistic_id", STATISTIC_ID),
        scale_factor=int(payload.get("scale_factor", SCALE_FACTOR)),
        minimum_support_rule=payload.get(
            "minimum_support_rule", MINIMUM_SUPPORT_RULE
        ),
        fallback_hierarchy=tuple(
            payload.get("fallback_hierarchy", FALLBACK_HIERARCHY)
        ),
        applicability_scope=payload.get(
            "applicability_scope", APPLICABILITY_SCOPE
        ),
        total_passengers=float(_require(payload, "total_passengers")),
        total_sample_count=int(_require(payload, "total_sample_count")),
        route_count=int(payload.get("route_count", len(cells))),
        cells=cells,
        manifest_freeze_id=_require(payload, "manifest_freeze_id"),
        support_state=SupportState(_require(payload, "support_state")),
        reason_code=payload.get(
            "reason_code", "DB1B_COUPON_OFFICIAL_10PCT_X10"
        ),
    )
