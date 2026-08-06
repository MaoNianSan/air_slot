from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..contracts import M1PredictionBundle, M1SnapshotNode, StateCommitStatus
from .state_store import InMemoryStateStore, StateEntry


class SnapshotSequenceProvider(Protocol):
    def ordered_snapshots(
        self,
        episode_id: str,
        *,
        up_to_query_time: datetime,
    ) -> tuple[M1SnapshotNode, ...]:
        ...


class ReplayPredictor(Protocol):
    def predict_snapshot(
        self,
        snapshot: M1SnapshotNode,
        previous_hidden: tuple[float, ...] | None,
        status: StateCommitStatus,
        *,
        trigger_type: str,
        replay_reason: str | None,
        replay_node_count: int,
    ) -> M1PredictionBundle:
        ...

    def state_entry(
        self,
        snapshot: M1SnapshotNode,
        prediction: M1PredictionBundle,
        trigger_type: str,
    ) -> StateEntry:
        ...


@dataclass(frozen=True)
class ReplayResult:
    reason: str
    replay_start_snapshot_id: str
    replay_end_snapshot_id: str
    replayed_node_count: int
    previous_state_hash: str | None
    final_state_hash: str
    final_prediction: M1PredictionBundle


def revision_reason(
    entries: tuple[StateEntry, ...],
    incoming: M1SnapshotNode,
) -> str | None:
    for entry in entries:
        current = entry.snapshot
        if (
            current.query_time == incoming.query_time
            and incoming.snapshot_version > current.snapshot_version
        ):
            return "SNAPSHOT_VERSION_INCREASED"
        if (
            current.query_time == incoming.query_time
            and incoming.information_cutoff != current.information_cutoff
        ):
            return "SNAPSHOT_EVIDENCE_REVISED"
    latest = entries[-1] if entries else None
    if latest is not None and incoming.query_time < latest.snapshot.query_time:
        return "HISTORICAL_QUERY_REVISED"
    return None


def replay_episode(
    episode_id: str,
    revised_from: datetime,
    up_to_query_time: datetime,
    snapshot_provider: SnapshotSequenceProvider,
    state_store: InMemoryStateStore,
    model: ReplayPredictor,
    *,
    reason: str,
    status: StateCommitStatus,
    replacement_snapshot: M1SnapshotNode | None = None,
) -> ReplayResult:
    previous = state_store.latest_before(episode_id, revised_from)
    snapshots = list(
        snapshot_provider.ordered_snapshots(
            episode_id,
            up_to_query_time=up_to_query_time,
        )
    )
    if replacement_snapshot is not None:
        snapshots = [
            replacement_snapshot
            if node.query_time == replacement_snapshot.query_time
            else node
            for node in snapshots
        ]
    replay_nodes = tuple(
        node
        for node in snapshots
        if revised_from <= node.query_time <= up_to_query_time
    )
    if not replay_nodes:
        raise ValueError("M1_REPLAY_SEQUENCE_EMPTY")
    hidden = previous.prediction.hidden_state if previous is not None else None
    replayed_entries: list[StateEntry] = []
    final_prediction: M1PredictionBundle | None = None
    for index, snapshot in enumerate(replay_nodes, start=1):
        final_prediction = model.predict_snapshot(
            snapshot,
            hidden,
            status,
            trigger_type="REPLAY",
            replay_reason=reason,
            replay_node_count=index,
        )
        hidden = final_prediction.hidden_state
        replayed_entries.append(
            model.state_entry(snapshot, final_prediction, "REPLAY")
        )
    state_store.replace_replayed_entries(
        episode_id,
        revised_from,
        tuple(replayed_entries),
    )
    if final_prediction is None:
        raise ValueError("M1_REPLAY_FINAL_PREDICTION_MISSING")
    return ReplayResult(
        reason=reason,
        replay_start_snapshot_id=replay_nodes[0].snapshot_id,
        replay_end_snapshot_id=replay_nodes[-1].snapshot_id,
        replayed_node_count=len(replay_nodes),
        previous_state_hash=previous.hidden_state_hash if previous is not None else None,
        final_state_hash=replayed_entries[-1].hidden_state_hash,
        final_prediction=final_prediction,
    )
