from __future__ import annotations

import math
from typing import Mapping

from .contracts import (
    ActivationStatus,
    AvailabilityStatus,
    ParameterStatus,
    SubitemActivation,
    ValuationContext,
)
from .dependencies import SUBITEM_DEPENDENCIES
from .rules import ALLOWED_RULE_TYPES


def _availability(value: AvailabilityStatus | str) -> AvailabilityStatus:
    return value if isinstance(value, AvailabilityStatus) else AvailabilityStatus(value)


def _configured_number(value: object) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number >= 0.0


def _rule_configuration_status(
    subitem: str,
    valuation: ValuationContext,
) -> tuple[bool, str]:
    if ParameterStatus(valuation.parameter_status) is not ParameterStatus.CONFIGURED:
        return False, "M2_PARAMETER_NOT_FROZEN"
    spec = SUBITEM_DEPENDENCIES[subitem]
    parameters = valuation.rule_parameters.get(subitem)
    if not isinstance(parameters, Mapping):
        return False, "RULE_PARAMETERS_NOT_CONFIGURED"
    missing = [name for name in spec.required_rule_parameters if name not in parameters]
    if missing:
        return False, f"RULE_PARAMETER_NOT_CONFIGURED:{','.join(missing)}"
    rule_type = str(parameters.get("rule_type", ""))
    if rule_type not in ALLOWED_RULE_TYPES:
        return False, "RULE_TYPE_NOT_CONFIGURED"
    numeric_names = [
        name for name in spec.required_rule_parameters if name != "rule_type"
    ]
    if any(not _configured_number(parameters[name]) for name in numeric_names):
        return False, "RULE_PARAMETER_INVALID"
    if spec.any_rule_parameters and not any(
        name in parameters and _configured_number(parameters[name])
        for name in spec.any_rule_parameters
    ):
        return False, (
            "RULE_PARAMETER_NOT_CONFIGURED_ANY_OF:"
            + ",".join(spec.any_rule_parameters)
        )
    return True, "CONFIGURED"


def _value_configuration_status(
    subitem: str,
    valuation: ValuationContext,
) -> tuple[bool, str]:
    if subitem not in valuation.subitem_value_parameters:
        return False, "VALUE_PARAMETER_NOT_CONFIGURED"
    if not _configured_number(valuation.subitem_value_parameters[subitem]):
        return False, "VALUE_PARAMETER_INVALID"
    return True, "CONFIGURED"


def activate_subitems(
    event_status: Mapping[str, AvailabilityStatus | str],
    context_support: Mapping[str, AvailabilityStatus | str],
    valuation: ValuationContext,
    *,
    disabled_subitems: tuple[str, ...] = (),
) -> dict[str, SubitemActivation]:
    result: dict[str, SubitemActivation] = {}
    disabled = set(disabled_subitems)
    for subitem, spec in SUBITEM_DEPENDENCIES.items():
        dependency_status: dict[str, str] = {}
        if subitem in disabled:
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.DISABLED_BY_CONFIG,
                "DISABLED_BY_CONFIG",
                "CONFIG",
                "NOT_ACTIVE",
                valuation.valuation_version,
                {"config": "DISABLED"},
            )
            continue

        required_event_states = {
            name: _availability(event_status.get(name, AvailabilityStatus.MISSING))
            for name in spec.required_events
        }
        any_event_states = {
            name: _availability(event_status.get(name, AvailabilityStatus.MISSING))
            for name in spec.any_required_events
        }
        context_states = {
            name: _availability(
                context_support.get(name, AvailabilityStatus.UNSUPPORTED)
            )
            for name in (*spec.required_context_fields, *spec.required_reference_fields)
        }
        dependency_status.update(
            {f"event:{name}": status.value for name, status in required_event_states.items()}
        )
        dependency_status.update(
            {f"event_any:{name}": status.value for name, status in any_event_states.items()}
        )
        dependency_status.update(
            {f"context:{name}": status.value for name, status in context_states.items()}
        )

        value_ok, value_reason = _value_configuration_status(subitem, valuation)
        rule_ok, rule_reason = _rule_configuration_status(subitem, valuation)
        dependency_status["value_parameter"] = value_reason
        dependency_status["rule_configuration"] = rule_reason
        if not value_ok or not rule_ok:
            reason = value_reason if not value_ok else rule_reason
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.NOT_CONFIGURED,
                reason,
                "PARAMETER_GATE",
                str(valuation.rule_parameters.get(subitem, {}).get("rule_version", "NOT_CONFIGURED")),
                valuation.valuation_version,
                dependency_status,
            )
            continue

        all_required_states = (*required_event_states.values(), *context_states.values())
        if any(status is AvailabilityStatus.TAIL_UNRESOLVED for status in all_required_states):
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.UNSUPPORTED,
                "TAIL_UNRESOLVED",
                "TAIL_UNRESOLVED",
                str(valuation.rule_parameters[subitem].get("rule_version", "M2_RULES_V2")),
                valuation.valuation_version,
                dependency_status,
            )
            continue
        if any_event_states and not any(
            status in {AvailabilityStatus.AVAILABLE, AvailabilityStatus.PROXY_AVAILABLE}
            for status in any_event_states.values()
        ):
            reason = (
                "TAIL_UNRESOLVED"
                if any(
                    status is AvailabilityStatus.TAIL_UNRESOLVED
                    for status in any_event_states.values()
                )
                else "REQUIRED_EVENT_UNAVAILABLE"
            )
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.UNSUPPORTED,
                reason,
                reason,
                str(valuation.rule_parameters[subitem].get("rule_version", "M2_RULES_V2")),
                valuation.valuation_version,
                dependency_status,
            )
            continue
        unavailable = [
            status
            for status in all_required_states
            if status not in {AvailabilityStatus.AVAILABLE, AvailabilityStatus.PROXY_AVAILABLE}
        ]
        if unavailable:
            reason = (
                "REQUIRED_INPUT_MISSING"
                if any(status is AvailabilityStatus.MISSING for status in unavailable)
                else "REQUIRED_INPUT_UNSUPPORTED"
            )
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.UNSUPPORTED,
                reason,
                ",".join(sorted({status.value for status in unavailable})),
                str(valuation.rule_parameters[subitem].get("rule_version", "M2_RULES_V2")),
                valuation.valuation_version,
                dependency_status,
            )
            continue

        proxy = any(
            status is AvailabilityStatus.PROXY_AVAILABLE
            for status in (*all_required_states, *any_event_states.values())
        )
        if proxy and not spec.allow_proxy:
            result[subitem] = SubitemActivation(
                subitem,
                spec.channel,
                ActivationStatus.UNSUPPORTED,
                "PROXY_NOT_ALLOWED",
                "PROXY_AVAILABLE",
                str(valuation.rule_parameters[subitem].get("rule_version", "M2_RULES_V2")),
                valuation.valuation_version,
                dependency_status,
            )
            continue
        status = ActivationStatus.PROXY_ACTIVE if proxy else ActivationStatus.ACTIVE
        result[subitem] = SubitemActivation(
            subitem,
            spec.channel,
            status,
            "PROXY_EVIDENCE" if proxy else "FORMAL_INPUT_SUPPORTED",
            "PROXY_AVAILABLE" if proxy else "AVAILABLE",
            str(valuation.rule_parameters[subitem].get("rule_version", "M2_RULES_V2")),
            valuation.valuation_version,
            dependency_status,
        )
    return result
