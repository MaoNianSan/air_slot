from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubitemDependencySpec:
    subitem_id: str
    channel: str
    required_events: tuple[str, ...] = ()
    any_required_events: tuple[str, ...] = ()
    required_context_fields: tuple[str, ...] = ()
    required_reference_fields: tuple[str, ...] = ()
    required_rule_parameters: tuple[str, ...] = ("rule_type",)
    any_rule_parameters: tuple[str, ...] = ()
    allow_proxy: bool = True
    requires_resolved_tail: bool = True
    requires_value_parameter: bool = True
    core_subitem: bool = False


SUBITEM_EVENT_REQUIREMENTS = {
    "F_TURN": frozenset({"turn_deficit"}),
    "F_WAIT": frozenset({"extra_offblock_wait"}),
    "F_PROPAGATION": frozenset({"takeoff_delay"}),
    "P_DELAY": frozenset({"takeoff_delay"}),
    "P_CONNECTION": frozenset({"takeoff_delay"}),
    "P_CARE": frozenset({"takeoff_delay"}),
    "R_GROUND": frozenset({"extra_offblock_wait"}),
    "R_TAXI": frozenset({"extra_taxi_delay"}),
    "R_SCARCITY": frozenset({"extra_offblock_wait", "extra_taxi_delay"}),
}


SUBITEM_DEPENDENCIES = {
    "F_TURN": SubitemDependencySpec(
        "F_TURN",
        "F",
        required_events=("turn_deficit",),
        required_context_fields=("continuity_exposure",),
        required_reference_fields=("successor_sobt", "turnaround_reference_minutes"),
        required_rule_parameters=(
            "rule_type",
            "context_gamma",
            "context_multiplier_min",
            "context_multiplier_max",
        ),
        core_subitem=True,
    ),
    "F_WAIT": SubitemDependencySpec(
        "F_WAIT",
        "F",
        required_events=("extra_offblock_wait",),
        required_context_fields=("execution_window_pressure",),
        required_rule_parameters=(
            "rule_type",
            "context_gamma",
            "context_multiplier_min",
            "context_multiplier_max",
        ),
        core_subitem=True,
    ),
    "F_PROPAGATION": SubitemDependencySpec(
        "F_PROPAGATION",
        "F",
        required_events=("takeoff_delay",),
        required_context_fields=("downstream_leg_count",),
    ),
    "P_DELAY": SubitemDependencySpec(
        "P_DELAY",
        "P",
        required_events=("takeoff_delay",),
        required_context_fields=("passenger_load_proxy",),
        core_subitem=True,
    ),
    "P_CONNECTION": SubitemDependencySpec(
        "P_CONNECTION",
        "P",
        required_events=("takeoff_delay",),
        required_context_fields=("connection_slack", "connection_pressure"),
        required_rule_parameters=(
            "rule_type",
            "context_gamma",
            "context_multiplier_min",
            "context_multiplier_max",
        ),
    ),
    "P_CARE": SubitemDependencySpec(
        "P_CARE",
        "P",
        required_events=("takeoff_delay",),
        required_context_fields=("passenger_load_proxy",),
        required_rule_parameters=("rule_type", "threshold_minutes"),
    ),
    "R_GROUND": SubitemDependencySpec(
        "R_GROUND",
        "R",
        required_events=("extra_offblock_wait",),
        required_context_fields=("ground_support_pressure",),
        required_rule_parameters=(
            "rule_type",
            "context_gamma",
            "context_multiplier_min",
            "context_multiplier_max",
        ),
        core_subitem=True,
    ),
    "R_TAXI": SubitemDependencySpec(
        "R_TAXI",
        "R",
        required_events=("extra_taxi_delay",),
        required_context_fields=("airport_flow_pressure",),
        required_rule_parameters=(
            "rule_type",
            "context_gamma",
            "context_multiplier_min",
            "context_multiplier_max",
        ),
        core_subitem=True,
    ),
    "R_SCARCITY": SubitemDependencySpec(
        "R_SCARCITY",
        "R",
        any_required_events=("extra_offblock_wait", "extra_taxi_delay"),
        required_context_fields=("resource_scarcity",),
        any_rule_parameters=("wait_threshold_minutes", "taxi_threshold_minutes"),
    ),
}


CORE_SUBITEMS = tuple(
    name for name, spec in SUBITEM_DEPENDENCIES.items() if spec.core_subitem
)


SUBITEMS_BY_CHANNEL = {
    channel: tuple(
        name for name, spec in SUBITEM_DEPENDENCIES.items() if spec.channel == channel
    )
    for channel in ("F", "P", "R")
}
