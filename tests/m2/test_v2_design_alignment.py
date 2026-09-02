from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from model.M1.contracts import M1V2Scenario
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_v2_context,
    build_m2_v2_scope,
    build_node_exposure_references,
    load_data2_reference_bundle,
    smoke_reference_payloads,
)
from model.M2.contracts import (
    ConsequenceState,
    ExposureConfidence,
    ExposureSupportLevel,
    M2ScenarioInput,
    ScientificContextValue,
    SourceType,
)
from model.M2.exposure import (
    NodeExposureReferences,
    NodeExposureRequest,
    ScheduledLegReference,
    resolve_node_specific_exposure,
)
from model.M2.mapper import M2Mapper
from model.M2.summary import summarize_formal_consequence
from model.M2.valuation import M2CUNormalizationAdapter
from model.PRE.transformation import ConstructionType
from model.common.cu_normalization import CUNormalizationRegistry
from model.common.enums import EvidenceClass, SupportState
from tests.fixtures.p0_p1_contracts import consequence, monetary_fixture


def _m1_scenario(scenario_id=7, weight=1.0, *, d_ob=20.0, d_tx=10.0):
    decision = datetime(2019, 1, 1, 12, 0, tzinfo=UTC).isoformat()
    t_ib = datetime(2019, 1, 1, 12, 30, tzinfo=UTC).isoformat()
    return M1V2Scenario(
        episode_id="episode-1",
        decision_node_id="node-1",
        scenario_id=scenario_id,
        scenario_weight=weight,
        operational_stage="PRE_IB",
        decision_time_utc=decision,
        t_ib_a00_utc=t_ib,
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED",
        d_tx_support="SUPPORTED",
        scenario_seed_key=f"seed-{scenario_id}",
        taxi_reference_id="taxi-ref",
    )


def _input(scenario=None):
    return M2ScenarioInput.from_m1(
        scenario or _m1_scenario(),
        pre_lineage=("pre-state-hash",),
        reference_lineage=("static-reference-hash",),
    )


def _request(**updates):
    base = {
        "decision_node_id": "node-1",
        "current_flight_id": "current",
        "current_aircraft_id": "N1",
        "connection_airport_id": "ABE",
        "successor_destination_airport_id": "ATL",
        "scheduled_arrival_anchor_utc": datetime(2019, 1, 1, 12, tzinfo=UTC),
        "information_cutoff_utc": datetime(2019, 1, 1, 10, tzinfo=UTC),
        "schedule_snapshot_complete": True,
    }
    base.update(updates)
    return NodeExposureRequest(**base)


def _leg(*, flight="next", aircraft="N1", origin="ABE", minutes=60, available=None):
    anchor = datetime(2019, 1, 1, 12, tzinfo=UTC)
    return ScheduledLegReference(
        flight_id=flight,
        aircraft_id=aircraft,
        origin_airport_id=origin,
        destination_airport_id="ATL",
        scheduled_departure_utc=anchor + timedelta(minutes=minutes),
        scheduled_arrival_utc=anchor + timedelta(minutes=minutes + 60),
        availability_time_utc=available or datetime(2019, 1, 1, 9, tzinfo=UTC),
        reference_id="schedule-freeze",
    )


def _reference(name, value):
    return ScientificContextValue(
        object_id=name,
        value=value,
        unit="legs",
        support_state=SupportState.SUPPORTED,
        evidence_class=EvidenceClass.DERIVED,
        construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
        reference_period="2019-H1",
        freeze_id=f"freeze-{name}",
        source_type=SourceType.DATA,
        reference_source=name,
    )


def _runtime():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    keys = AirportReferenceKeys(
        connection_airport_id="ABE",
        successor_destination_airport_id="ATL",
    )
    exposure = resolve_node_specific_exposure(
        _request(), (_leg(),), build_node_exposure_references(bundle, keys)
    )
    context = build_m2_v2_context(
        bundle, keys, node_specific_exposure=exposure
    )
    scope = build_m2_v2_scope()
    registry = CUNormalizationRegistry.from_scales(
        registry_id=scope.cu_normalization_registry_id,
        version="TEST-1",
        freeze_id="test-train-freeze",
        reference_period="train-only",
        scales={name: 10.0 for name in scope.included_components},
        provenance=("TEST_FIXTURE_NOT_SCIENTIFIC_FREEZE",),
    )
    return M2Mapper(M2CUNormalizationAdapter(registry), scope), context


def test_a_m2_consumes_strict_m1_scenario_only():
    typed = _input()
    assert typed.d_to_minutes == 30.0
    with pytest.raises(ValidationError):
        M2ScenarioInput.model_validate(
            {**typed.model_dump(), "future_observation": 99.0}
        )
    mapper, context = _runtime()
    with pytest.raises(TypeError, match="TYPED_M1_SCENARIO"):
        mapper.map_m1_scenarios((typed.model_dump(),), context)


def test_b_no_future_information_leakage():
    with pytest.raises(ValidationError):
        ScheduledLegReference.model_validate(
            {**_leg().model_dump(), "actual_departure_utc": datetime.now(UTC)}
        )
    future_publication = _leg(
        available=datetime(2019, 1, 1, 11, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="FUTURE_SCHEDULE_REFERENCE"):
        resolve_node_specific_exposure(
            _request(), (future_publication,), NodeExposureReferences()
        )


def test_c_d_j_scenario_identity_d_to_and_lineage_are_preserved():
    typed = _input()
    mapper, context = _runtime()
    output = mapper.map_m1_scenarios((typed,), context)[0]
    assert output.scenario_id == typed.scenario_id
    assert output.episode_id == typed.episode_id
    assert typed.d_to_minutes == typed.d_ob_minutes + typed.d_tx_minutes
    assert output.pre_lineage == ("pre-state-hash",)
    assert output.reference_lineage == ("static-reference-hash", "taxi-ref")
    assert any(
        "pre_lineage=pre-state-hash" in item
        for item in output.component_vector.rows[0].provenance
    )
    resolved = summarize_formal_consequence((output,))
    assert resolved.status == "AVAILABLE"
    assert resolved.reason_code is None
    with pytest.raises(ValidationError, match="M2_D_TO_IDENTITY_VIOLATION"):
        M2ScenarioInput.model_validate(
            {**typed.model_dump(), "d_to_minutes": 29.0}
        )


def test_e_f_g_cu_is_native_normalization_not_money():
    mapper, context = _runtime()
    typed = _input()
    before = mapper.map_m1_scenarios((typed,), context)[0]
    execution = next(
        row for row in before.component_vector.rows
        if row.component_id == "F_execution"
    )
    assert execution.native_quantity == 20.0
    assert execution.constructed_value_cu == 2.0
    assert execution.native_unit == "minutes"
    monetary_fixture(weights={name: 1.0 for name in mapper.consequence_scope.included_components})
    monetary_fixture(weights={name: 999.0 for name in mapper.consequence_scope.included_components})
    after = mapper.map_m1_scenarios((typed,), context)[0]
    assert before == after


def test_h_unsupported_component_cannot_silently_be_supported():
    with pytest.raises(ValidationError, match="UNSUPPORTED_EVIDENCE_MUST_ABSTAIN"):
        ScientificContextValue(
            object_id="invented-itinerary",
            value=1.0,
            unit="events",
            support_state=SupportState.SUPPORTED,
            evidence_class=EvidenceClass.UNSUPPORTED,
            construction_type=ConstructionType.UNSUPPORTED,
            source_type=SourceType.DATA,
        )


def test_i_downstream_fallback_hierarchy_is_explicit():
    same_aircraft = resolve_node_specific_exposure(
        _request(), (_leg(),), NodeExposureReferences()
    )
    assert same_aircraft.value == 1.0
    assert same_aircraft.support_level is ExposureSupportLevel.SAME_AIRCRAFT_SUCCESSOR_CHAIN
    assert same_aircraft.confidence is ExposureConfidence.HIGH

    references = NodeExposureReferences(
        same_route=_reference("route", 3.0),
        airport=_reference("airport", 2.0),
        global_reference=_reference("global", 1.0),
    )
    route = resolve_node_specific_exposure(
        _request(current_aircraft_id=None, schedule_snapshot_complete=False),
        (),
        references,
    )
    assert route.support_level is ExposureSupportLevel.SAME_ROUTE_PROPAGATION
    assert route.value == 3.0
    airport = resolve_node_specific_exposure(
        _request(current_aircraft_id=None, schedule_snapshot_complete=False),
        (),
        references.model_copy(update={"same_route": None}),
    )
    assert airport.support_level is ExposureSupportLevel.AIRPORT_REFERENCE
    global_value = resolve_node_specific_exposure(
        _request(current_aircraft_id=None, schedule_snapshot_complete=False),
        (),
        NodeExposureReferences(global_reference=_reference("global", 1.0)),
    )
    assert global_value.support_level is ExposureSupportLevel.GLOBAL_REFERENCE


def test_k_action_effect_is_not_mixed_into_native_consequence():
    mapper, context = _runtime()
    output = mapper.map_m1_scenarios((_input(),), context)[0]
    assert output.consequence_state is ConsequenceState.BASELINE
    assert output.action_id is None
    assert output.action_adjustments_applied is False
    with pytest.raises(ValidationError, match="BASELINE_CANNOT_CONTAIN_ACTION_EFFECT"):
        output.model_validate(
            {
                **output.model_dump(exclude_computed_fields=True),
                "action_id": "A11",
                "action_adjustments_applied": True,
            }
        )


def test_l_train_frozen_normalization_is_reproducible():
    mapper, context = _runtime()
    typed = _input()
    first = mapper.map_m1_scenarios((typed,), context)[0]
    second = mapper.map_m1_scenarios((typed,), context)[0]
    assert first.component_vector == second.component_vector


def test_preserved_scenarios_support_mean_variance_cvar_and_tail():
    low = consequence(
        scenario_id=0, scenario_weight=0.5, values={"F_execution": 10.0}
    ).model_copy(update={"episode_id": "episode"})
    high = consequence(
        scenario_id=1, scenario_weight=0.5, values={"F_execution": 30.0}
    ).model_copy(update={"episode_id": "episode"})
    summary = summarize_formal_consequence(
        (low, high), cvar_alpha=0.5, tail_threshold_cu=20.0
    )
    assert summary.mean_cu == 20.0
    assert summary.variance_cu2 == 100.0
    assert summary.cvar_cu == 30.0
    assert summary.tail_probability == 0.5
