"""Typed PRE-owned artifacts consumed by downstream training preparation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, TypedDict

from model.common.errors import ContractError
from model.PRE.contracts.pre_state import DecisionNodeRecord, TargetSupportState


class Data2M2CanonicalTrainRow(TypedDict):
    dataset_instance_id: str
    aircraft_id_namespace: str
    aircraft_id: str
    flight_id: str
    canonical_record_id: str
    origin_airport_id: str
    destination_airport_id: str
    event_start_time: datetime
    event_end_time: datetime
    actual_arrival_utc: datetime | None
    actual_departure_utc: datetime | None
    taxi_out_minutes: float | None
    split: Literal["train"]


@dataclass(frozen=True)
class Data2M2TrainPreparationArtifact:
    rows: list[Data2M2CanonicalTrainRow]
    source_paths: tuple[Path, ...]
    months: tuple[int, ...]
    fit_period: str
    timezone_rule_id: str = "D2-TIMEZONE"
    schedule_rule_id: str = "D2-BTS-SCHEDULE"
    outcome_rule_id: str = "D2-BTS-ACTUAL"
    schema_version: str = "DATA2_M2_TRAIN_PREPARATION_V1"
    final_test_access_count: int = 0

    def __post_init__(self) -> None:
        if not self.months or any(month < 1 or month > 6 for month in self.months):
            raise ContractError("M2_PREPARATION_NON_TRAIN_MONTH")
        if self.final_test_access_count != 0:
            raise ContractError("M2_PREPARATION_FINAL_TEST_ACCESS_VIOLATION")


class M1TrainingCoverageRow(TypedDict):
    episode_id: str
    decision_node_id: str
    decision_time: datetime
    node_index: int
    operational_stage: str
    target_support: tuple[dict[str, Any], ...]
    split: str
    lineage: tuple[str, ...]


@dataclass(frozen=True)
class DerivedM1TrainingCoverageArtifact:
    rows: tuple[M1TrainingCoverageRow, ...]
    schema_version: str = "DERIVED_M1_TRAINING_COVERAGE_ARTIFACT_V1"
    rule_id: str = "D2-M1-TRAINING-COVERAGE"
    source_schema: str = "PRE_DECISION_NODE"


def build_m1_training_coverage_row(
    *,
    episode_id: str,
    node: DecisionNodeRecord,
    target_support: tuple[TargetSupportState, ...],
    split: str,
) -> M1TrainingCoverageRow:
    if node.episode_id != episode_id:
        raise ContractError("M1_COVERAGE_EPISODE_ID_MISMATCH")
    return {
        "episode_id": episode_id,
        "decision_node_id": node.decision_node_id,
        "decision_time": node.decision_time,
        "node_index": node.node_index,
        "operational_stage": node.operational_stage.value,
        "target_support": tuple(
            item.model_dump(mode="json") for item in target_support
        ),
        "split": split,
        "lineage": (
            "PRE_DECISION_NODE",
            "D2-LABEL-R-IB",
            "D2-LABEL-DELTA-OB",
            "D2-LABEL-T-TX",
        ),
    }


__all__ = [
    "Data2M2CanonicalTrainRow",
    "Data2M2TrainPreparationArtifact",
    "DerivedM1TrainingCoverageArtifact",
    "M1TrainingCoverageRow",
    "build_m1_training_coverage_row",
]
