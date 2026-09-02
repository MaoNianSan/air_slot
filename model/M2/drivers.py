from __future__ import annotations

import json

from model.common.enums import EvidenceClass, SupportState
from model.M2.contracts import (
    COMPONENTS,
    ComponentInputContract,
    ExposureConfidence,
    M2ScenarioInput,
    M2ScientificContext,
    NativeQuantity,
    ScientificContextValue,
    SourceType,
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
            critical_inputs=("d_ob_minutes",),
            irrelevant_inputs=_CONTEXT_FIELDS,
        ),
        ComponentInputContract(
            component_id="F_propagation",
            critical_inputs=("d_to_minutes", "expected_downstream_exposure"),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name != "expected_downstream_exposure"
            ),
        ),
        ComponentInputContract(
            component_id="P_time",
            critical_inputs=("d_to_minutes", "expected_passengers_per_flight"),
            irrelevant_inputs=tuple(
                name for name in _CONTEXT_FIELDS if name != "expected_passengers_per_flight"
            ),
        ),
        ComponentInputContract(
            component_id="P_itinerary",
            critical_inputs=("d_to_minutes", "expected_passengers_per_flight", "connection_share_reference"),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name not in {"d_to_minutes", "expected_passengers_per_flight", "connection_share_reference"}
            ),
        ),
        ComponentInputContract(
            component_id="P_service",
            critical_inputs=(
                "d_to_minutes",
                "expected_passengers_per_flight",
            ),
            irrelevant_inputs=tuple(
                name
                for name in _CONTEXT_FIELDS
                if name != "expected_passengers_per_flight"
            ),
        ),
        ComponentInputContract(
            component_id="R_operating",
            critical_inputs=("d_tx_minutes",),
            irrelevant_inputs=tuple(
                name for name in _CONTEXT_FIELDS if name != "taxi_reference"
            ),
        ),
    )
}

_LEGACY_FIELD_SUPPORT = {
    "r_ib_minutes": "ib_support",
    "d_ob_minutes": "d_ob_support",
    "d_tx_minutes": "d_tx_support",
    "d_to_minutes": "d_to_support",
}


def _scenario_value(
    scenario: dict | M2ScenarioInput, name: str
) -> tuple[float | None, SupportState]:
    if isinstance(scenario, M2ScenarioInput):
        value = getattr(scenario, name)
        support = getattr(scenario, f"{name.removesuffix('_minutes')}_support")
    else:
        value = scenario.get(name)
        support_name = _LEGACY_FIELD_SUPPORT[name]
        support = SupportState(scenario.get(support_name, "SUPPORTED"))
    if value is None or support is SupportState.ABSTAIN:
        return None, SupportState.ABSTAIN
    return float(value), support


def _context_value(context: M2ScientificContext, name: str) -> ScientificContextValue:
    return getattr(context, name)


def _itinerary_disruption_events(
    reference: ScientificContextValue | None, d_to: float | None
) -> float | None:
    """Scenario-level missed-connection events under ASSUMPTION_GROUNDED classes.

    Classes are JSON-encoded ``[{"passenger_count": n, "buffer_minutes": b}]``.
    The assumption is literature-parameterized (connection-buffer threshold);
    it is not empirical evidence.
    """
    if reference is None or reference.value is None:
        return None
    if reference.support_state is SupportState.ABSTAIN:
        return None
    if d_to is None:
        return None
    classes = json.loads(str(reference.value))
    return float(
        sum(
            float(item["passenger_count"])
            * (1.0 if d_to > float(item["buffer_minutes"]) else 0.0)
            for item in classes
        )
    )


def _connection_share_value(reference: ScientificContextValue | None) -> float | None:
    if reference is None or reference.value is None or reference.support_state is SupportState.ABSTAIN:
        return None
    try:
        value = float(reference.value)
    except (TypeError, ValueError):
        return None
    return value if 0.0 <= value <= 1.0 else None


def _abstain(
    component: str,
    scenario_id: int,
    scenario_weight: float,
    unit: str,
    driver: str,
    reasons,
    *,
    source_type: SourceType,
    reference_source: str,
    reference_lineage: tuple[str, ...],
    confidence: ExposureConfidence,
    provenance: tuple[str, ...],
):
    return NativeQuantity(
        component_id=component,
        scenario_id=scenario_id,
        scenario_weight=scenario_weight,
        native_quantity=None,
        native_unit=unit,
        driver=driver,
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN,
        source_type=source_type,
        reference_source=reference_source,
        reference_lineage=reference_lineage,
        confidence=confidence,
        reason_code=";".join(sorted(reasons)),
        provenance=provenance,
    )


def native_quantities(
    scenario: dict | M2ScenarioInput, context: M2ScientificContext
) -> tuple[NativeQuantity, ...]:
    """Consume the formal M1 scenario contract (D_OB/D_TX/D_TO).

    M2 never reconstructs M1 delay state from DELTA_OB/T_TX/taxi reference;
    scenarios without the formal fields abstain rather than fabricate values.
    """
    if not isinstance(context, M2ScientificContext):
        context = M2ScientificContext.model_validate(context)
    sid = int(
        scenario.scenario_id
        if isinstance(scenario, M2ScenarioInput)
        else scenario["scenario_id"]
    )
    scenario_weight = float(
        scenario.scenario_weight
        if isinstance(scenario, M2ScenarioInput)
        else scenario["scenario_weight"]
    )
    scenario_reference_lineage = (
        scenario.reference_lineage
        if isinstance(scenario, M2ScenarioInput)
        else ("LEGACY_M2_V1_REFERENCE_LINEAGE_UNAVAILABLE",)
    )
    scenario_provenance = (
        (
            f"episode_id={scenario.episode_id}",
            f"decision_node_id={scenario.decision_node_id}",
            f"m1_scenario_id={scenario.scenario_id}",
            f"m1_scenario_seed_key={scenario.m1_scenario_seed_key}",
            *(f"pre_lineage={item}" for item in scenario.pre_lineage),
            *(f"reference_lineage={item}" for item in scenario.reference_lineage),
        )
        if isinstance(scenario, M2ScenarioInput)
        else ()
    )
    rib, rib_support = _scenario_value(scenario, "r_ib_minutes")
    d_ob, d_ob_support = _scenario_value(scenario, "d_ob_minutes")
    d_tx, d_tx_support = _scenario_value(scenario, "d_tx_minutes")
    d_to, d_to_support = _scenario_value(scenario, "d_to_minutes")

    def ctx(name):
        return _context_value(context, name)

    def expected_pax():
        item = ctx("expected_passengers_per_flight")
        if item is None:
            return None
        return item

    def publish(
        component,
        value,
        unit,
        driver,
        parents,
        context_names=(),
        evidence=EvidenceClass.DERIVED,
        source_type=SourceType.SCENARIO_ASSUMPTION,
    ):
        missing = []
        support_states = []
        provenance = list(scenario_provenance)
        reference_sources = []
        reference_lineage = list(scenario_reference_lineage)
        confidences = []
        for name, parent_value, parent_support in parents:
            support_states.append(parent_support)
            if parent_value is None or parent_support is SupportState.ABSTAIN:
                missing.append(f"{name}_ABSTAIN")
        for name in context_names:
            item = ctx(name)
            if item is None:
                missing.append(f"{name}_MISSING")
                continue
            support_states.append(item.support_state)
            provenance.extend(item.provenance)
            reference_sources.append(item.reference_source or item.object_id)
            reference_lineage.extend(
                (
                    item.reference_id or item.object_id,
                    item.lineage_hash,
                )
            )
            confidences.append(
                item.confidence
                or (
                    ExposureConfidence.NONE
                    if item.support_state is SupportState.ABSTAIN
                    else ExposureConfidence.LOW
                )
            )
            if item.value is None or item.support_state is SupportState.ABSTAIN:
                missing.append(f"{name}_ABSTAIN")
        reference_source = (
            "|".join(reference_sources) if reference_sources else "M1_SCENARIO"
        )
        confidence_rank = {
            ExposureConfidence.NONE: 0,
            ExposureConfidence.LOW: 1,
            ExposureConfidence.MEDIUM: 2,
            ExposureConfidence.HIGH: 3,
        }
        confidence = (
            min(confidences, key=confidence_rank.get)
            if confidences
            else ExposureConfidence.HIGH
        )
        typed_reference_lineage = tuple(sorted(set(reference_lineage)))
        if missing:
            return _abstain(
                component,
                sid,
                scenario_weight,
                unit,
                driver,
                missing,
                source_type=source_type,
                reference_source=reference_source,
                reference_lineage=typed_reference_lineage,
                confidence=confidence,
                provenance=tuple(sorted(set(provenance))),
            )
        state = (
            SupportState.DEGRADED
            if any(item is SupportState.DEGRADED for item in support_states)
            else SupportState.SUPPORTED
        )
        return NativeQuantity(
            component_id=component,
            scenario_id=sid,
            scenario_weight=scenario_weight,
            native_quantity=float(value()),
            native_unit=unit,
            driver=driver,
            evidence_class=evidence,
            support_state=state,
            source_type=source_type,
            reference_source=reference_source,
            reference_lineage=typed_reference_lineage,
            confidence=confidence,
            reason_code=(
                "DEGRADED_PARENT_INPUT" if state is SupportState.DEGRADED else None
            ),
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
            source_type=SourceType.HYBRID,
        ),
        publish(
            "F_execution",
            lambda: d_ob,
            "minutes",
            "additional_off_block_wait",
            (("d_ob_minutes", d_ob, d_ob_support),),
        ),
        publish(
            "F_propagation",
            lambda: d_to * float(ctx("expected_downstream_exposure").value),
            "exposure_minutes",
            "takeoff_delay_x_expected_downstream_exposure",
            (("d_to_minutes", d_to, d_to_support),),
            ("expected_downstream_exposure",),
            source_type=SourceType.HYBRID,
        ),
        publish(
            "P_time",
            lambda: float(expected_pax().value) * d_to,
            "passenger_minutes",
            "expected_passengers_per_flight_x_delay",
            (("d_to_minutes", d_to, d_to_support),),
            ("expected_passengers_per_flight",),
            EvidenceClass.DOMAIN_PROXY,
            SourceType.HYBRID,
        ),
        publish(
            "P_itinerary",
            lambda: float(expected_pax().value)
            * float(_connection_share_value(ctx("connection_share_reference")))
            * (1.0 if d_to > 45.0 else 0.0),
            "expected_disrupted_connecting_passenger_exposure",
            "expected_passengers_x_connecting_share_x_itinerary_threshold",
            (("d_to_minutes", d_to, d_to_support),),
            ("expected_passengers_per_flight", "connection_share_reference"),
            EvidenceClass.DERIVED,
            SourceType.HYBRID,
        ),
        publish(
            "P_service",
            lambda: float(expected_pax().value)
            * (1.0 if d_to >= 180.0 else 0.0),
            "expected_long_delay_passenger_service_exposure",
            "expected_passengers_x_service_threshold",
            (("d_to_minutes", d_to, d_to_support),),
            ("expected_passengers_per_flight",),
            EvidenceClass.DERIVED,
            SourceType.HYBRID,
        ),
        publish(
            "R_operating",
            lambda: d_tx,
            "excess_taxi_minutes",
            "excess_taxi",
            (("d_tx_minutes", d_tx, d_tx_support),),
        ),
    )
    assert tuple(row.component_id for row in rows) == COMPONENTS
    return rows
