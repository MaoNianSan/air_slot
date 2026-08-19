"""Tests C and D — scenario lineage preservation and M2 consuming formal fields.

Test C: the same scenario identity (episode, node, id, weight) survives from
M1 through M2 into M4.  Test D: M2 consumes D_OB/D_TX/D_TO directly and
abstains instead of reconstructing delay state from DELTA_OB/T_TX/taxi ref.
"""

import pytest

from model.M2.contracts import M2ScientificContext, ScientificContextValue
from model.M2.drivers import native_quantities
from model.PRE.transformation import ConstructionType
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.scenario_lineage import (
    aligned_scenario_ids,
    scenario_lineage_key,
    validate_same_lineage,
)
from tests.m2.test_mapping import context, supported


def m1_rows():
    return [
        {
            "episode_id": "e", "decision_node_id": "n", "scenario_id": index,
            "scenario_weight": 1.0 / 3,
        }
        for index in range(3)
    ]


def m2_rows():
    return [
        {
            "episode_id": "e", "decision_node_id": "n", "scenario_id": index,
            "scenario_weight": 1.0 / 3,
        }
        for index in range(3)
    ]


def test_c_lineage_identity_preserved_across_m1_m2_m4():
    m4_rows = [
        {
            "episode_id": "e", "decision_node_id": "n", "scenario_id": index,
            "scenario_weight": 1.0 / 3,
        }
        for index in range(3)
    ]
    validate_same_lineage(m1_rows(), m2_rows(), m4_rows)
    assert aligned_scenario_ids(m1_rows()) == (0, 1, 2)
    assert scenario_lineage_key(m1_rows()[0]) == scenario_lineage_key(m4_rows[0])


def test_c_lineage_mismatch_is_rejected():
    bad = m2_rows()
    bad[0] = {**bad[0], "scenario_id": 9}
    with pytest.raises(ContractError, match="SCENARIO_LINEAGE"):
        validate_same_lineage(m1_rows(), bad)


def _formal_scenario(**overrides):
    row = {
        "decision_node_id": "n",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "delta_ob_minutes": -10,
        "t_tx_minutes": 30,
        "d_ob_minutes": 0,
        "d_tx_minutes": 18,
        "d_to_minutes": 18,
        "ib_support": "SUPPORTED",
        "delta_ob_support": "SUPPORTED",
        "tx_support": "SUPPORTED",
        "d_ob_support": "SUPPORTED",
        "d_tx_support": "SUPPORTED",
        "d_to_support": "SUPPORTED",
    }
    row.update(overrides)
    return row


def test_d_m2_consumes_formal_fields_and_never_reconstructs_d_to():
    ctx = context(
        turnaround_reference=supported("turnaround_reference", 5),
        expected_downstream_exposure=supported("expected_downstream_exposure", 1.0),
        passenger_exposure=supported("passenger_exposure", 100.0),
        service_policy_reference=supported("service_policy_reference", 15.0),
    )
    rows = native_quantities(_formal_scenario(), ctx)
    by_component = {row.component_id: row for row in rows}
    # D_OB = max(0, -10) = 0 and D_TX = max(0, 30-12) = 18 drive M2 directly.
    assert by_component["F_execution"].native_quantity == 0
    assert by_component["R_operating"].native_quantity == 18
    assert by_component["F_propagation"].native_quantity == 18.0
    assert by_component["P_time"].native_quantity == 100.0 * 18.0
    # No M2-side taxi reference is consulted for delay state.
    assert all(
        "taxi_reference_ABSTAIN" not in (row.reason_code or "")
        for row in rows
    )


def test_d_legacy_only_scenario_abstains_instead_of_reconstructing():
    legacy = {
        "decision_node_id": "n",
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "r_ib_minutes": 10,
        "delta_ob_minutes": 20,
        "t_tx_minutes": 15,
        "ib_support": "SUPPORTED",
        "delta_ob_support": "SUPPORTED",
        "tx_support": "SUPPORTED",
    }
    ctx = context(
        turnaround_reference=supported("turnaround_reference", 5),
        expected_downstream_exposure=supported("expected_downstream_exposure", 1.0),
        passenger_exposure=supported("passenger_exposure", 100.0),
        service_policy_reference=supported("service_policy_reference", 15.0),
    )
    rows = native_quantities(legacy, ctx)
    by_component = {row.component_id: row for row in rows}
    assert by_component["F_execution"].support_state is SupportState.ABSTAIN
    assert by_component["F_propagation"].support_state is SupportState.ABSTAIN
    assert by_component["P_time"].support_state is SupportState.ABSTAIN
    assert by_component["R_operating"].support_state is SupportState.ABSTAIN
    # F_continuity still works from R_IB; legacy delay inputs are not used.
    assert by_component["F_continuity"].native_quantity == 5
