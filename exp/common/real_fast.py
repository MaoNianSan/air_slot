"""Shared real-Data2 FAST helpers with explicit scientific gates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from time import perf_counter

from exp.common.context import ExecutionTier, ExperimentContext
from exp.common.replay import (
    EpisodeReplaySelector,
    ReplayAvailabilitySemantics,
    ReplayDecisionRecord,
    ReplayEpisodeRecord,
    ReplayEpisodeRegistry,
    ReplaySelectionStatus,
)


def assert_real_fast_context(context: ExperimentContext) -> None:
    if context.execution_tier is not ExecutionTier.REAL_DATA_FAST:
        raise ValueError("REAL_FAST_CONTEXT_REQUIRED")
    if context.dataset_id != "DATA2" or context.split != "DEVELOPMENT":
        raise ValueError("REAL_FAST_DATA2_DEVELOPMENT_REQUIRED")
    if context.final_test_access_count != 0 or context.paper_full_run:
        raise ValueError("REAL_FAST_SAFETY_BOUNDARY_VIOLATION")
    if not context.cohort:
        raise ValueError("REAL_FAST_COHORT_REQUIRED")


def blocked_gate(context: ExperimentContext, *keys: str) -> str | None:
    for key in keys:
        value = context.shared_gates.get(key)
        if value and not value.startswith(("READY", "FROZEN", "SUPPORTED")):
            return f"{key}:{value}"
    return None


def m4_result_unit(context: ExperimentContext) -> str:
    """Keep experiment diagnostics below the un-frozen currency boundary."""
    del context
    return "CONSTRUCTED_LOSS_UNIT"


def replay_registry(context: ExperimentContext) -> ReplayEpisodeRegistry:
    """Materialize a typed replay registry only from frozen PRE decision nodes."""
    assert_real_fast_context(context)
    by_episode: dict[str, list[dict]] = defaultdict(list)
    for node in context.cohort:
        by_episode[str(node["episode_id"])].append(dict(node))
    episodes = []
    for episode_id, nodes in sorted(by_episode.items()):
        records = []
        for node in sorted(nodes, key=lambda item: (item["decision_time"], item["decision_node_id"])):
            cutoff = datetime.fromisoformat(str(node["information_cutoff"]).replace("Z", "+00:00"))
            records.append(ReplayDecisionRecord(
                decision_node_id=str(node["decision_node_id"]),
                decision_time=datetime.fromisoformat(str(node["decision_time"]).replace("Z", "+00:00")),
                information_cutoff=cutoff,
                legal_record_ids=tuple(str(value) for value in node["legal_record_ids"]),
                availability_time_semantics=(
                    ReplayAvailabilitySemantics.PREVALIDATED_LEGAL_AT_CUTOFF
                ),
                # PRE already proved these record identities legal at cutoff.
                # No observed airline-message arrival time exists in Data2.
                legal_record_availability_times=(),
            ))
        episodes.append(ReplayEpisodeRecord(
            episode_id=episode_id,
            split_id=context.split,
            scenario_lineage=(context.scenario_hash,),
            decision_records=tuple(records),
        ))
    return ReplayEpisodeRegistry(
        dataset_id=context.dataset_id,
        source_dataset_id="data2_2019",
        dataset_version="DATA2_2019_DEVELOPMENT_AUG_SEP_CURRENT_STAGE_V2",
        source_manifest_hash=str(context.pre_binding["source_manifest_hash"]),
        pre_schema_version="AIR_SLOT_EXP2_DATA2_DEVELOPMENT_CURRENT_STAGE_COHORT_V2",
        episodes=tuple(episodes),
    )


def select_replay(context: ExperimentContext):
    registry = replay_registry(context)
    result = EpisodeReplaySelector().select(
        registry,
        episode_ids=tuple(item.episode_id for item in registry.episodes),
        expected_split=context.split,
    )
    if result.status is not ReplaySelectionStatus.READY:
        raise RuntimeError("REAL_FAST_REPLAY_SELECTION_BLOCKED")
    return registry, result


def state_vintage_bindings(context: ExperimentContext, *, lag_minutes: int) -> tuple[dict, ...]:
    """Select prior state identities; a lagged variant never falls back to current."""
    if lag_minutes < 0:
        raise ValueError("REAL_FAST_LAG_MUST_BE_NONNEGATIVE")
    registry, _ = select_replay(context)
    output = []
    for episode in registry.episodes:
        rows = episode.decision_records
        for current in rows:
            latest_allowed = current.decision_time - timedelta(minutes=lag_minutes)
            eligible = tuple(item for item in rows if item.decision_time <= latest_allowed)
            source = eligible[-1] if eligible else None
            output.append({
                "episode_id": episode.episode_id,
                "decision_node_id": current.decision_node_id,
                "lag_minutes": lag_minutes,
                "state_vintage_node_id": None if source is None else source.decision_node_id,
                "state_vintage_time": None if source is None else source.decision_time.isoformat(),
                "current_state_read": lag_minutes == 0,
            })
    return tuple(output)


def replay_latency_seconds(context: ExperimentContext, *, repeats: int = 7) -> tuple[float, ...]:
    if repeats < 1:
        raise ValueError("REAL_FAST_LATENCY_REPEATS_REQUIRED")
    values = []
    for _ in range(repeats):
        started = perf_counter()
        select_replay(context)
        values.append(perf_counter() - started)
    return tuple(values)


__all__ = [
    "assert_real_fast_context", "blocked_gate", "m4_result_unit", "replay_latency_seconds",
    "replay_registry", "select_replay", "state_vintage_bindings",
]
