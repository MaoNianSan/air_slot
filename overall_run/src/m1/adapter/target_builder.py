from __future__ import annotations

from typing import Any

import pandas as pd

from ..contracts import M1SupportLevel, OperationalReferences, TargetContract


TARGETS = ("R_IB", "R_OB", "T_TX")


def _event_details(row: pd.Series | None) -> dict[str, object]:
    if row is None:
        return {}
    return {
        key: row.get(key)
        for key in (
            "event_id",
            "support_level",
            "reconstruction_method",
            "confidence",
            "source_hash",
        )
    }


def _event(events: pd.DataFrame, flight_id: object, event_name: str) -> pd.Series | None:
    rows = events[
        events["flight_id"].astype(str).eq(str(flight_id))
        & events["event_name"].astype(str).eq(event_name)
    ]
    if rows.empty:
        return None
    ordered = rows.copy()
    ordered["_availability_order"] = pd.to_datetime(
        ordered.get("availability_time"), utc=True, errors="coerce"
    )
    ordered["_event_order"] = pd.to_datetime(
        ordered.get("event_time"), utc=True, errors="coerce"
    )
    return ordered.sort_values(
        ["_availability_order", "_event_order"], kind="mergesort"
    ).iloc[-1]


def _utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _support(event_rows: list[pd.Series | None], chain_support: str) -> str:
    if any(row is None or str(row.get("support_level")) == "UNSUPPORTED" for row in event_rows):
        return M1SupportLevel.UNSUPPORTED.value
    levels = {str(row.get("support_level")) for row in event_rows if row is not None}
    if levels == {"OFFICIAL_OBSERVED"} and chain_support == "OFFICIAL_ROTATION":
        return M1SupportLevel.OFFICIAL_OPERATIONAL.value
    if levels.issubset({"OFFICIAL_OBSERVED", "RECONSTRUCTED_HIGH"}) and chain_support in {
        "OFFICIAL_ROTATION",
        "SCHEDULE_AIRCRAFT_MATCH",
        "RECONSTRUCTED_CHAIN",
    }:
        return M1SupportLevel.INFERRED_OPERATIONAL.value
    if not levels & {"UNSUPPORTED"} and chain_support != "UNSUPPORTED":
        return M1SupportLevel.OBSERVED_CHAIN_PROXY.value
    return M1SupportLevel.UNSUPPORTED.value


def build_target_contracts(
    episode: pd.Series,
    events: pd.DataFrame,
    operational_references: OperationalReferences | None = None,
) -> dict[str, TargetContract]:
    predecessor = episode.get("predecessor_flight_id")
    successor = episode.get("successor_flight_id")
    chain_support = str(episode.get("chain_support_level", "UNSUPPORTED"))
    ib = _event(events, predecessor, "AIBT_MINUS")
    ob = _event(events, successor, "AOBT_PLUS")
    tx = _event(events, successor, "ATOT_PLUS")
    schedule_supported = bool(
        operational_references is not None
        and operational_references.successor_sobt.active
        and operational_references.turnaround_floor_minutes.active
    )
    specifications: dict[str, tuple[str, list[pd.Series | None], bool, str]] = {
        "R_IB": ("remaining time to predecessor in-block", [ib], ib is not None, "AIBT_MINUS-query_time"),
        "R_OB": (
            "successor extra off-block waiting after earliest feasible off-block",
            [ib, ob],
            ib is not None and ob is not None and schedule_supported,
            "AOBT_PLUS-max(SOBT,AIBT_MINUS+turnaround_floor)",
        ),
        "T_TX": ("successor actual taxi time", [ob, tx], ob is not None and tx is not None, "ATOT_PLUS-AOBT_PLUS"),
    }
    result: dict[str, TargetContract] = {}
    for name, (semantics, rows, prerequisites, reference) in specifications.items():
        support = _support(rows, chain_support) if prerequisites else M1SupportLevel.UNSUPPORTED.value
        active = prerequisites and support != M1SupportLevel.UNSUPPORTED.value
        inactive = None if active else "REQUIRED_OPERATIONAL_EVIDENCE_OR_SCHEDULE_FIELD_MISSING"
        result[name] = TargetContract(
            target_name=name,
            target_semantics=semantics,
            active=active,
            m1_support_level=support,
            pre_event_support_levels={
                str(row.get("event_name")): str(row.get("support_level"))
                for row in rows
                if row is not None
            },
            chain_support_level=chain_support,
            target_reference=reference if active else None,
            target_units="minutes",
            target_time_uncertainty_seconds=None,
            inactive_reason=inactive,
            event_details={
                str(row.get("event_name")): _event_details(row)
                for row in rows
                if row is not None
            },
        )
    return result


def target_values(
    episode: pd.Series,
    events: pd.DataFrame,
    query_time: object,
    operational_references: OperationalReferences,
) -> dict[str, float | None]:
    contracts = build_target_contracts(episode, events, operational_references)
    query = pd.Timestamp(query_time)
    query = query.tz_localize("UTC") if query.tzinfo is None else query.tz_convert("UTC")
    ib = _event(events, episode.get("predecessor_flight_id"), "AIBT_MINUS")
    ob = _event(events, episode.get("successor_flight_id"), "AOBT_PLUS")
    tx = _event(events, episode.get("successor_flight_id"), "ATOT_PLUS")
    values: dict[str, float | None] = {name: None for name in TARGETS}
    if contracts["R_IB"].active and ib is not None:
        values["R_IB"] = max((_utc(ib["event_time"]) - query).total_seconds() / 60.0, 0.0)
    if contracts["R_OB"].active and ib is not None and ob is not None:
        sobt = _utc(operational_references.successor_sobt.value)
        turnaround = float(operational_references.turnaround_floor_minutes.value)
        earliest = max(
            sobt,
            _utc(ib["event_time"]) + pd.Timedelta(minutes=turnaround),
        )
        values["R_OB"] = max((_utc(ob["event_time"]) - earliest).total_seconds() / 60.0, 0.0)
    if contracts["T_TX"].active and ob is not None and tx is not None:
        values["T_TX"] = max((_utc(tx["event_time"]) - _utc(ob["event_time"])).total_seconds() / 60.0, 0.0)
    return values
