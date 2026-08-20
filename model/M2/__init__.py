"""M2 scenario-preserving consequence mapping."""

from .contracts import (
    CUQuantity,
    M2ScenarioInput,
    ScenarioConsequence,
    ScenarioConsequenceDistribution,
)
from .mapper import M2Mapper
from .summary import ConsequenceDistributionSummary, summarize_formal_consequence


def map_pre_action_consequence(scenarios, context, *, registry, consequence_scope):
    return M2Mapper(registry, consequence_scope).map_scenarios(scenarios, context)


def map_m1_scenario_consequence(scenarios, context, *, registry, consequence_scope):
    """Strict V2 M1 -> baseline M2 consequence boundary."""
    return M2Mapper(registry, consequence_scope).map_m1_scenarios(
        tuple(scenarios), context
    )


__all__ = [
    "ConsequenceDistributionSummary",
    "CUQuantity",
    "M2Mapper",
    "M2ScenarioInput",
    "ScenarioConsequence",
    "ScenarioConsequenceDistribution",
    "map_m1_scenario_consequence",
    "map_pre_action_consequence",
    "summarize_formal_consequence",
]
