from __future__ import annotations

from model.common.enums import EvidenceClass, SupportState
from model.M2.contracts import (
    COMPONENTS,
    ComponentInputContract,
    M2ScientificContext,
    NativeQuantity,
    ScientificContextValue,
)


_CONTEXT_FIELDS = tuple(M2ScientificContext.model_fields)

COMPONENT_INPUT_CONTRACTS = {
    item.component_id: item
    for item in (
        ComponentInputContract(
            component_id="F_continuity",
            critical_inputs=("r_ib_minutes", "turnaround_reference"),
            degradable_inputs=("turnaround_floor",),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name not in {"turnaround_reference", "turnaround_floor"}
            ),
        ),
        ComponentInputContract(
            component_id="F_execution",
            critical_inputs=("r_ob_minutes",),
            irrelevant_inputs=_CONTEXT_FIELDS,
        ),
        ComponentInputContract(
            component_id="F_propagation",
            critical_inputs=(
                "r_ob_minutes",
                "t_tx_minutes",
                "expected_downstream_exposure",
            ),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name != "expected_downstream_exposure"
            ),
        ),
        ComponentInputContract(
            component_id="P_time",
            critical_inputs=("r_ob_minutes", "t_tx_minutes", "passenger_exposure"),
            irrelevant_inputs=tuple(
                name for name in _CONTEXT_FIELDS if name != "passenger_exposure"
            ),
        ),
        ComponentInputContract(
            component_id="P_itinerary",
            critical_inputs=("itinerary_disruption_events",),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name != "itinerary_disruption_events"
            ),
        ),
        ComponentInputContract(
            component_id="P_service",
            critical_inputs=(
                "r_ob_minutes",
                "t_tx_minutes",
                "service_policy_reference",
            ),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name != "service_policy_reference"
            ),
        ),
        ComponentInputContract(
            component_id="R_operating",
            critical_inputs=("t_tx_minutes", "taxi_reference"),
            irrelevant_inputs=tuple(
                name for name in _CONTEXT_FIELDS if name != "taxi_reference"
            ),
        ),
    )
}


def _scenario_value(scenario: dict, name: str) -> tuple[float | None, SupportState]:
    value = scenario.get(name)
    support_name = {
        "r_ib_minutes": "ib_support",
        "r_ob_minutes": "ob_support",
        "t_tx_minutes": "tx_support",
    }[name]
    support = SupportState(scenario.get(support_name, "SUPPORTED"))
    if value is None or support is SupportState.ABSTAIN:
        return None, SupportState.ABSTAIN
    return float(value), support


def _context_value(
    context: M2ScientificContext, name: str
) -> ScientificContextValue:
    return getattr(context, name)


def _abstain(component: str, scenario_id: int, unit: str, driver: str, reasons):
    return NativeQuantity(
        component_id=component,
        scenario_id=scenario_id,
        native_quantity=None,
        native_unit=unit,
        driver=driver,
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN,
        reason_code=";".join(sorted(reasons)),
        provenance=(),
    )


def native_quantities(
    scenario: dict, context: M2ScientificContext
) -> tuple[NativeQuantity, ...]:
    if not isinstance(context, M2ScientificContext):
        context = M2ScientificContext.model_validate(context)
    sid = int(scenario["scenario_id"])
    rib, rib_support = _scenario_value(scenario, "r_ib_minutes")
    rob, rob_support = _scenario_value(scenario, "r_ob_minutes")
    taxi, taxi_support = _scenario_value(scenario, "t_tx_minutes")
    takeoff = None if rob is None or taxi is None else rob + taxi

    def ctx(name):
        return _context_value(context, name)

    def publish(
        component,
        value,
        unit,
        driver,
        parents,
        context_names=(),
        evidence=EvidenceClass.DERIVED,
    ):
        missing = []
        support_states = []
        provenance = []
        for name, parent_value, parent_support in parents:
            support_states.append(parent_support)
            if parent_value is None or parent_support is SupportState.ABSTAIN:
                missing.append(f"{name}_ABSTAIN")
        for name in context_names:
            item = ctx(name)
            support_states.append(item.support_state)
            provenance.extend(item.provenance)
            if item.value is None or item.support_state is SupportState.ABSTAIN:
                missing.append(f"{name}_ABSTAIN")
        if missing:
            return _abstain(component, sid, unit, driver, missing)
        state = (
            SupportState.DEGRADED
            if any(item is SupportState.DEGRADED for item in support_states)
            else SupportState.SUPPORTED
        )
        return NativeQuantity(
            component_id=component,
            scenario_id=sid,
            native_quantity=float(value()),
            native_unit=unit,
            driver=driver,
            evidence_class=evidence,
            support_state=state,
            reason_code="DEGRADED_PARENT_INPUT" if state is SupportState.DEGRADED else None,
            provenance=tuple(sorted(set(provenance))),
        )

    rows = (
        publish(
            "F_continuity",
            lambda: max(0.0, rib - float(ctx("turnaround_reference").value)),
            "minutes",
            "turnaround_compression",
            (("r_ib_minutes", rib, rib_support),),
            ("turnaround_reference",),
        ),
        publish(
            "F_execution",
            lambda: rob,
            "minutes",
            "additional_off_block_wait",
            (("r_ob_minutes", rob, rob_support),),
        ),
        publish(
            "F_propagation",
            lambda: takeoff * float(ctx("expected_downstream_exposure").value),
            "exposure_minutes",
            "takeoff_delay_x_expected_downstream_exposure",
            (
                ("r_ob_minutes", rob, rob_support),
                ("t_tx_minutes", taxi, taxi_support),
            ),
            ("expected_downstream_exposure",),
        ),
        publish(
            "P_time",
            lambda: float(ctx("passenger_exposure").value) * takeoff,
            "passenger_minutes",
            "passenger_exposure_x_delay",
            (
                ("r_ob_minutes", rob, rob_support),
                ("t_tx_minutes", taxi, taxi_support),
            ),
            ("passenger_exposure",),
            EvidenceClass.DOMAIN_PROXY,
        ),
        publish(
            "P_itinerary",
            lambda: float(ctx("itinerary_disruption_events").value),
            "events",
            "supported_itinerary_disruption_events",
            (),
            ("itinerary_disruption_events",),
        ),
        publish(
            "P_service",
            lambda: 1.0
            if takeoff >= float(ctx("service_policy_reference").value)
            else 0.0,
            "threshold_events",
            "service_policy_threshold",
            (
                ("r_ob_minutes", rob, rob_support),
                ("t_tx_minutes", taxi, taxi_support),
            ),
            ("service_policy_reference",),
            EvidenceClass.SCENARIO_PARAMETER
            if ctx("service_policy_reference").evidence_class
            is EvidenceClass.SCENARIO_PARAMETER
            else EvidenceClass.DERIVED,
        ),
        publish(
            "R_operating",
            lambda: max(0.0, taxi - float(ctx("taxi_reference").value)),
            "excess_taxi_minutes",
            "excess_taxi",
            (("t_tx_minutes", taxi, taxi_support),),
            ("taxi_reference",),
        ),
    )
    assert tuple(row.component_id for row in rows) == COMPONENTS
    return rows

