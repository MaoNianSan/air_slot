from __future__ import annotations

from dataclasses import dataclass

from ..contracts import M1InputBundle, M1PredictionBundle, StateCommitStatus


@dataclass(frozen=True)
class StateWatermark:
    episode_id: str
    latest_snapshot_id: str
    latest_snapshot_version: int
    latest_information_cutoff: object
    latest_hidden_state: tuple[float, ...]
    ordered_pre_bundle_ids: tuple[str, ...]
    pre_manifest_hash: str
    model_version: str
    state_commit_status: StateCommitStatus


@dataclass(frozen=True)
class StateEntry:
    input_bundle: M1InputBundle
    prediction: M1PredictionBundle

    @property
    def key(self) -> tuple[str, str, int, str, str]:
        bundle = self.input_bundle
        return (
            bundle.episode_id,
            bundle.snapshot_id,
            bundle.snapshot_version,
            bundle.pre_bundle_identity.pre_manifest_hash,
            self.prediction.model_version,
        )


class InMemoryStateStore:
    def __init__(self) -> None:
        self._entries: dict[str, list[StateEntry]] = {}

    def entries(self, episode_id: str) -> tuple[StateEntry, ...]:
        return tuple(self._entries.get(episode_id, ()))

    def find(self, key: tuple[str, str, int, str, str]) -> M1PredictionBundle | None:
        for entry in self._entries.get(key[0], ()):
            if entry.key == key:
                return entry.prediction
        return None

    def latest(self, episode_id: str) -> StateEntry | None:
        entries = self._entries.get(episode_id, ())
        return entries[-1] if entries else None

    def append(self, entry: StateEntry) -> None:
        entries = self._entries.setdefault(entry.input_bundle.episode_id, [])
        entries.append(entry)
        entries.sort(
            key=lambda item: (
                item.input_bundle.query_time,
                item.input_bundle.snapshot_id,
                item.input_bundle.snapshot_version,
            )
        )

    def clear_episode(self, episode_id: str) -> int:
        return len(self._entries.pop(episode_id, ()))

    def truncate_from(self, episode_id: str, query_time: object) -> tuple[StateEntry, ...]:
        entries = self._entries.get(episode_id, [])
        kept = [entry for entry in entries if entry.input_bundle.query_time < query_time]
        removed = tuple(entry for entry in entries if entry.input_bundle.query_time >= query_time)
        self._entries[episode_id] = kept
        return removed

    def watermark(self, episode_id: str) -> StateWatermark | None:
        latest = self.latest(episode_id)
        if latest is None:
            return None
        bundle = latest.input_bundle
        prediction = latest.prediction
        return StateWatermark(
            episode_id=episode_id,
            latest_snapshot_id=bundle.snapshot_id,
            latest_snapshot_version=bundle.snapshot_version,
            latest_information_cutoff=bundle.information_cutoff,
            latest_hidden_state=prediction.hidden_state,
            ordered_pre_bundle_ids=tuple(
                entry.input_bundle.pre_bundle_identity.pre_manifest_hash
                for entry in self._entries[episode_id]
            ),
            pre_manifest_hash=bundle.pre_bundle_identity.pre_manifest_hash,
            model_version=prediction.model_version,
            state_commit_status=prediction.state_commit_status,
        )
