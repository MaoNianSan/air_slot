"""Public M2 service boundary."""

from __future__ import annotations

from .mapper import M2Mapper


class M2Service:
    """Map typed M1 scenario inputs to baseline seven-component CU outputs."""

    def __init__(self, registry, consequence_scope):
        self.mapper = M2Mapper(registry, consequence_scope)

    def map_scenarios(self, scenarios, context):
        return self.mapper.map_m1_scenarios(tuple(scenarios), context)

    def map_distribution(self, scenarios, context):
        return self.mapper.map_m1_distribution(tuple(scenarios), context)

    def map_legacy(self, scenarios, context):
        return self.mapper.map_scenarios(scenarios, context)


__all__ = ["M2Service"]

