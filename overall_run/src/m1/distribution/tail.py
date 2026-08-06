from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EmpiricalTailArtifact:
    target_name: str
    overflow_lower_bound: float
    training_tail_values: tuple[float, ...]
    tail_sample_count: int
    artifact_version: str
    source_split: str = "TRAIN"
    minimum_tail_count: int = 30

    def __post_init__(self) -> None:
        if self.source_split != "TRAIN":
            raise ValueError("M1_TAIL_ARTIFACT_NON_TRAIN_SOURCE")
        if self.tail_sample_count != len(self.training_tail_values):
            raise ValueError("M1_TAIL_ARTIFACT_COUNT_MISMATCH")
        if any(value < self.overflow_lower_bound for value in self.training_tail_values):
            raise ValueError("M1_TAIL_ARTIFACT_VALUE_BELOW_OVERFLOW")

    @property
    def resolution_status(self) -> str:
        return "RESOLVED" if self.tail_sample_count >= self.minimum_tail_count else "TAIL_UNRESOLVED"

    @property
    def resolved_values(self) -> tuple[float, ...]:
        return self.training_tail_values if self.resolution_status == "RESOLVED" else ()


def build_empirical_tail_artifact(
    target_name: str,
    training_values: tuple[float, ...],
    overflow_lower_bound: float,
    *,
    artifact_version: str,
    minimum_tail_count: int = 30,
    source_split: str = "TRAIN",
) -> EmpiricalTailArtifact:
    values = np.asarray(training_values, dtype=float)
    tail = tuple(float(value) for value in values[np.isfinite(values) & (values >= overflow_lower_bound)])
    return EmpiricalTailArtifact(
        target_name=target_name,
        overflow_lower_bound=float(overflow_lower_bound),
        training_tail_values=tail,
        tail_sample_count=len(tail),
        artifact_version=artifact_version,
        source_split=source_split,
        minimum_tail_count=int(minimum_tail_count),
    )
