from __future__ import annotations

import hashlib
import math

import pandas as pd

from ..contracts import M1SnapshotNode
from .availability import available_observations, latest_values
from .bundle_loader import PublishedPreBundle
from .feature_schema import M1FeatureSchema
from .operational_references import build_operational_references
from .stage_builder import available_events, flight_chain_stage
from .target_builder import build_target_contracts


def _utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def _numeric(value: object) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _episode_events(bundle: PublishedPreBundle, episode: pd.Series) -> pd.DataFrame:
    flight_ids = {
        str(episode.get("predecessor_flight_id", "")),
        str(episode.get("successor_flight_id", "")),
    } - {"", "<NA>", "nan", "None"}
    return bundle.events[
        bundle.events.get("flight_id", pd.Series(dtype=str)).astype(str).isin(flight_ids)
    ].copy()


def _evidence(
    bundle: PublishedPreBundle,
    names: tuple[str, ...],
) -> tuple[dict[str, str], dict[str, str]]:
    evidence: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for name in names:
        rows = bundle.evidence_audit[
            bundle.evidence_audit.get("variable_name", pd.Series(dtype=str))
            .astype(str)
            .eq(name)
        ]
        if rows.empty:
            evidence[name] = "MISSING_EVIDENCE_AUDIT"
            fallback[name] = "MISSING"
            continue
        row = rows.iloc[-1]
        evidence[name] = str(row.get("support_level", "UNSPECIFIED"))
        fallback[name] = str(row.get("fallback_level", "NONE"))
    return evidence, fallback


def build_snapshot_node(
    bundle: PublishedPreBundle,
    episode_id: str,
    query_time: object,
    feature_schema: M1FeatureSchema,
    *,
    snapshot_version: int = 1,
    previous_query_time: object | None = None,
    state_reset_signal: bool = False,
    stale_after_minutes: float = 30.0,
) -> M1SnapshotNode:
    episodes = bundle.episodes[
        bundle.episodes["chain_episode_id"].astype(str).eq(str(episode_id))
    ]
    if len(episodes) != 1:
        raise ValueError("M1_EPISODE_ID_NOT_UNIQUE")
    episode = episodes.iloc[0]
    query = _utc(query_time)
    observations = available_observations(
        bundle.observations,
        bundle.observation_membership,
        str(episode_id),
        query,
    )
    latest = latest_values(observations, feature_schema.value_features)
    evidence, fallback_status = _evidence(bundle, feature_schema.value_features)
    values: dict[str, float] = {}
    masks: dict[str, bool] = {}
    ages: dict[str, float] = {}
    stale: dict[str, bool] = {}
    fallback: dict[str, bool] = {}
    for name in feature_schema.value_features:
        value = _numeric(latest.get(name, {}).get("value"))
        age = _numeric(latest.get(name, {}).get("age_minutes"))
        values[name] = 0.0 if value is None else value
        masks[name] = value is not None
        ages[name] = 0.0 if age is None else age
        stale[name] = age is None or age > stale_after_minutes
        fallback[name] = fallback_status[name] not in {"", "NONE", "EXACT_CELL"}
    static: dict[str, float] = {}
    for name in feature_schema.static_features:
        value = _numeric(episode.get(name))
        static[name] = float("nan") if value is None else value
    episode_events = _episode_events(bundle, episode)
    visible_events = available_events(episode_events, query)
    stage = flight_chain_stage(episode, episode_events, query)
    previous = query if previous_query_time is None else _utc(previous_query_time)
    delta = max((query - previous).total_seconds() / 60.0, 0.0)
    vector = feature_schema.encode(
        values=values,
        masks=masks,
        ages=ages,
        stale=stale,
        fallback=fallback,
        stage=stage,
        delta_t_minutes=delta,
        static=static,
    )
    cutoff_values = list(
        pd.to_datetime(observations.get("availability_time", []), utc=True)
    ) + list(pd.to_datetime(visible_events.get("availability_time", []), utc=True))
    cutoff = min(max(cutoff_values) if cutoff_values else query, query)
    identifier = hashlib.sha256(
        (
            f"{episode_id}|{query.isoformat()}|{snapshot_version}|"
            f"{bundle.identity.pre_manifest_hash}|{feature_schema.schema_hash}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    selected_ids = {
        str(record.get("observation_id"))
        for record in latest.values()
        if record.get("observation_id") is not None
    }
    operational = build_operational_references(episode, visible_events)
    return M1SnapshotNode(
        episode_id=str(episode_id),
        snapshot_id=identifier,
        snapshot_version=int(snapshot_version),
        query_time=query.to_pydatetime(),
        information_cutoff=_utc(cutoff).to_pydatetime(),
        pre_bundle_identity=bundle.identity,
        feature_vector=vector,
        feature_schema_hash=feature_schema.schema_hash,
        source_observation_ids=tuple(sorted(selected_ids)),
        evidence_status=evidence,
        fallback_status=fallback_status,
        flight_chain_stage=stage,
        observed_event_mask={
            str(name): True
            for name in visible_events.get("event_name", pd.Series(dtype=str))
            .astype(str)
            .unique()
        },
        target_contracts=build_target_contracts(episode, episode_events, operational),
        operational_references=operational,
        state_reset_signal=bool(state_reset_signal),
    )
