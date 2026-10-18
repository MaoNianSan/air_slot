"""Explicit PRE-to-M3 factual adaptation and tri-state eligibility.

The action registry names scientific facts.  PRE publishes source objects, so
the translation between the two layers must be explicit and provenance-aware.
This module deliberately never uses Python truthiness to decide factual
eligibility.  A non-boolean source value is UNKNOWN unless a named semantic
conversion rule handles it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class FactualState(str, Enum):
    """Tri-state result for one factual object or action condition."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class ActionContractStatus(str, Enum):
    """Whether the registry facts are sufficient for operational eligibility."""

    SUPPORTED = "SUPPORTED"
    CONTRACT_UNDERSPECIFIED = "CONTRACT_UNDERSPECIFIED"


@dataclass(frozen=True)
class FactualEvidence:
    """One explicit scientific-fact mapping with its evidence boundary."""

    scientific_fact: str
    state: FactualState
    source_family: str | None
    source_key: str | None
    conversion_rule: str
    support_state: str
    evidence_class: str
    support_ceiling: str
    provenance: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class AdaptedPreState:
    """Facts and parameters exposed to M3 after explicit PRE adaptation."""

    facts: dict[str, FactualEvidence]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ActionFactualEvaluation:
    """Action-level factual eligibility, retaining fact-level provenance."""

    state: FactualState
    reason: str
    facts: tuple[FactualEvidence, ...]
    provenance: tuple[str, ...]


# These entries record missing factual contracts. They are deliberately not
# inferred from a template's framework capability labels.
ACTION_CONTRACT_STATUS: dict[str, ActionContractStatus] = {
    "A21": ActionContractStatus.CONTRACT_UNDERSPECIFIED,
    "A71": ActionContractStatus.CONTRACT_UNDERSPECIFIED,
    "A72": ActionContractStatus.CONTRACT_UNDERSPECIFIED,
}

_CONTRACT_MISSING_PROVENANCE: dict[str, tuple[str, ...]] = {
    "A21": (
        "contract_missing=departure_not_yet_executed",
        "contract_missing=retiming_window_defined",
        "contract_missing=retiming_authority_or_policy_support",
    ),
    "A71": (
        "contract_missing=contemporaneous_cancellation_authority",
        "capability_label_not_contemporaneous_authority",
    ),
    "A72": (
        "contract_missing=contemporaneous_network_authority",
        "capability_label_not_contemporaneous_authority",
    ),
}


def _support_value(value: Any) -> str:
    support = getattr(value, "support_state", None)
    return getattr(support, "value", str(support or "UNKNOWN"))


def _evidence_value(value: Any) -> str:
    evidence = getattr(value, "evidence_class", None)
    return getattr(evidence, "value", str(evidence or "UNKNOWN"))


def _support_ceiling(value: Any) -> str:
    ceiling = getattr(value, "support_ceiling", None)
    return getattr(ceiling, "value", str(ceiling or "UNKNOWN"))


def _provenance(value: Any, *, scientific_fact: str, source_family: str,
                source_key: str, conversion_rule: str) -> tuple[str, ...]:
    source_record_id = getattr(value, "source_record_id", None)
    source_name = getattr(value, "source_name", None)
    parts = [
        f"scientific_fact={scientific_fact}",
        f"source_family={source_family}",
        f"source_key={source_key}",
        f"conversion_rule={conversion_rule}",
    ]
    if source_name:
        parts.append(f"source_name={source_name}")
    if source_record_id:
        parts.append(f"source_record_id={source_record_id}")
    return tuple(parts)


def _unknown(scientific_fact: str, *, reason: str,
             source_family: str | None = None, source_key: str | None = None,
             value: Any = None) -> FactualEvidence:
    support = _support_value(value) if value is not None else "UNKNOWN"
    evidence = _evidence_value(value) if value is not None else "UNKNOWN"
    ceiling = _support_ceiling(value) if value is not None else "UNKNOWN"
    if value is None:
        provenance = (
            f"scientific_fact={scientific_fact}",
            f"source_family={source_family or 'NOT_PUBLISHED'}",
            f"source_key={source_key or 'NOT_PUBLISHED'}",
            "conversion_rule=NO_IMPLICIT_TRUTHINESS",
        )
    else:
        provenance = _provenance(
            value,
            scientific_fact=scientific_fact,
            source_family=source_family or "UNKNOWN",
            source_key=source_key or "UNKNOWN",
            conversion_rule="NO_IMPLICIT_TRUTHINESS",
        )
    return FactualEvidence(
        scientific_fact=scientific_fact,
        state=FactualState.UNKNOWN,
        source_family=source_family,
        source_key=source_key,
        conversion_rule="NO_IMPLICIT_TRUTHINESS",
        support_state=support,
        evidence_class=evidence,
        support_ceiling=ceiling,
        provenance=provenance,
        reason=reason,
    )


def _explicit_boolean(scientific_fact: str, value: Any, *, source_family: str,
                      source_key: str) -> FactualEvidence:
    """Convert only a native bool; all other values remain UNKNOWN."""
    if value is None:
        return _unknown(
            scientific_fact,
            reason="MISSING_FACT",
            source_family=source_family,
            source_key=source_key,
        )
    if type(value) is not bool:
        return _unknown(
            scientific_fact,
            reason="NON_BOOLEAN_FACT_REQUIRES_EXPLICIT_ADAPTER",
            source_family=source_family,
            source_key=source_key,
        )
    state = FactualState.TRUE if value else FactualState.FALSE
    return FactualEvidence(
        scientific_fact=scientific_fact,
        state=state,
        source_family=source_family,
        source_key=source_key,
        conversion_rule="NATIVE_BOOLEAN_ONLY",
        support_state="SUPPORTED",
        evidence_class="DIRECT",
        support_ceiling="DIRECT",
        provenance=(
            f"scientific_fact={scientific_fact}",
            f"source_family={source_family}",
            f"source_key={source_key}",
            "conversion_rule=NATIVE_BOOLEAN_ONLY",
        ),
        reason="EXPLICIT_BOOLEAN_FACT",
    )


def _schedule_reference(scientific_fact: str, value: Any, *,
                        source_family: str, source_key: str) -> FactualEvidence:
    """Map a supported PRE schedule object without evaluating its truthiness."""
    support = _support_value(value)
    provenance = _provenance(
        value,
        scientific_fact=scientific_fact,
        source_family=source_family,
        source_key=source_key,
        conversion_rule="SCHEDULE_REFERENCE_OBJECT_PRESENT",
    )
    if support != "SUPPORTED":
        return FactualEvidence(
            scientific_fact=scientific_fact,
            state=FactualState.UNKNOWN,
            source_family=source_family,
            source_key=source_key,
            conversion_rule="SCHEDULE_REFERENCE_OBJECT_PRESENT",
            support_state=support,
            evidence_class=_evidence_value(value),
            support_ceiling=_support_ceiling(value),
            provenance=provenance,
            reason="SCHEDULE_REFERENCE_NOT_SUPPORTED",
        )
    if getattr(value, "value", None) is None:
        return FactualEvidence(
            scientific_fact=scientific_fact,
            state=FactualState.UNKNOWN,
            source_family=source_family,
            source_key=source_key,
            conversion_rule="SCHEDULE_REFERENCE_OBJECT_PRESENT",
            support_state=support,
            evidence_class=_evidence_value(value),
            support_ceiling=_support_ceiling(value),
            provenance=provenance,
            reason="SCHEDULE_REFERENCE_VALUE_MISSING",
        )
    return FactualEvidence(
        scientific_fact=scientific_fact,
        state=FactualState.TRUE,
        source_family=source_family,
        source_key=source_key,
        conversion_rule="SCHEDULE_REFERENCE_OBJECT_PRESENT",
        support_state=support,
        evidence_class=_evidence_value(value),
        support_ceiling=_support_ceiling(value),
        provenance=provenance,
        reason="SCHEDULE_REFERENCE_PRESENT",
    )


def _adapt_mapping(values: Mapping[str, Any], *, source_family: str,
                   facts: dict[str, FactualEvidence],
                   parameters: dict[str, Any]) -> None:
    for key, value in values.items():
        if hasattr(value, "support_state"):
            support = _support_value(value)
            if support == "ABSTAIN":
                facts[key] = _unknown(
                    key,
                    reason="PRE_SUPPORT_ABSTAIN",
                    source_family=source_family,
                    source_key=key,
                    value=value,
                )
                parameters[key] = None
                continue
            raw_value = getattr(value, "value", None)
            facts[key] = _explicit_boolean(
                key, raw_value, source_family=source_family, source_key=key
            )
            parameters[key] = raw_value
            continue
        facts[key] = _explicit_boolean(
            key, value, source_family=source_family, source_key=key
        )
        parameters[key] = value


def adapt_pre_state(pre_state: Any) -> AdaptedPreState:
    """Publish a deterministic, provenance-aware M3 view of a PRE state.

    ``successor_schedule`` is the only current cross-layer alias.  It maps
    explicitly to PRE ``successor_state.schedule_reference``.  Aggregate
    references and post-hoc operational fields are not aliased to the action
    registry's contemporaneous resource facts.
    """
    facts: dict[str, FactualEvidence] = {}
    parameters: dict[str, Any] = {}
    if isinstance(pre_state, Mapping):
        _adapt_mapping(
            pre_state.get("facts", {}),
            source_family="facts",
            facts=facts,
            parameters=parameters,
        )
        raw_parameters = pre_state.get("parameters", {})
        parameters.update(raw_parameters)
        return AdaptedPreState(facts=facts, parameters=parameters)

    state_maps = (
        ("predecessor_state", getattr(pre_state, "predecessor_state", {})),
        ("current_state", getattr(pre_state, "current_state", {})),
        ("successor_state", getattr(pre_state, "successor_state", {})),
        ("reference_state", getattr(getattr(pre_state, "reference_state", None),
                                     "entries", {})),
    )
    raw_values: dict[str, tuple[str, Any]] = {}
    for source_family, values in state_maps:
        for key, value in values.items():
            raw_values[key] = (source_family, value)

    for key, (source_family, value) in raw_values.items():
        support = _support_value(value)
        raw_value = getattr(value, "value", None)
        if support == "ABSTAIN":
            facts[key] = _unknown(
                key,
                reason="PRE_SUPPORT_ABSTAIN",
                source_family=source_family,
                source_key=key,
                value=value,
            )
            parameters[key] = None
        else:
            facts[key] = _explicit_boolean(
                key,
                raw_value,
                source_family=source_family,
                source_key=key,
            )
            parameters[key] = raw_value

    schedule = raw_values.get("schedule_reference")
    if schedule is not None:
        source_family, value = schedule
        facts["successor_schedule"] = _schedule_reference(
            "successor_schedule", value,
            source_family=source_family,
            source_key="schedule_reference",
        )

    return AdaptedPreState(facts=facts, parameters=parameters)


def evaluate_action_facts(template: Any, adapted: AdaptedPreState) -> ActionFactualEvaluation:
    """Evaluate required facts and then the explicit action contract."""
    required = tuple(template.required_facts)
    evidence = tuple(
        adapted.facts.get(
            name,
            _unknown(name, reason="REQUIRED_FACT_NOT_PUBLISHED"),
        )
        for name in required
    )
    if any(item.state is FactualState.FALSE for item in evidence):
        state = FactualState.FALSE
        reason = "REQUIRED_FACT_FALSE"
    elif any(item.state is FactualState.UNKNOWN for item in evidence):
        state = FactualState.UNKNOWN
        reason = "REQUIRED_FACT_UNKNOWN"
    else:
        state = FactualState.TRUE
        reason = "REQUIRED_FACTS_TRUE"

    contract_status = ACTION_CONTRACT_STATUS.get(
        template.template_id, ActionContractStatus.SUPPORTED
    )
    # A contract-under-specified action never acquires contemporaneous factual
    # eligibility merely because the currently published subset of facts is
    # TRUE.  The missing predicates remain an explicit UNKNOWN boundary.
    if contract_status is not ActionContractStatus.SUPPORTED:
        state = FactualState.UNKNOWN
        reason = contract_status.value

    provenance = tuple(
        item for fact in evidence for item in fact.provenance
    )
    if reason == ActionContractStatus.CONTRACT_UNDERSPECIFIED.value:
        provenance += _CONTRACT_MISSING_PROVENANCE[template.template_id]
    return ActionFactualEvaluation(
        state=state,
        reason=reason,
        facts=evidence,
        provenance=provenance,
    )


__all__ = [
    "ActionContractStatus",
    "ActionFactualEvaluation",
    "AdaptedPreState",
    "FactualEvidence",
    "FactualState",
    "ACTION_CONTRACT_STATUS",
    "adapt_pre_state",
    "evaluate_action_facts",
]
