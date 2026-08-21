"""Canonical and PRE output contracts."""
from .pre_state import AirportReferenceSlot, KeyedAirportReference
from .training_artifacts import (
    Data2M2TrainPreparationArtifact,
    DerivedM1TrainingCoverageArtifact,
)

__all__ = [
    "AirportReferenceSlot",
    "Data2M2TrainPreparationArtifact",
    "DerivedM1TrainingCoverageArtifact",
    "KeyedAirportReference",
]
