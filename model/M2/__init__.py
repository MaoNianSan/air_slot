"""M2 scenario-preserving consequence mapping."""

from .contracts import ScenarioConsequence
from .mapper import M2Mapper


def map_pre_action_consequence(scenarios, context, *, registry, consequence_scope):
    return M2Mapper(registry, consequence_scope).map_scenarios(scenarios, context)


__all__ = ["M2Mapper", "ScenarioConsequence", "map_pre_action_consequence"]
