from __future__ import annotations

from model.common.errors import ContractError


def scenario_opportunities(candidate, m1_scenarios):
    if candidate.precondition_state == "FALSE":
        return [0.0 for _ in m1_scenarios]
    if candidate.template_id == "A00":
        return [1.0 for _ in m1_scenarios]
    scalar = candidate.parameters.get("deadline_minutes")
    by_scenario = candidate.parameters.get("deadline_minutes_by_scenario", {})
    deadlines = [
        scenario.get(
            "deadline_minutes",
            by_scenario.get(str(scenario["scenario_id"]),
                            by_scenario.get(scenario["scenario_id"], scalar)),
        )
        for scenario in m1_scenarios
    ]
    if candidate.precondition_state == "UNKNOWN" and any(value is None for value in deadlines):
        return [1.0 for _ in m1_scenarios]
    if any(value is None for value in deadlines):
        raise ContractError("ACTION_DEADLINE_UNRESOLVED")
    return [
        1.0 if float(value) > candidate.preparation_time_minutes else 0.0
        for value in deadlines
    ]
