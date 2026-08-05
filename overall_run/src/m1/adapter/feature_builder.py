from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import pandas as pd

from ..contracts import M1InputBundle
from .availability import IDENTITY_COLUMNS, available_observations, latest_values
from .bundle_loader import PublishedPreBundle
from .stage_builder import available_events, flight_chain_stage
from .target_builder import build_target_contracts


def _allowed(registry: tuple[dict[str, Any], ...], table: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(row.get("standard_column") or row.get("column"))
                for row in registry
                if str(row.get("table")) == table
                and bool(row.get("model_input_allowed"))
                and str(row.get("standard_column") or row.get("column"))
                not in IDENTITY_COLUMNS
            }
        )
    )


def _numeric(value: object) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if pd.notna(converted) else None


def _evidence(bundle: PublishedPreBundle, names: tuple[str, ...]) -> tuple[dict[str, str], dict[str, str]]:
    audit = bundle.evidence_audit
    evidence: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for name in names:
        rows = audit[audit.get("variable_name", pd.Series(dtype=str)).astype(str).eq(name)]
        if rows.empty:
            evidence[name] = "MISSING_EVIDENCE_AUDIT"
            fallback[name] = "MISSING"
        else:
            row = rows.iloc[-1]
            evidence[name] = str(row.get("support_level", "UNSPECIFIED"))
            fallback[name] = str(row.get("fallback_level", "NONE"))
    return evidence, fallback


def _episode_events(episode: pd.Series, events: pd.DataFrame) -> pd.DataFrame:
    flight_ids = {
        str(episode.get("predecessor_flight_id", "")),
        str(episode.get("successor_flight_id", "")),
    }
    flight_ids -= {"", "<NA>", "nan", "None"}
    if not flight_ids or "flight_id" not in events:
        return events.iloc[0:0].copy()
    return events[events["flight_id"].astype(str).isin(flight_ids)].copy()


def _sequence(frame: pd.DataFrame, allowed: tuple[str, ...], query: pd.Timestamp) -> tuple[dict[str, float], ...]:
    rows: list[dict[str, float]] = []
    for _, source in frame.sort_values("availability_time", kind="mergesort").iterrows():
        record: dict[str, float] = {
            "delta_to_query_minutes": max(
                (query - pd.Timestamp(source["availability_time"])).total_seconds() / 60.0,
                0.0,
            )
        }
        for name in allowed:
            value = _numeric(source.get(name))
            record[name] = 0.0 if value is None else value
            record[f"mask__{name}"] = 0.0 if value is None else 1.0
        rows.append(record)
    return tuple(rows)


def build_input_bundle(
    bundle: PublishedPreBundle,
    episode_id: str,
    query_time: object,
    *,
    snapshot_id: str | None = None,
    snapshot_version: int = 1,
    previous_query_time: object | None = None,
    state_reset_signal: bool = False,
) -> M1InputBundle:
    episodes = bundle.episodes[
        bundle.episodes["chain_episode_id"].astype(str).eq(str(episode_id))
    ]
    if len(episodes) != 1:
        raise ValueError("M1_EPISODE_ID_NOT_UNIQUE")
    episode = episodes.iloc[0]
    query = pd.Timestamp(query_time)
    query = query.tz_localize("UTC") if query.tzinfo is None else query.tz_convert("UTC")
    observations = available_observations(
        bundle.observations,
        bundle.observation_membership,
        str(episode_id),
        query,
    )
    allowed_dynamic = _allowed(bundle.column_registry, "observations")
    latest = latest_values(observations, allowed_dynamic)
    current: dict[str, float] = {}
    masks: dict[str, bool] = {}
    for name in allowed_dynamic:
        value = _numeric(latest.get(name, {}).get("value"))
        current[name] = 0.0 if value is None else value
        masks[name] = value is not None
    episode_events = _episode_events(episode, bundle.events)
    visible_events = available_events(episode_events, query)
    cutoffs = list(pd.to_datetime(observations.get("availability_time", []), utc=True))
    cutoffs.extend(pd.to_datetime(visible_events.get("availability_time", []), utc=True))
    cutoff = max(cutoffs) if cutoffs else query
    cutoff = min(pd.Timestamp(cutoff), query)
    static_allowed = _allowed(bundle.column_registry, "episodes")
    static = {name: episode.get(name) for name in static_allowed if name in episode.index}
    evidence, fallback = _evidence(bundle, allowed_dynamic)
    identifier = snapshot_id or hashlib.sha256(
        f"{episode_id}|{query.isoformat()}".encode("utf-8")
    ).hexdigest()[:24]
    previous = query if previous_query_time is None else pd.Timestamp(previous_query_time)
    previous = previous.tz_localize("UTC") if previous.tzinfo is None else previous.tz_convert("UTC")
    observed_mask = {
        str(name): True
        for name in visible_events["event_name"].astype(str).unique()
    }
    return M1InputBundle(
        episode_id=str(episode_id),
        snapshot_id=identifier,
        snapshot_version=int(snapshot_version),
        query_time=query.to_pydatetime(),
        information_cutoff=cutoff.to_pydatetime(),
        pre_bundle_identity=bundle.identity,
        flight_chain_stage=flight_chain_stage(episode, bundle.events, query),
        current_features=current,
        sequence_features=_sequence(observations, allowed_dynamic, query),
        static_features=static,
        masks=masks,
        delta_t_minutes=max((query - previous).total_seconds() / 60.0, 0.0),
        evidence_status=evidence,
        fallback_status=fallback,
        target_contracts=build_target_contracts(episode, episode_events),
        observed_event_mask=observed_mask,
        state_reset_signal=bool(state_reset_signal),
    )
