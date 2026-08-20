"""Data2 adapters for the shared, fail-closed replay contracts.

This module names the Data2 dataset boundary and retains its public error
codes. Generic episode selection, scenario construction, and lineage checks
live in :mod:`exp.common.replay`.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, model_validator

from exp.common.replay import (
    EpisodeReplaySelector,
    ReplayConsequenceBinding,
    ReplayDecisionRecord,
    ReplayEpisodeRecord,
    ReplayEpisodeRegistry,
    ReplayLineageValidationResult,
    ReplayScenarioBinding,
    ReplaySelectionResult,
    ReplaySelectionStatus,
    SelectedReplayEpisode,
    construct_replay_scenario,
    validate_replay_lineage,
)


DATA2_LOGICAL_DATASET_ID = "DATA2"
DATA2_SOURCE_DATASET_ID = "data2_2019"
DATA2_SELECTOR_SCHEMA_VERSION = "AIR_SLOT_EXP2_DATA2_SELECTOR_V1"


class Data2DecisionRecord(ReplayDecisionRecord):
    ERROR_NAMESPACE: ClassVar[str] = "DATA2"


class Data2EpisodeRecord(ReplayEpisodeRecord):
    ERROR_NAMESPACE: ClassVar[str] = "DATA2"
    split_id: str = Field(min_length=1)
    decision_records: tuple[Data2DecisionRecord, ...] = Field(min_length=1)


class Data2EpisodeRegistry(ReplayEpisodeRegistry):
    ERROR_NAMESPACE: ClassVar[str] = "DATA2"

    schema_version: str = DATA2_SELECTOR_SCHEMA_VERSION
    dataset_id: str = DATA2_LOGICAL_DATASET_ID
    source_dataset_id: str = DATA2_SOURCE_DATASET_ID
    episodes: tuple[Data2EpisodeRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_data2_identity(self) -> "Data2EpisodeRegistry":
        if self.schema_version != DATA2_SELECTOR_SCHEMA_VERSION:
            raise ValueError("DATA2_SELECTOR_SCHEMA_VERSION_MISMATCH")
        if self.dataset_id != DATA2_LOGICAL_DATASET_ID:
            raise ValueError("DATA2_LOGICAL_DATASET_ID_MISMATCH")
        if self.source_dataset_id != DATA2_SOURCE_DATASET_ID:
            raise ValueError("DATA2_SOURCE_DATASET_ID_MISMATCH")
        return self


Data2SelectionStatus = ReplaySelectionStatus
SelectedData2Episode = SelectedReplayEpisode
Data2SelectionResult = ReplaySelectionResult


class M1ScenarioBinding(ReplayScenarioBinding):
    ERROR_NAMESPACE: ClassVar[str] = "DATA2"


class M2ConsequenceBinding(ReplayConsequenceBinding):
    ERROR_NAMESPACE: ClassVar[str] = "DATA2"


Data2CompatibilityResult = ReplayLineageValidationResult


class Data2EpisodeSelector:
    """Select Data2 episodes through the generic frozen replay selector."""

    def __init__(self) -> None:
        self._selector = EpisodeReplaySelector()

    def select(
        self,
        registry: Data2EpisodeRegistry,
        *,
        episode_ids: tuple[str, ...],
        expected_split: str | None = None,
    ) -> Data2SelectionResult:
        if not isinstance(registry, Data2EpisodeRegistry):
            raise TypeError("DATA2_EPISODE_REGISTRY_REQUIRED")
        if not expected_split:
            return Data2SelectionResult(
                status=Data2SelectionStatus.BLOCKED,
                selected_episodes=(),
                reason_codes=("DATA2_FROZEN_SPLIT_REQUIRED",),
            )
        return self._selector.select(
            registry,
            episode_ids=episode_ids,
            expected_split=expected_split,
        )


class Data2ScenarioConstructor:
    """Construct Data2 M1 scenario inputs from selected replay nodes."""

    def construct(
        self,
        episode: SelectedData2Episode,
        *,
        decision_node_id: str,
        scenario_ids: tuple[int, ...],
    ) -> M1ScenarioBinding:
        binding = construct_replay_scenario(
            episode,
            decision_node_id=decision_node_id,
            scenario_ids=scenario_ids,
        )
        return M1ScenarioBinding.model_validate(binding.model_dump(mode="python"))


class Data2CompatibilityChecker:
    """Validate PRE -> M1 -> M2 Data2 bindings through common lineage checks."""

    def validate(
        self,
        episode: Data2EpisodeRecord,
        decision_node_id: str,
        m1: M1ScenarioBinding,
        m2: M2ConsequenceBinding,
    ) -> Data2CompatibilityResult:
        if not isinstance(episode, Data2EpisodeRecord):
            raise TypeError("DATA2_EPISODE_RECORD_REQUIRED")
        result = validate_replay_lineage(episode, decision_node_id, m1, m2)
        if result.reason_codes == ("DATA2_LINEAGE_COMPATIBLE",):
            return result.model_copy(
                update={"reason_codes": ("DATA2_PRE_M1_M2_COMPATIBLE",)}
            )
        return result


__all__ = [
    "DATA2_LOGICAL_DATASET_ID",
    "DATA2_SELECTOR_SCHEMA_VERSION",
    "DATA2_SOURCE_DATASET_ID",
    "Data2CompatibilityChecker",
    "Data2CompatibilityResult",
    "Data2DecisionRecord",
    "Data2EpisodeRecord",
    "Data2EpisodeRegistry",
    "Data2EpisodeSelector",
    "Data2ScenarioConstructor",
    "Data2SelectionResult",
    "Data2SelectionStatus",
    "M1ScenarioBinding",
    "M2ConsequenceBinding",
    "SelectedData2Episode",
]
