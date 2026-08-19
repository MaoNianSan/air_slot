from model.M2.contracts import M2ScientificContext, ScientificContextValue
from model.M2.drivers import COMPONENT_INPUT_CONTRACTS, native_quantities
from model.M2.mapper import M2Mapper
from model.M2.valuation import ValuationRegistry
from model.PRE.transformation import ConstructionType
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import FormalEstimandStatus
from tests.fixtures.p0_p1_contracts import scope_fixture


def context_value(
    object_id,
    value=None,
    *,
    support=SupportState.ABSTAIN,
    evidence=EvidenceClass.UNSUPPORTED,
    construction=ConstructionType.UNSUPPORTED,
    reason="NOT_FROZEN",
):
    return ScientificContextValue(
        object_id=object_id,
        value=value,
        unit="unit",
        support_state=support,
        evidence_class=evidence,
        construction_type=construction,
        reason_code=reason if support is SupportState.ABSTAIN else None,
        provenance=(),
    )


def context(**overrides):
    values = {
        name: context_value(name)
        for name in M2ScientificContext.model_fields
    }
    values.update(overrides)
    return M2ScientificContext(**values)


def supported(object_id, value, *, evidence=EvidenceClass.DERIVED):
    return context_value(
        object_id,
        value,
        support=SupportState.SUPPORTED,
        evidence=evidence,
        construction=ConstructionType.DETERMINISTIC_DERIVATION,
    )


def scenario():
    # Formal M1 scenario contract: D_OB/D_TX/D_TO are M1 outputs; M2 consumes
    # them directly and never reconstructs delay state.
    return {
        "decision_node_id": "n",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "delta_ob_minutes": 5,
        "t_tx_minutes": 15,
        "d_ob_minutes": 5,
        "d_tx_minutes": 0,
        "d_to_minutes": 5,
        "ib_support": "SUPPORTED",
        "delta_ob_support": "SUPPORTED",
        "tx_support": "SUPPORTED",
        "d_ob_support": "SUPPORTED",
        "d_tx_support": "SUPPORTED",
        "d_to_support": "SUPPORTED",
    }


def test_missing_taxi_reference_only_abstains_resource_component():
    rows = native_quantities(
        scenario(),
        context(
            turnaround_reference=supported("turnaround_reference", 5),
        ),
    )
    by_component = {row.component_id: row for row in rows}
    # D_TX is a formal M1 output; R_operating consumes it without needing a
    # second M2-side taxi reference.
    assert by_component["F_execution"].native_quantity == 5
    assert by_component["R_operating"].native_quantity == 0
    assert by_component["R_operating"].support_state is SupportState.SUPPORTED
    assert by_component["F_execution"].support_state is SupportState.SUPPORTED


def test_missing_passenger_reference_does_not_block_flight_components():
    rows = native_quantities(
        scenario(),
        context(turnaround_reference=supported("turnaround_reference", 5)),
    )
    by_component = {row.component_id: row for row in rows}
    assert by_component["F_continuity"].native_quantity == 5
    assert by_component["F_execution"].native_quantity == 5
    assert by_component["P_time"].support_state is SupportState.ABSTAIN


def test_component_drivers_declare_local_input_roles():
    assert COMPONENT_INPUT_CONTRACTS["R_operating"].critical_inputs == (
        "d_tx_minutes",
    )
    assert "taxi_reference" in COMPONENT_INPUT_CONTRACTS["F_execution"].irrelevant_inputs


def test_dev_valuation_never_creates_formal_cu_or_sortable_zero():
    scope = scope_fixture(cu_normalization_registry_id="DEV-1")
    mapper = M2Mapper(ValuationRegistry.smoke(), scope)
    output = mapper.map_scenarios(
        (scenario(),),
        context(turnaround_reference=supported("turnaround_reference", 5)),
    )[0]
    assert all(
        row.constructed_value_cu is None for row in output.component_vector.rows
    )
    assert output.available_component_sum_diagnostic.value_cu is None
    assert output.available_component_sum_diagnostic.sortable is False
    assert (
        output.formal_estimand_value.status
        is FormalEstimandStatus.VALUATION_NOT_FROZEN
    )


def test_unsupported_evidence_is_null_abstain_not_numeric_fallback():
    value = context_value("passenger_exposure")
    assert value.value is None
    assert value.support_state is SupportState.ABSTAIN
    assert value.evidence_class is EvidenceClass.UNSUPPORTED


def test_all_seven_null_diagnostic_is_null_and_never_sortable_zero():
    from tests.fixtures.p0_p1_contracts import consequence

    output = consequence(missing=tuple(M2ScientificContext.model_fields)[:0] + (
        "F_continuity", "F_execution", "F_propagation", "P_time",
        "P_itinerary", "P_service", "R_operating"))
    assert output.available_component_sum_diagnostic.value_cu is None
    assert output.available_component_sum_diagnostic.status == "NO_VALUED_COMPONENTS"
    assert output.available_component_sum_diagnostic.sortable is False
