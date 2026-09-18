"""M2 comparison support and consequence priority (Phase 2).

M2 owns:

- ``Omega^CS``: the scenarios on which successor take-off delay and the required
  consequence quantities are *jointly* supported;
- ``m^CS = sum_{s in Omega^CS} w_s`` and the nominal ``m^CS >= 0.90`` rule;
- the unique consequence-based priority authority ``P^C = Phi_C(C^CU)``;
- the manuscript delay-comparator adapter ``P^D = (1/m^CS) sum w_s D^{+,TO}_s``
  (manuscript section 4, ``eq:empirical_delay_score``) that M3 Stage I consumes.

The legacy ``exp/shared/recovery_priority.py::summarize_delay_score`` (weight
sum without ``m^CS`` renormalisation, all-or-nothing scenario support) is a
recorded deviation and is *not* the paper-primary definition.

``missing`` (no value), ``unsupported`` (no admissible source) and a supported
``zero`` stay distinct: only the third one enters ``Omega^CS`` as a value.
"""

from __future__ import annotations

from typing import Mapping

from pydantic import Field

from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.decision_contracts import (
    NOMINAL_COMMON_SUPPORT_MASS,
    PREDEFINED_COMMON_SUPPORT_SENSITIVITY,
    ComparisonSupport,
    ConsequenceScenario,
    ConsequenceScenarioSet,
    PrioritySignal,
    SignalKind,
    StateScenario,
    StateScenarioSet,
    TypedStatus,
    WEIGHT_TOLERANCE,
)
from model.common.enums import SupportState
from model.common.errors import ContractError
from model.common.value_objects import FrozenModel


__all__ = [
    "DOMAIN_BY_COMPONENT",
    "EQUAL_COMPONENT_VIEW",
    "NOMINAL_COMPARISON_SUPPORT_RULE",
    "PRIMARY_AGGREGATION_VIEW",
    "ComparisonSupportRule",
    "build_comparison_support",
    "consequence_priority_signal",
    "delay_priority_signal",
    "expected_cu_vector",
    "phi_c",
    "priority_signals",
]


NOMINAL_COMPARISON_SUPPORT_RULE = "M2_COMMON_SUPPORT_NOMINAL_0P90"

#: Primary aggregation view: the manuscript's fixed domain-balanced mapping
#: (equal weight within the F and P domains, equal weight across the three
#: domains), reported in the manuscript aggregation-mapping appendix entry.
PRIMARY_AGGREGATION_VIEW = "PRIMARY_DOMAIN_BALANCED"

#: Appendix robustness view, recorded but not the primary mapping.
EQUAL_COMPONENT_VIEW = "EQUAL_COMPONENT"

DOMAIN_BY_COMPONENT: dict[str, str] = {
    "F_continuity": "F",
    "F_execution": "F",
    "F_propagation": "F",
    "P_time": "P",
    "P_itinerary": "P",
    "P_service": "P",
    "R_operating": "R",
}


class ComparisonSupportRule(FrozenModel):
    """M2-owned common-support rule with the nominal threshold only.

    The latest manuscript body predefines no ``m^CS`` sensitivity values, so
    ``predefined_sensitivity`` stays empty and the gap is reported rather than
    filled with an appendix-only grid.
    """

    rule_id: str = NOMINAL_COMPARISON_SUPPORT_RULE
    threshold: float = Field(default=NOMINAL_COMMON_SUPPORT_MASS, gt=0.0, le=1.0)
    estimand: str = "JOINTLY_SUPPORTED_PRIORITY_COMPARISON"
    predefined_sensitivity: tuple[float, ...] = (
        PREDEFINED_COMMON_SUPPORT_SENSITIVITY
    )
    sensitivity_authority: str = "MANUSCRIPT_BODY_PREDEFINED_VALUES_ONLY"
    sensitivity_status: str = "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES"


def _scenario_index_by_id(items) -> dict[int, object]:
    return {item.scenario_id: item for item in items}


def _require_alignment(
    state: StateScenarioSet, consequence: ConsequenceScenarioSet
) -> tuple[dict[int, StateScenario], dict[int, ConsequenceScenario]]:
    if (state.episode_id, state.chain_id, state.node_id) != (
        consequence.episode_id,
        consequence.chain_id,
        consequence.node_id,
    ):
        raise ContractError("M2_CS_IDENTITY_MISMATCH")
    if state.stage is not consequence.stage:
        raise ContractError("M2_CS_STAGE_MISMATCH")
    if state.representation != consequence.representation:
        raise ContractError("M2_CS_REPRESENTATION_MISMATCH")
    state_by_id = _scenario_index_by_id(state.scenarios)
    consequence_by_id = _scenario_index_by_id(consequence.scenarios)
    if set(state_by_id) != set(consequence_by_id):
        raise ContractError("M2_CS_SCENARIO_ID_SET_MISMATCH")
    for scenario_id, scenario in state_by_id.items():
        if (
            abs(
                scenario.scenario_weight
                - float(consequence_by_id[scenario_id].scenario_weight)
            )
            > WEIGHT_TOLERANCE
        ):
            raise ContractError(f"M2_CS_SCENARIO_WEIGHT_MISMATCH:{scenario_id}")
    return state_by_id, consequence_by_id


def _scenario_exclusion_reasons(
    state: StateScenario, consequence: ConsequenceScenario
) -> list[str]:
    reasons: list[str] = []
    if state.support is SupportState.ABSTAIN:
        reasons.append("M2_CS_STATE_UNSUPPORTED")
    if consequence.support is SupportState.ABSTAIN:
        reasons.append("M2_CS_CONSEQUENCE_UNSUPPORTED")
    if state.d_to_minutes is None:
        reasons.append("M2_CS_DELAY_MISSING")
    for component in CONSEQUENCE_COMPONENTS:
        value = consequence.cu_components.get(component)
        if value is None:
            reasons.append(f"M2_CS_CU_MISSING:{component}")
    return reasons


def build_comparison_support(
    state: StateScenarioSet,
    consequence: ConsequenceScenarioSet,
    *,
    rule: ComparisonSupportRule | None = None,
) -> ComparisonSupport:
    """Form ``Omega^CS`` and ``m^CS`` for one decision node.

    A scenario enters ``Omega^CS`` only when the delay quantity is present and
    supported *and* every required consequence CU quantity is present and
    supported. Nodes whose jointly supported mass misses the threshold are
    recorded with ``ABSTAIN_NO_COMMON_SUPPORT``; their mass is reported as-is
    and never renormalised or zero-filled.
    """

    active_rule = rule or ComparisonSupportRule()
    state_by_id, consequence_by_id = _require_alignment(state, consequence)
    supported_ids: list[int] = []
    reasons: set[str] = set()
    degraded = False
    for scenario_id in sorted(state_by_id):
        state_scenario = state_by_id[scenario_id]
        consequence_scenario = consequence_by_id[scenario_id]
        exclusion = _scenario_exclusion_reasons(state_scenario, consequence_scenario)
        if exclusion:
            reasons.update(exclusion)
            continue
        supported_ids.append(scenario_id)
        if (
            state_scenario.support is SupportState.DEGRADED
            or consequence_scenario.support is SupportState.DEGRADED
        ):
            degraded = True
    supported_mass = sum(
        state_by_id[scenario_id].scenario_weight for scenario_id in supported_ids
    )
    included = supported_mass + WEIGHT_TOLERANCE >= active_rule.threshold
    if included:
        status = TypedStatus.DEGRADED if degraded else TypedStatus.SUPPORTED
    else:
        status = TypedStatus.ABSTAIN_NO_COMMON_SUPPORT
        reasons.add("M2_CS_BELOW_NOMINAL_THRESHOLD")
    return ComparisonSupport(
        episode_id=state.episode_id,
        chain_id=state.chain_id,
        node_id=state.node_id,
        rule_id=active_rule.rule_id,
        estimand=active_rule.estimand,
        supported_mass=supported_mass,
        supported_scenario_ids=tuple(supported_ids),
        scenario_count_total=len(state.scenarios),
        threshold=active_rule.threshold,
        included=included,
        status=status,
        reason_codes=tuple(sorted(reasons)),
    )


def expected_cu_vector(
    consequence: ConsequenceScenarioSet, support: ComparisonSupport
) -> dict[str, float]:
    """Common-support expected CU quantity per required component."""

    if (consequence.episode_id, consequence.chain_id, consequence.node_id) != (
        support.episode_id,
        support.chain_id,
        support.node_id,
    ):
        raise ContractError("M2_CS_SUPPORT_IDENTITY_MISMATCH")
    if not support.included:
        raise ContractError("M2_CS_EXPECTATION_ON_UNSUPPORTED_NODE")
    mass = support.supported_mass
    if mass <= 0.0:
        raise ContractError("M2_CS_ZERO_SUPPORT_MASS")
    by_id = _scenario_index_by_id(consequence.scenarios)
    totals = {component: 0.0 for component in CONSEQUENCE_COMPONENTS}
    for scenario_id in support.supported_scenario_ids:
        scenario = by_id[scenario_id]
        for component in CONSEQUENCE_COMPONENTS:
            value = scenario.cu_components.get(component)
            if value is None:
                raise ContractError(
                    f"M2_CS_MISSING_CU_ON_SUPPORTED_SCENARIO:{scenario_id}:{component}"
                )
            totals[component] += scenario.scenario_weight * float(value)
    return {component: total / mass for component, total in totals.items()}


def phi_c(
    cu_by_component: Mapping[str, float],
    *,
    view: str = PRIMARY_AGGREGATION_VIEW,
) -> float:
    """Aggregate a CU vector into the consequence priority ``P^C``.

    The primary view is the manuscript's fixed domain-balanced mapping: equal
    weight within the flight-chain and passenger domains and equal weight across
    the three domains,
    ``Phi_C = (1/3)[mean(F) + mean(P) + R]``. ``EQUAL_COMPONENT`` is the
    appendix robustness view and is never the default.
    """

    missing = [
        component
        for component in CONSEQUENCE_COMPONENTS
        if cu_by_component.get(component) is None
    ]
    if missing:
        raise ContractError("M2_CS_PHI_C_INCOMPLETE_CU_VECTOR:" + ",".join(missing))
    values = {component: float(cu_by_component[component]) for component in CONSEQUENCE_COMPONENTS}
    if view == PRIMARY_AGGREGATION_VIEW:
        flight = (
            values["F_continuity"] + values["F_execution"] + values["F_propagation"]
        ) / 3.0
        passenger = (
            values["P_time"] + values["P_itinerary"] + values["P_service"]
        ) / 3.0
        operating = values["R_operating"]
        return (flight + passenger + operating) / 3.0
    if view == EQUAL_COMPONENT_VIEW:
        return sum(values.values()) / len(CONSEQUENCE_COMPONENTS)
    raise ContractError(f"M2_CS_UNKNOWN_AGGREGATION_VIEW:{view}")


def _support_attestation(
    state: StateScenarioSet | ConsequenceScenarioSet, support: ComparisonSupport
) -> None:
    if (state.episode_id, state.chain_id, state.node_id) != (
        support.episode_id,
        support.chain_id,
        support.node_id,
    ):
        raise ContractError("M2_CS_SUPPORT_IDENTITY_MISMATCH")


def _abstaining_signal(
    *, signal_type: SignalKind, representation_id: str, support: ComparisonSupport
) -> PrioritySignal:
    return PrioritySignal(
        signal_type=signal_type,
        episode_id=support.episode_id,
        chain_id=support.chain_id,
        node_id=support.node_id,
        representation_id=representation_id,
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        comparison_support_mass=support.supported_mass,
        comparison_support_threshold=support.threshold,
        reason_codes=support.reason_codes,
    )


def delay_priority_signal(
    state: StateScenarioSet, support: ComparisonSupport
) -> PrioritySignal:
    """``P^D``: the manuscript common-support conditional mean of ``D^TO``."""

    _support_attestation(state, support)
    representation_id = state.representation.representation_id
    if not support.included:
        return _abstaining_signal(
            signal_type=SignalKind.DELAY,
            representation_id=representation_id,
            support=support,
        )
    mass = support.supported_mass
    if mass <= 0.0:
        raise ContractError("M2_CS_ZERO_SUPPORT_MASS")
    by_id = _scenario_index_by_id(state.scenarios)
    total = 0.0
    for scenario_id in support.supported_scenario_ids:
        scenario = by_id[scenario_id]
        if scenario.d_to_minutes is None:
            raise ContractError(
                f"M2_CS_MISSING_DELAY_ON_SUPPORTED_SCENARIO:{scenario_id}"
            )
        total += scenario.scenario_weight * float(scenario.d_to_minutes)
    return PrioritySignal(
        signal_type=SignalKind.DELAY,
        episode_id=state.episode_id,
        chain_id=state.chain_id,
        node_id=state.node_id,
        representation_id=representation_id,
        score=total / mass,
        support=(
            SupportState.DEGRADED
            if support.status is TypedStatus.DEGRADED
            else SupportState.SUPPORTED
        ),
        status=support.status,
        comparison_support_mass=mass,
        comparison_support_threshold=support.threshold,
        reason_codes=support.reason_codes,
    )


def consequence_priority_signal(
    consequence: ConsequenceScenarioSet,
    support: ComparisonSupport,
    *,
    view: str = PRIMARY_AGGREGATION_VIEW,
) -> PrioritySignal:
    """``P^C = Phi_C(C^CU)``: the only consequence-based priority authority."""

    _support_attestation(consequence, support)
    representation_id = consequence.representation.representation_id
    if not support.included:
        return _abstaining_signal(
            signal_type=SignalKind.CONSEQUENCE,
            representation_id=representation_id,
            support=support,
        )
    expected = expected_cu_vector(consequence, support)
    return PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id=consequence.episode_id,
        chain_id=consequence.chain_id,
        node_id=consequence.node_id,
        representation_id=representation_id,
        score=phi_c(expected, view=view),
        support=(
            SupportState.DEGRADED
            if support.status is TypedStatus.DEGRADED
            else SupportState.SUPPORTED
        ),
        status=support.status,
        comparison_support_mass=support.supported_mass,
        comparison_support_threshold=support.threshold,
        reason_codes=support.reason_codes,
    )


def priority_signals(
    state: StateScenarioSet,
    consequence: ConsequenceScenarioSet,
    *,
    rule: ComparisonSupportRule | None = None,
    view: str = PRIMARY_AGGREGATION_VIEW,
) -> tuple[ComparisonSupport, PrioritySignal, PrioritySignal]:
    """Both Stage-I signals on one shared ``Omega^CS`` attestation.

    The delay comparator and the consequence authority share the same candidate
    cohort, the same common-support set and the same inclusion threshold; they
    differ only in the priority signal itself.
    """

    support = build_comparison_support(state, consequence, rule=rule)
    delay = delay_priority_signal(state, support)
    effect = consequence_priority_signal(consequence, support, view=view)
    return support, delay, effect
