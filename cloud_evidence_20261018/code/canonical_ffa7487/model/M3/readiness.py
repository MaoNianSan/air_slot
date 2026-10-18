"""M3 numerical-response completeness derived from structural footprints.

Structural relevance and numerical response magnitude are separate contracts.
This module reports the distinction without changing action instantiation: a
formed action may still be numerically partial when an active footprint cell
has no materialized mitigation or induced score.
"""

from __future__ import annotations

from enum import Enum
from math import isfinite
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.value_objects import FrozenModel
from .contracts import FootprintRole


class NumericalParameterState(str, Enum):
    """State of one structural footprint cell's numerical parameter."""

    STRUCTURAL_ZERO = "STRUCTURAL_ZERO"
    NUMERICALLY_MATERIALIZED = "NUMERICALLY_MATERIALIZED"
    NUMERICAL_PARAMETER_NOT_MATERIALIZED = "NUMERICAL_PARAMETER_NOT_MATERIALIZED"


class ActionNumericalReadiness(FrozenModel):
    """Action-level numerical readiness, independent of factual eligibility."""

    action_id: str
    structural_status: str
    response_parameter_status: str
    missing_response_cells: tuple[str, ...] = ()
    chi_num_possible_if_state_complete: bool
    reason: str
    parameter_states: dict[str, NumericalParameterState]

    @property
    def numerical_complete(self) -> bool:
        return self.chi_num_possible_if_state_complete

    @property
    def chi_num(self) -> str:
        """Compatibility projection used by readiness/audit reports."""
        return "DEFINED" if self.chi_num_possible_if_state_complete else "UNDEFINED"

    @property
    def reason_code(self) -> str:
        return self.reason

    def state_for(self, component_id: str) -> NumericalParameterState:
        return self.parameter_states[component_id]


def _coefficient_for_role(template, component_id: str):
    footprint = template.footprint[component_id]
    if footprint.role is FootprintRole.MITIGATION:
        return template.mitigation.get(component_id)
    if footprint.role is FootprintRole.INDUCED:
        if component_id in template.induced_response:
            return template.induced_response[component_id]
        return template.induced.get(component_id)
    return 0.0


def readiness_for_template(template, *, response_status: str | None = None):
    """Derive one readiness record from a template-like action object."""

    parameter_states: dict[str, NumericalParameterState] = {}
    missing: list[str] = []
    for component_id in CONSEQUENCE_COMPONENTS:
        footprint = template.footprint[component_id]
        if footprint.role is FootprintRole.UNTOUCHED:
            parameter_states[component_id] = NumericalParameterState.STRUCTURAL_ZERO
            continue
        coefficient = _coefficient_for_role(template, component_id)
        if coefficient is None or not isfinite(float(coefficient)):
            parameter_states[component_id] = (
                NumericalParameterState.NUMERICAL_PARAMETER_NOT_MATERIALIZED
            )
            missing.append(component_id)
        else:
            parameter_states[component_id] = (
                NumericalParameterState.NUMERICALLY_MATERIALIZED
            )

    if template.template_id == "A00":
        effective_status = "NOT_REQUIRED"
        response_complete = True
    else:
        effective_status = response_status or template.response_parameter_status.value
        response_complete = effective_status == "FROZEN"
        if missing:
            effective_status = "PARTIAL"

    if template.template_id == "A00":
        reason = "NOT_REQUIRED"
    elif missing:
        reason = "RESPONSE_PARAMETER_NOT_MATERIALIZED"
    elif not response_complete:
        reason = "RESPONSE_PARAMETERS_NOT_FROZEN"
    else:
        reason = "NUMERICAL_RESPONSE_COMPLETE"

    return ActionNumericalReadiness(
        action_id=template.template_id,
        structural_status="COMPLETE",
        response_parameter_status=effective_status,
        missing_response_cells=tuple(missing),
        chi_num_possible_if_state_complete=(
            template.template_id == "A00" or (not missing and response_complete)
        ),
        reason=reason,
        parameter_states=parameter_states,
    )


def build_action_numerical_readiness(
    structural_registry,
    *,
    response_registry=None,
) -> tuple[ActionNumericalReadiness, ...]:
    """Build one readiness record for every registered action.

    ``response_registry`` is optional for compatibility. When supplied, its
    action response status is combined with structural-cell completeness.
    Missing active-cell coefficients are never treated as structural zeros.
    """

    records = []
    for template in structural_registry.templates:
        response_status = None
        if response_registry is not None and template.template_id in response_registry.actions:
            response_status = response_registry.actions[
                template.template_id
            ].response_parameter_status
        records.append(
            readiness_for_template(template, response_status=response_status)
        )
    return tuple(records)


def readiness_for_action(
    structural_registry,
    action_id: str,
    *,
    response_registry=None,
) -> ActionNumericalReadiness:
    """Return one action readiness record or raise for an unknown action."""

    records = build_action_numerical_readiness(
        structural_registry, response_registry=response_registry
    )
    for record in records:
        if record.action_id == action_id:
            return record
    raise KeyError(action_id)


__all__ = [
    "ActionNumericalReadiness",
    "NumericalParameterState",
    "build_action_numerical_readiness",
    "readiness_for_template",
    "readiness_for_action",
]
