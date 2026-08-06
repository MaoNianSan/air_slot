from __future__ import annotations

from collections.abc import Callable, Mapping

import pandas as pd

from ..contracts import M1EpisodeSequence, M1SnapshotNode
from .bundle_loader import PublishedPreBundle
from .feature_schema import M1FeatureSchema
from .snapshot_builder import build_snapshot_node
from .timeline import build_timeline


SnapshotVersionResolver = Callable[[str, pd.Timestamp], int]


def _version(
    resolver: SnapshotVersionResolver | None,
    episode_id: str,
    query_time: pd.Timestamp,
) -> int:
    return 1 if resolver is None else int(resolver(episode_id, query_time))


def build_episode_sequence(
    published_pre_bundle: PublishedPreBundle,
    episode_id: str,
    feature_schema: M1FeatureSchema,
    roll_minutes: int = 5,
    maximum_minutes: int = 480,
    *,
    up_to_query_time: object | None = None,
    snapshot_version_resolver: SnapshotVersionResolver | None = None,
    stale_after_minutes: float = 30.0,
) -> M1EpisodeSequence:
    episodes = published_pre_bundle.episodes[
        published_pre_bundle.episodes["chain_episode_id"].astype(str).eq(str(episode_id))
    ]
    if len(episodes) != 1:
        raise ValueError("M1_EPISODE_ID_NOT_UNIQUE")
    episode = episodes.iloc[0]
    stop_candidates = [value for value in (episode.get("episode_end_time"), up_to_query_time) if value is not None and pd.notna(value)]
    stop_time = min((_utc(value) for value in stop_candidates), default=None)
    grid = build_timeline(
        episode.get("episode_start_time"),
        roll_minutes=roll_minutes,
        maximum_minutes=maximum_minutes,
        stop_time=stop_time,
    )
    snapshots: list[M1SnapshotNode] = []
    previous: pd.Timestamp | None = None
    for query in grid:
        snapshots.append(
            build_snapshot_node(
                published_pre_bundle,
                str(episode_id),
                query,
                feature_schema,
                snapshot_version=_version(snapshot_version_resolver, str(episode_id), query),
                previous_query_time=previous,
                stale_after_minutes=stale_after_minutes,
            )
        )
        previous = query
    return M1EpisodeSequence(
        episode_id=str(episode_id),
        feature_schema_hash=feature_schema.schema_hash,
        pre_manifest_hash=published_pre_bundle.identity.pre_manifest_hash,
        snapshots=tuple(snapshots),
    )


def _utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


class PublishedSnapshotSequenceProvider:
    def __init__(
        self,
        bundle: PublishedPreBundle,
        feature_schema: M1FeatureSchema,
        *,
        roll_minutes: int = 5,
        maximum_minutes: int = 480,
        snapshot_versions: Mapping[tuple[str, str], int] | None = None,
        stale_after_minutes: float = 30.0,
    ) -> None:
        self.bundle = bundle
        self.feature_schema = feature_schema
        self.roll_minutes = int(roll_minutes)
        self.maximum_minutes = int(maximum_minutes)
        self.snapshot_versions = dict(snapshot_versions or {})
        self.stale_after_minutes = float(stale_after_minutes)

    def _resolve_version(self, episode_id: str, query_time: pd.Timestamp) -> int:
        return int(self.snapshot_versions.get((episode_id, query_time.isoformat()), 1))

    def ordered_snapshots(
        self,
        episode_id: str,
        *,
        up_to_query_time: object,
    ) -> tuple[M1SnapshotNode, ...]:
        sequence = build_episode_sequence(
            self.bundle,
            episode_id,
            self.feature_schema,
            self.roll_minutes,
            self.maximum_minutes,
            up_to_query_time=up_to_query_time,
            snapshot_version_resolver=self._resolve_version,
            stale_after_minutes=self.stale_after_minutes,
        )
        return sequence.snapshots
