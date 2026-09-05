"""Adapters that preserve the formal M1 -> M2 typed boundary."""

from __future__ import annotations

from model.M1.contracts import M1V2Scenario
from model.M2.contracts import M2ScenarioInput


def to_m2_inputs(
    scenarios: tuple[M1V2Scenario, ...],
    *,
    pre_lineage: tuple[str, ...],
    reference_lineage: tuple[str, ...],
) -> tuple[M2ScenarioInput, ...]:
    if any(not isinstance(scenario, M1V2Scenario) for scenario in scenarios):
        raise TypeError("EXP1_M2_INPUT_REQUIRES_TYPED_M1_V2_SCENARIOS")
    return tuple(
        M2ScenarioInput.from_m1(
            scenario,
            pre_lineage=pre_lineage,
            reference_lineage=reference_lineage,
        )
        for scenario in scenarios
    )


class M1M2Adapter:
    """Thin delegation wrapper; no model semantics or raw-data parsing."""

    def __init__(self, m1_service, m2_mapper, m2_context):
        self.m1_service = m1_service
        self.m2_mapper = m2_mapper
        self.m2_context = m2_context

    def generate(self, pre_state, values, lengths, **kwargs):
        return self.m1_service.generate_scenarios(pre_state, values, lengths, **kwargs)

    def map(self, scenarios, *, pre_lineage, reference_lineage):
        typed = to_m2_inputs(
            tuple(scenarios),
            pre_lineage=pre_lineage,
            reference_lineage=reference_lineage,
        )
        return self.m2_mapper.map_m1_scenarios(typed, self.m2_context)
