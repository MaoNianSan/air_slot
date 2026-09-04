"""Canonical M2 baseline consequence envelopes."""

from .contracts import (
    ComponentVector,
    ConsequenceRow,
    ScenarioConsequence,
    ScenarioConsequenceDistribution,
)

# Stable public name for the scenario-preserving seven-component envelope.
ConsequenceEnvelope = ScenarioConsequenceDistribution

__all__ = [
    "ComponentVector",
    "ConsequenceEnvelope",
    "ConsequenceRow",
    "ScenarioConsequence",
    "ScenarioConsequenceDistribution",
]
