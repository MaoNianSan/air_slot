from datetime import UTC, datetime, timedelta

import pytest

from exp.exp2.model_inputs import (
    active_model_contract,
    flatten_node,
    map_model_outputs,
    typed_m1_inputs,
)
from exp.exp2.protocol import COMPONENTS, INHERITED_SUPPORT_BLOCK
from model.M1.contracts import M1V2Scenario
from model.M2.context import (
    AirportReferenceKeys,
    build_m2_v4_context,
    build_node_exposure_references,
    load_data2_reference_bundle,
    smoke_reference_payloads,
)
from model.M2.exposure import (
    NodeExposureRequest,
    ScheduledLegReference,
    resolve_node_specific_exposure,
)


def _scenario(
    scenario_id: int, weight: float, d_ob: float, d_tx: float
) -> M1V2Scenario:
    decision = datetime(2019, 8, 1, 10, tzinfo=UTC)
    return M1V2Scenario(
        episode_id="episode",
        decision_node_id="node",
        scenario_id=scenario_id,
        scenario_weight=weight,
        operational_stage="PRE_IB",
        decision_time_utc=decision.isoformat(),
        t_ib_a00_utc=(decision + timedelta(minutes=30)).isoformat(),
        d_ob_minutes=d_ob,
        d_tx_minutes=d_tx,
        t_ib_support="SUPPORTED",
        d_ob_support="SUPPORTED",
        d_tx_support="SUPPORTED",
        scenario_seed_key=f"seed-{scenario_id}",
    )


def _context():
    bundle = load_data2_reference_bundle(smoke_reference_payloads())
    keys = AirportReferenceKeys(
        connection_airport_id="ABE", successor_destination_airport_id="ATL"
    )
    decision = datetime(2019, 8, 1, 10, tzinfo=UTC)
    request = NodeExposureRequest(
        decision_node_id="node",
        current_flight_id="current",
        current_aircraft_id="N1",
        connection_airport_id="ABE",
        successor_destination_airport_id="ATL",
        scheduled_arrival_anchor_utc=decision + timedelta(hours=1),
        information_cutoff_utc=decision,
        schedule_snapshot_complete=True,
    )
    leg = ScheduledLegReference(
        flight_id="next",
        aircraft_id="N1",
        origin_airport_id="ABE",
        destination_airport_id="ATL",
        scheduled_departure_utc=decision + timedelta(hours=2),
        scheduled_arrival_utc=decision + timedelta(hours=3),
        availability_time_utc=decision,
        reference_id="schedule-freeze",
    )
    exposure = resolve_node_specific_exposure(
        request, (leg,), build_node_exposure_references(bundle, keys)
    )
    return build_m2_v4_context(bundle, keys, node_specific_exposure=exposure)


def test_active_registry_and_ontology_are_exact_v4():
    frozen, _, scope = active_model_contract()
    assert frozen.registry_id == "M2_DATA2_FORMAL_CU_V4"
    assert frozen.scientific_status == "FROZEN"
    assert frozen.implementation_status == "MATCH"
    assert frozen.final_test_access_count == 0
    assert tuple(frozen.formal_scope) == COMPONENTS
    assert tuple(scope.included_components) == COMPONENTS
    assert all(frozen.scale(component) > 0 for component in COMPONENTS)


def test_model_outputs_supply_native_and_frozen_cu_without_exp2_formula():
    scenarios = (_scenario(0, 0.4, 10, 5), _scenario(1, 0.6, 20, 10))
    typed = typed_m1_inputs(
        scenarios, pre_lineage=("pre",), reference_lineage=("reference",)
    )
    mapped = map_model_outputs(typed, _context())
    row = flatten_node(
        typed,
        mapped,
        metadata={"operational_stage": "PRE_IB"},
        inherited_support={"primary": True, "sensitivity": True},
    )
    frozen, _, _ = active_model_contract()
    assert row["delay_to_mean"] == pytest.approx(0.4 * 15 + 0.6 * 30)
    for component in COMPONENTS:
        assert row[f"Z_{component}"] == pytest.approx(
            row[f"{component}_native"] / frozen.scale(component)
        )


def test_inherited_support_must_be_explicit():
    scenarios = (_scenario(0, 1.0, 0, 0),)
    typed = typed_m1_inputs(
        scenarios, pre_lineage=("pre",), reference_lineage=("reference",)
    )
    mapped = map_model_outputs(typed, _context())
    with pytest.raises(RuntimeError, match=INHERITED_SUPPORT_BLOCK):
        flatten_node(
            typed,
            mapped,
            metadata={"operational_stage": "PRE_IB"},
            inherited_support=None,
        )


def test_missing_component_is_not_renormalized_and_valid_zero_survives():
    scenarios = (_scenario(0, 0.5, 0, 0), _scenario(1, 0.5, 10, 0))
    typed = typed_m1_inputs(
        scenarios, pre_lineage=("pre",), reference_lineage=("reference",)
    )
    mapped = list(map_model_outputs(typed, _context()))
    complete = flatten_node(
        typed,
        mapped,
        metadata={"operational_stage": "PRE_IB"},
        inherited_support={"primary": True, "sensitivity": True},
    )
    assert complete["R_operating_native"] == 0
    assert complete["Z_R_operating"] == 0

    rows = list(mapped[1].component_vector.rows)
    index = next(i for i, item in enumerate(rows) if item.component_id == "P_time")
    rows[index] = rows[index].model_copy(
        update={
            "support_state": "ABSTAIN",
            "native_quantity": None,
            "constructed_value_cu": None,
        }
    )
    mapped[1] = mapped[1].model_copy(
        update={
            "component_vector": mapped[1].component_vector.model_copy(
                update={"rows": tuple(rows)}
            )
        }
    )
    incomplete = flatten_node(
        typed,
        mapped,
        metadata={"operational_stage": "PRE_IB"},
        inherited_support={"primary": True, "sensitivity": True},
    )
    assert incomplete["P_time_native"] is None
    assert incomplete["Z_P_time"] is None
    assert incomplete["aggregate_complete"] is False


def test_model_service_enforces_scenario_weights():
    scenarios = (_scenario(0, 0.4, 1, 1), _scenario(1, 0.4, 2, 2))
    typed = typed_m1_inputs(
        scenarios, pre_lineage=("pre",), reference_lineage=("reference",)
    )
    with pytest.raises(ValueError, match="WEIGHTS_MUST_SUM_TO_ONE"):
        map_model_outputs(typed, _context())
