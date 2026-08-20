from datetime import UTC, datetime

from model.M2.contracts import (
    COMPONENTS,
    ExposureConfidence,
    ExposureSupportLevel,
    ScenarioConsequenceDistribution,
    ScientificContextValue,
    SourceType,
)
from model.M2.drivers import native_quantities
from model.M2.exposure import (
    NodeExposureReferences,
    NodeExposureRequest,
    resolve_node_specific_exposure,
)
from model.M2.summary import summarize_formal_consequence
from model.M2.valuation import M2CUNormalizationAdapter
from model.PRE.transformation import ConstructionType
from model.common.cu_normalization import CUNormalizationRegistry
from model.common.enums import EvidenceClass, SupportState
from tests.fixtures.p0_p1_contracts import consequence, monetary_fixture
from tests.m2.test_v2_design_alignment import _input, _runtime


def test_formal_rows_carry_complete_scenario_and_reference_contract():
    mapper, context = _runtime()
    typed = _input()
    output = mapper.map_m1_scenarios((typed,), context)[0]
    assert tuple(row.component_id for row in output.component_vector.rows) == COMPONENTS
    for row in output.component_vector.rows:
        assert row.scenario_id == typed.scenario_id
        assert row.scenario_weight == typed.scenario_weight
        assert row.reference_source
        assert row.reference_lineage
        assert row.reference_lineage_hash.startswith("sha256:")
        assert row.native_artifact_id.startswith("sha256:")
        assert row.cu_quantity.native_artifact_id == row.native_artifact_id
        assert row.confidence in ExposureConfidence
    assert output.reference_lineage == ("static-reference-hash", "taxi-ref")


def test_cu_artifact_is_version_sensitive_and_monetary_independent():
    mapper, context = _runtime()
    native = next(
        item
        for item in native_quantities(_input(), context)
        if item.component_id == "F_execution"
    )
    scales = {component: 10.0 for component in COMPONENTS}
    registry_v1 = CUNormalizationRegistry.from_scales(
        registry_id=mapper.consequence_scope.cu_normalization_registry_id,
        version="V1",
        freeze_id="scale-freeze-v1",
        reference_period="train",
        scales=scales,
    )
    registry_v2 = CUNormalizationRegistry.from_scales(
        registry_id=mapper.consequence_scope.cu_normalization_registry_id,
        version="V2",
        freeze_id="scale-freeze-v2",
        reference_period="train",
        scales=scales,
    )
    row_v1 = M2CUNormalizationAdapter(registry_v1).value(native)
    monetary_fixture(weights={component: 1.0 for component in COMPONENTS})
    monetary_fixture(weights={component: 999.0 for component in COMPONENTS})
    row_v1_repeat = M2CUNormalizationAdapter(registry_v1).value(native)
    row_v2 = M2CUNormalizationAdapter(registry_v2).value(native)
    assert row_v1 == row_v1_repeat
    assert row_v1.constructed_value_cu == row_v2.constructed_value_cu == 2.0
    assert row_v1.cu_artifact_id != row_v2.cu_artifact_id
    assert row_v1.cu_quantity.registry_hash != row_v2.cu_quantity.registry_hash
    assert row_v1.cu_quantity.compatible_with_registry(registry_v1)
    assert not row_v1.cu_quantity.compatible_with_registry(registry_v2)
    assert row_v1.cu_quantity.scale_freeze_id == "scale-freeze-v1"
    assert row_v1.cu_quantity.reference_period == "train"


def _route_reference(version: str) -> ScientificContextValue:
    return ScientificContextValue(
        object_id="route-exposure",
        value=2.0,
        unit="legs",
        support_state=SupportState.SUPPORTED,
        evidence_class=EvidenceClass.DERIVED,
        construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
        reference_period="2019-H1",
        freeze_id=f"route-freeze-{version}",
        source_type=SourceType.DATA,
        reference_source="ROUTE_REFERENCE",
        reference_id="route-reference-id",
        reference_version=version,
        confidence=ExposureConfidence.MEDIUM,
    )


def _exposure_request() -> NodeExposureRequest:
    return NodeExposureRequest(
        decision_node_id="node",
        current_flight_id="flight",
        current_aircraft_id=None,
        connection_airport_id="ABE",
        successor_destination_airport_id="ATL",
        scheduled_arrival_anchor_utc=datetime(2019, 1, 1, 12, tzinfo=UTC),
        information_cutoff_utc=datetime(2019, 1, 1, 10, tzinfo=UTC),
        schedule_snapshot_complete=False,
    )


def test_e_down_lineage_is_deterministic_and_reference_version_sensitive():
    first = resolve_node_specific_exposure(
        _exposure_request(),
        (),
        NodeExposureReferences(same_route=_route_reference("V1")),
    )
    repeat = resolve_node_specific_exposure(
        _exposure_request(),
        (),
        NodeExposureReferences(same_route=_route_reference("V1")),
    )
    changed = resolve_node_specific_exposure(
        _exposure_request(),
        (),
        NodeExposureReferences(same_route=_route_reference("V2")),
    )
    assert first.support_level is ExposureSupportLevel.SAME_ROUTE_PROPAGATION
    assert first.reference_source == "route-exposure"
    assert first.reference_id == "route-reference-id"
    assert first.confidence is ExposureConfidence.MEDIUM
    assert first.lineage_hash == repeat.lineage_hash
    assert first.lineage_hash != changed.lineage_hash


def test_passenger_abstention_is_preserved_in_formal_output():
    mapper, context = _runtime()
    output = mapper.map_m1_scenarios((_input(),), context)[0]
    by_component = {row.component_id: row for row in output.component_vector.rows}
    assert by_component["P_time"].support_state is SupportState.SUPPORTED
    for component in ("P_itinerary", "P_service"):
        assert by_component[component].support_state is SupportState.ABSTAIN
        assert by_component[component].native_quantity is None
        assert by_component[component].constructed_value_cu is None


def test_distribution_object_preserves_all_weights_and_changes_risk_summary():
    low_heavy = ScenarioConsequenceDistribution(
        consequences=(
            consequence(scenario_id=0, scenario_weight=0.9, values={"F_execution": 10}),
            consequence(scenario_id=1, scenario_weight=0.1, values={"F_execution": 30}),
        )
    )
    high_heavy = ScenarioConsequenceDistribution(
        consequences=(
            consequence(scenario_id=0, scenario_weight=0.3, values={"F_execution": 10}),
            consequence(scenario_id=1, scenario_weight=0.7, values={"F_execution": 30}),
        )
    )
    low_summary = summarize_formal_consequence(low_heavy, cvar_alpha=0.5)
    high_summary = summarize_formal_consequence(high_heavy, cvar_alpha=0.5)
    assert low_heavy.scenario_ids == high_heavy.scenario_ids == (0, 1)
    assert low_heavy.scenario_weights == (0.9, 0.1)
    assert high_heavy.scenario_weights == (0.3, 0.7)
    assert low_summary.mean_cu != high_summary.mean_cu
    assert low_summary.variance_cu2 != high_summary.variance_cu2
    assert low_summary.cvar_cu != high_summary.cvar_cu
