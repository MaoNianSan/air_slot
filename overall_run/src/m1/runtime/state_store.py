from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..contracts import M1PredictionBundle, M1SnapshotNode, StateCommitStatus


@dataclass(frozen=True)
class StateWatermark:
    episode_id: str
    latest_snapshot_id: str
    latest_snapshot_version: int
    latest_query_time: datetime
    latest_information_cutoff: datetime
    latest_hidden_state: tuple[float, ...]
    feature_schema_hash: str
    pre_manifest_hash: str
    model_artifact_hash: str
    temperature_artifact_hash: str
    state_commit_status: StateCommitStatus


@dataclass(frozen=True)
class StateEntry:
    snapshot: M1SnapshotNode
    prediction: M1PredictionBundle
    feature_schema_hash: str
    pre_manifest_hash: str
    model_artifact_hash: str
    temperature_artifact_hash: str
    snapshot_vector_hash: str
    hidden_state_hash: str
    trigger_type: str
    committed_at: datetime

    @property
    def key(self) -> tuple[str, str, int, str, str, str, str]:
        return (
            self.snapshot.episode_id,
            self.snapshot.snapshot_id,
            self.snapshot.snapshot_version,
            self.pre_manifest_hash,
            self.feature_schema_hash,
            self.model_artifact_hash,
            self.temperature_artifact_hash,
        )

    @classmethod
    def committed(
        cls,
        *,
        snapshot: M1SnapshotNode,
        prediction: M1PredictionBundle,
        model_artifact_hash: str,
        temperature_artifact_hash: str,
        snapshot_vector_hash: str,
        hidden_state_hash: str,
        trigger_type: str,
    ) -> "StateEntry":
        return cls(
            snapshot=snapshot,
            prediction=prediction,
            feature_schema_hash=snapshot.feature_schema_hash,
            pre_manifest_hash=snapshot.pre_bundle_identity.pre_manifest_hash,
            model_artifact_hash=model_artifact_hash,
            temperature_artifact_hash=temperature_artifact_hash,
            snapshot_vector_hash=snapshot_vector_hash,
            hidden_state_hash=hidden_state_hash,
            trigger_type=trigger_type,
            committed_at=datetime.now(timezone.utc),
        )


class InMemoryStateStore:
    def __init__(self) -> None:
        self._entries: dict[str, list[StateEntry]] = {}

    def entries(self, episode_id: str) -> tuple[StateEntry, ...]:
        return tuple(self._entries.get(episode_id, ()))

    def latest(self, episode_id: str) -> StateEntry | None:
        entries = self._entries.get(episode_id, ())
        return entries[-1] if entries else None

    def latest_before(self, episode_id: str, query_time: datetime) -> StateEntry | None:
        candidates = [
            entry
            for entry in self._entries.get(episode_id, ())
            if entry.snapshot.query_time < query_time
        ]
        return candidates[-1] if candidates else None

    def find_exact(
        self,
        state_key: tuple[str, str, int, str, str, str, str],
    ) -> StateEntry | None:
        for entry in self._entries.get(state_key[0], ()):
            if entry.key == state_key:
                return entry
        return None

    def entries_between(
        self,
        episode_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[StateEntry, ...]:
        return tuple(
            entry
            for entry in self._entries.get(episode_id, ())
            if start_time <= entry.snapshot.query_time <= end_time
        )

    def append(self, entry: StateEntry) -> None:
        entries = self._entries.setdefault(entry.snapshot.episode_id, [])
        if any(existing.key == entry.key for existing in entries):
            raise ValueError("M1_STATE_DUPLICATE_KEY")
        latest = entries[-1] if entries else None
        if latest is not None:
            if entry.snapshot.query_time <= latest.snapshot.query_time:
                raise ValueError("M1_STATE_OUT_OF_ORDER_REQUIRES_REPLAY")
            current_identity = (
                entry.pre_manifest_hash,
                entry.feature_schema_hash,
                entry.model_artifact_hash,
                entry.temperature_artifact_hash,
            )
            latest_identity = (
                latest.pre_manifest_hash,
                latest.feature_schema_hash,
                latest.model_artifact_hash,
                latest.temperature_artifact_hash,
            )
            if current_identity != latest_identity:
                raise ValueError("M1_STATE_ARTIFACT_IDENTITY_MISMATCH")
        entries.append(entry)

    def truncate_from(
        self,
        episode_id: str,
        query_time: datetime,
    ) -> tuple[StateEntry, ...]:
        entries = self._entries.get(episode_id, [])
        kept = [entry for entry in entries if entry.snapshot.query_time < query_time]
        removed = tuple(
            entry for entry in entries if entry.snapshot.query_time >= query_time
        )
        self._entries[episode_id] = kept
        return removed

    def replace_replayed_entries(
        self,
        episode_id: str,
        replay_from: datetime,
        entries: tuple[StateEntry, ...],
    ) -> None:
        kept = [
            entry
            for entry in self._entries.get(episode_id, ())
            if entry.snapshot.query_time < replay_from
        ]
        self._entries[episode_id] = kept
        for entry in entries:
            self.append(entry)

    def clear_episode(self, episode_id: str) -> int:
        return len(self._entries.pop(episode_id, ()))

    def clone_episode_state(self, episode_id: str) -> "InMemoryStateStore":
        clone = InMemoryStateStore()
        clone._entries[episode_id] = list(self._entries.get(episode_id, ()))
        return clone

    def watermark(self, episode_id: str) -> StateWatermark | None:
        latest = self.latest(episode_id)
        if latest is None:
            return None
        snapshot = latest.snapshot
        prediction = latest.prediction
        return StateWatermark(
            episode_id=episode_id,
            latest_snapshot_id=snapshot.snapshot_id,
            latest_snapshot_version=snapshot.snapshot_version,
            latest_query_time=snapshot.query_time,
            latest_information_cutoff=snapshot.information_cutoff,
            latest_hidden_state=prediction.hidden_state,
            feature_schema_hash=latest.feature_schema_hash,
            pre_manifest_hash=latest.pre_manifest_hash,
            model_artifact_hash=latest.model_artifact_hash,
            temperature_artifact_hash=latest.temperature_artifact_hash,
            state_commit_status=prediction.state_commit_status,
        )
