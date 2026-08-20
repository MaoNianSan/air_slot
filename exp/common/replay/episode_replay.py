"""Generic, fail-closed replay episode selection and scenario construction.

This module owns only identities, legal information cutoffs, frozen selection,
and split containment. It intentionally contains no warning, threshold, FPR,
or recall semantics.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator


REPLAY_SCHEMA_VERSION = "AIR_SLOT_COMMON_REPLAY_V1"


class ReplaySelectionStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class ReplayDecisionRecord(BaseModel):
    """One pre-constructed decision node and the inputs legal at its cutoff."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ERROR_NAMESPACE: ClassVar[str] = "REPLAY"

    decision_node_id: str = Field(min_length=1)
    decision_time: datetime
    information_cutoff: datetime
    legal_record_ids: tuple[str, ...] = Field(min_length=1)
    legal_record_availability_times: tuple[datetime, ...] = Field(min_length=1)

    def reason_code(self, suffix: str) -> str:
        return f"{type(self).ERROR_NAMESPACE}_{suffix}"

    @model_validator(mode="after")
    def validate_cutoff_and_availability(self) -> "ReplayDecisionRecord":
        if self.decision_time.tzinfo is None or self.information_cutoff.tzinfo is None:
            raise ValueError(self.reason_code("DECISION_TIMESTAMPS_MUST_BE_TIMEZONE_AWARE"))
        if self.information_cutoff > self.decision_time:
            raise ValueError(self.reason_code("INFORMATION_CUTOFF_EXCEEDS_DECISION_TIME"))
        if len(self.legal_record_ids) != len(self.legal_record_availability_times):
            raise ValueError(self.reason_code("LEGAL_RECORD_AVAILABILITY_CARDINALITY_MISMATCH"))
        for availability_time in self.legal_record_availability_times:
            if availability_time.tzinfo is None:
                raise ValueError(self.reason_code("AVAILABILITY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE"))
            if availability_time > self.information_cutoff:
                raise ValueError(self.reason_code("FUTURE_INFORMATION_LEAKAGE"))
        return self


class ReplayEpisodeRecord(BaseModel):
    """A frozen replay episode, independent of any raw dataset representation."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ERROR_NAMESPACE: ClassVar[str] = "REPLAY"

    episode_id: str = Field(min_length=1)
    split_id: str | None = Field(default=None, min_length=1)
    scenario_lineage: tuple[str, ...] = Field(min_length=1)
    decision_records: tuple[ReplayDecisionRecord, ...] = Field(min_length=1)

    def reason_code(self, suffix: str) -> str:
        return f"{type(self).ERROR_NAMESPACE}_{suffix}"

    @model_validator(mode="after")
    def validate_identity(self) -> "ReplayEpisodeRecord":
        node_ids = tuple(item.decision_node_id for item in self.decision_records)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError(self.reason_code("DUPLICATE_DECISION_NODE_ID"))
        if len(self.scenario_lineage) != len(set(self.scenario_lineage)):
            raise ValueError(self.reason_code("DUPLICATE_SCENARIO_LINEAGE_ID"))
        return self


class ReplayEpisodeRegistry(BaseModel):
    """A supplied frozen episode registry; never a raw-data discovery interface."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ERROR_NAMESPACE: ClassVar[str] = "REPLAY"

    schema_version: str = REPLAY_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1)
    source_dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_schema_version: str = Field(min_length=1)
    episodes: tuple[ReplayEpisodeRecord, ...] = Field(min_length=1)

    def reason_code(self, suffix: str) -> str:
        return f"{type(self).ERROR_NAMESPACE}_{suffix}"

    @model_validator(mode="after")
    def validate_registry_identity(self) -> "ReplayEpisodeRegistry":
        episode_ids = tuple(item.episode_id for item in self.episodes)
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError(self.reason_code("DUPLICATE_EPISODE_ID"))
        return self


class SelectedReplayEpisode(BaseModel):
    """The selection envelope passed to replay scenario construction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    episode_id: str
    split_id: str | None
    scenario_lineage: tuple[str, ...]
    decision_timestamps: tuple[datetime, ...]
    information_cutoffs: tuple[datetime, ...]
    decision_node_ids: tuple[str, ...]


class ReplaySelectionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ReplaySelectionStatus
    selected_episodes: tuple[SelectedReplayEpisode, ...]
    reason_codes: tuple[str, ...]


class ReplayScenarioBinding(BaseModel):
    """Scenario construction input copied exactly from a selected decision node."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    ERROR_NAMESPACE: ClassVar[str] = "REPLAY"

    episode_id: str = Field(min_length=1)
    decision_node_id: str = Field(min_length=1)
    decision_time: datetime
    information_cutoff: datetime
    scenario_lineage: tuple[str, ...] = Field(min_length=1)
    scenario_ids: tuple[int, ...] = Field(min_length=1)

    def reason_code(self, suffix: str) -> str:
        return f"{type(self).ERROR_NAMESPACE}_{suffix}"

    @model_validator(mode="after")
    def validate_scenario_identity(self) -> "ReplayScenarioBinding":
        if self.information_cutoff > self.decision_time:
            raise ValueError(self.reason_code("INFORMATION_CUTOFF_EXCEEDS_DECISION_TIME"))
        if len(self.scenario_lineage) != len(set(self.scenario_lineage)):
            raise ValueError(self.reason_code("DUPLICATE_SCENARIO_LINEAGE_ID"))
        if len(self.scenario_ids) != len(set(self.scenario_ids)):
            raise ValueError(self.reason_code("DUPLICATE_SCENARIO_ID"))
        return self


class EpisodeReplaySelector:
    """Select explicitly named episodes in frozen-registry order only."""

    @staticmethod
    def _reason(registry: ReplayEpisodeRegistry, suffix: str) -> str:
        return registry.reason_code(suffix)

    def select(
        self,
        registry: ReplayEpisodeRegistry,
        *,
        episode_ids: tuple[str, ...],
        expected_split: str | None = None,
    ) -> ReplaySelectionResult:
        if not isinstance(registry, ReplayEpisodeRegistry):
            raise TypeError("REPLAY_EPISODE_REGISTRY_REQUIRED")
        if expected_split is not None and not expected_split:
            raise ValueError(self._reason(registry, "EXPECTED_SPLIT_REQUIRED"))
        if not episode_ids:
            return ReplaySelectionResult(
                status=ReplaySelectionStatus.BLOCKED,
                selected_episodes=(),
                reason_codes=(self._reason(registry, "EPISODE_SELECTION_REQUIRED"),),
            )
        if len(episode_ids) != len(set(episode_ids)):
            return ReplaySelectionResult(
                status=ReplaySelectionStatus.BLOCKED,
                selected_episodes=(),
                reason_codes=(self._reason(registry, "DUPLICATE_REQUESTED_EPISODE_ID"),),
            )
        available = {item.episode_id: item for item in registry.episodes}
        missing = tuple(item for item in episode_ids if item not in available)
        if missing:
            return ReplaySelectionResult(
                status=ReplaySelectionStatus.BLOCKED,
                selected_episodes=(),
                reason_codes=tuple(
                    self._reason(registry, f"REQUESTED_EPISODE_NOT_IN_FROZEN_REGISTRY:{item}")
                    for item in missing
                ),
            )
        if expected_split is not None:
            outside_split = tuple(
                item for item in episode_ids
                if available[item].split_id != expected_split
            )
            if outside_split:
                return ReplaySelectionResult(
                    status=ReplaySelectionStatus.BLOCKED,
                    selected_episodes=(),
                    reason_codes=tuple(
                        self._reason(
                            registry,
                            f"EPISODE_SPLIT_MISMATCH:{item}:expected={expected_split}:actual={available[item].split_id}",
                        )
                        for item in outside_split
                    ),
                )
        selected = tuple(
            SelectedReplayEpisode(
                episode_id=available[episode_id].episode_id,
                split_id=available[episode_id].split_id,
                scenario_lineage=available[episode_id].scenario_lineage,
                decision_timestamps=tuple(
                    item.decision_time for item in available[episode_id].decision_records
                ),
                information_cutoffs=tuple(
                    item.information_cutoff for item in available[episode_id].decision_records
                ),
                decision_node_ids=tuple(
                    item.decision_node_id for item in available[episode_id].decision_records
                ),
            )
            for episode_id in episode_ids
        )
        return ReplaySelectionResult(
            status=ReplaySelectionStatus.READY,
            selected_episodes=selected,
            reason_codes=(self._reason(registry, "SELECTION_PRESERVES_FROZEN_REGISTRY_ORDER"),),
        )


def construct_replay_scenario(
    episode: SelectedReplayEpisode,
    *,
    decision_node_id: str,
    scenario_ids: tuple[int, ...],
) -> ReplayScenarioBinding:
    """Construct a scenario request from one selected node without mutation."""
    if not isinstance(episode, SelectedReplayEpisode):
        raise TypeError("REPLAY_SELECTED_EPISODE_REQUIRED")
    try:
        node_index = episode.decision_node_ids.index(decision_node_id)
    except ValueError as exc:
        raise ValueError("REPLAY_DECISION_NODE_NOT_IN_SELECTED_EPISODE") from exc
    return ReplayScenarioBinding(
        episode_id=episode.episode_id,
        decision_node_id=decision_node_id,
        decision_time=episode.decision_timestamps[node_index],
        information_cutoff=episode.information_cutoffs[node_index],
        scenario_lineage=episode.scenario_lineage,
        scenario_ids=scenario_ids,
    )


__all__ = [
    "REPLAY_SCHEMA_VERSION",
    "EpisodeReplaySelector",
    "ReplayDecisionRecord",
    "ReplayEpisodeRecord",
    "ReplayEpisodeRegistry",
    "ReplayScenarioBinding",
    "ReplaySelectionResult",
    "ReplaySelectionStatus",
    "SelectedReplayEpisode",
    "construct_replay_scenario",
]
