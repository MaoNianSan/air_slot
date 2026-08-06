from __future__ import annotations

from .contracts import ActivationStatus, FlightContext, PassengerContext, ResourceContext, SubitemActivation, ValuationContext


SUBITEMS = {
    "F": ("TURN", "WAIT", "PROPAGATION"),
    "P": ("DELAY", "CONNECTION", "CARE"),
    "R": ("GROUND", "TAXI", "SCARCITY"),
}


def activate_subitems(
    flight: FlightContext,
    passenger: PassengerContext,
    resource: ResourceContext,
    valuation: ValuationContext,
    *,
    disabled_subitems: tuple[str, ...] = (),
) -> dict[str, SubitemActivation]:
    support = {
        "TURN": (flight.turnaround_reference_type != "UNSUPPORTED", flight.evidence_status),
        "WAIT": (True, "M1_R_OB"),
        "PROPAGATION": (flight.downstream_leg_count > 0 or flight.continuity_exposure > 0, "DOWNSTREAM_CONTEXT"),
        "DELAY": (passenger.passenger_load_proxy is not None, passenger.evidence_status),
        "CONNECTION": (passenger.connection_pressure is not None or passenger.connection_slack is not None, passenger.evidence_status),
        "CARE": (passenger.passenger_load_proxy is not None, passenger.evidence_status),
        "GROUND": (resource.ground_support_pressure is not None or resource.resource_availability is not None, resource.evidence_status),
        "TAXI": (resource.airport_flow_pressure is not None, resource.evidence_status),
        "SCARCITY": (resource.resource_availability is not None, resource.evidence_status),
    }
    values = valuation.subitem_value_parameters
    result: dict[str, SubitemActivation] = {}
    for channel, names in SUBITEMS.items():
        for name in names:
            key = f"{channel}_{name}"
            if key in disabled_subitems:
                status = ActivationStatus.DISABLED_BY_CONFIG
                reason = "DISABLED_BY_CONFIG"
                evidence = "CONFIG"
            elif key not in values:
                status = ActivationStatus.UNSUPPORTED
                reason = "VALUE_PARAMETER_NOT_CONFIGURED"
                evidence = str(support[name][1])
            elif not support[name][0]:
                status = ActivationStatus.UNSUPPORTED
                reason = "INPUT_EVIDENCE_UNSUPPORTED"
                evidence = str(support[name][1])
            elif str(support[name][1]).upper() in {"PROXY", "SUPPORTED_PROXY", "EMPIRICAL_REFERENCE"}:
                status = ActivationStatus.PROXY_ACTIVE
                reason = "PROXY_EVIDENCE"
                evidence = str(support[name][1])
            else:
                status = ActivationStatus.ACTIVE
                reason = "FORMAL_INPUT_SUPPORTED"
                evidence = str(support[name][1])
            result[key] = SubitemActivation(key, channel, status, reason, evidence, "M2_RULES_V2", valuation.valuation_version)
    return result
