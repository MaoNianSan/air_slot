from __future__ import annotations

from math import isfinite

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS

from .contracts import ComponentSummary, DomainScoreSummary

FLIGHT_COMPONENTS = ("F_continuity", "F_execution", "F_propagation")
PASSENGER_COMPONENTS = ("P_time", "P_itinerary", "P_service")
AGGREGATION_CONTRACT_ID = "M4_SECTION3_SEVEN_COMPONENT_DOMAIN_MEAN_V1"


def build_domain_scores(
    components: tuple[ComponentSummary, ...],
) -> tuple[DomainScoreSummary, ...]:
    by_id = {item.component_id: item for item in components}
    result = []
    for domain_id, component_ids in (
        ("F", FLIGHT_COMPONENTS),
        ("P", PASSENGER_COMPONENTS),
        ("R", ("R_operating",)),
    ):
        values = tuple(by_id[item].value for item in component_ids)
        if any(value is None for value in values):
            result.append(
                DomainScoreSummary(
                    domain_id=domain_id,
                    value=None,
                    component_ids=component_ids,
                    reason_code=f"M4_{domain_id}_DOMAIN_UNSUPPORTED",
                )
            )
        else:
            result.append(
                DomainScoreSummary(
                    domain_id=domain_id,
                    value=sum(float(value) for value in values) / len(values),
                    component_ids=component_ids,
                )
            )
    return tuple(result)


def aggregate_domain_scores(
    domains: tuple[DomainScoreSummary, ...],
) -> float | None:
    values = tuple(item.value for item in domains)
    if any(value is None for value in values):
        return None
    value = sum(float(item) for item in values) / 3
    if not isfinite(value):
        raise ValueError("M4_AGGREGATE_SCORE_NONFINITE")
    return value


def priority_score(
    representation,
    *,
    delay_mean: float | None,
    aggregate_score: float | None,
) -> float | None:
    return delay_mean if representation.value == "DELAY" else aggregate_score


__all__ = [
    "AGGREGATION_CONTRACT_ID",
    "FLIGHT_COMPONENTS",
    "PASSENGER_COMPONENTS",
    "aggregate_domain_scores",
    "build_domain_scores",
    "priority_score",
]
