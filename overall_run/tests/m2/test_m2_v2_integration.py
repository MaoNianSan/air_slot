from __future__ import annotations

from dataclasses import replace

import pytest

from overall_run.src.m2 import build_m2_input, reconstruct_pre_action_loss, summarize_episode
from overall_run.src.m2.contracts import M2InputStatus, PassengerContext, ResourceContext, ValuationContext


VALUES = {name: 1.0 for name in (
    "F_TURN", "F_WAIT", "F_PROPAGATION", "P_DELAY", "P_CONNECTION",
    "P_CARE", "R_GROUND", "R_TAXI", "R_SCARCITY",
)}


def _valuation():
    return ValuationContext(
        subitem_value_parameters=VALUES,
        rule_parameters={
            "P_CARE": {"threshold_minutes": 60.0},
            "R_GROUND": {"context_gamma": 0.5},
            "R_TAXI": {"context_gamma": 0.5},
            "R_SCARCITY": {"wait_threshold_minutes": 30.0},
        },
        valuation_version="TEST_VALUES_V1",
    )


def _passenger():
    return PassengerContext(100.0, 0.5, 20.0, 0.2, "OFFICIAL_OPERATIONAL")


def _resource():
    return ResourceContext(0.5, 0.5, 0.5, 0.5, "OFFICIAL_OPERATIONAL")


def test_synthetic_m1_to_m2_direct_structural_compact(m1_scenario_factory) -> None:
    bundle = build_m2_input(m1_scenario_factory(), passenger_context=_passenger(), resource_context=_resource(), valuation_context=_valuation())
    assert bundle.input_status is M2InputStatus.VALID
    losses = reconstruct_pre_action_loss(bundle)
    assert all(loss.sample_weight == 0.25 for loss in losses)
    assert all(loss.extra_offblock_wait_minutes == bundle.joint_scenarios[loss.sample_id].r_ob_minutes for loss in losses)
    assert all(loss.total_pre_action_loss_rmb == loss.total_constructed_units for loss in losses)
    summary = summarize_episode(losses)
    assert summary.rmb_summary["mean"] is not None
    assert summary.rmb_summary["cvar90"] is not None


def test_unsupported_subitems_are_not_relabelled_as_zero(m1_scenario_factory) -> None:
    bundle = build_m2_input(m1_scenario_factory(), passenger_context=PassengerContext(), resource_context=_resource(), valuation_context=_valuation())
    assert bundle.input_status is M2InputStatus.PARTIAL
    loss = reconstruct_pre_action_loss(bundle)[0]
    assert loss.passenger_delay_quantity is None
    assert loss.passenger_loss_rmb is None
    assert loss.total_pre_action_loss_rmb is not None


def test_unresolved_overflow_abstains_and_blocks_formal_tail(m1_scenario_factory) -> None:
    bundle = build_m2_input(m1_scenario_factory(tail_status="TAIL_UNRESOLVED", overflow=True), passenger_context=_passenger(), resource_context=_resource(), valuation_context=_valuation())
    assert bundle.input_status is M2InputStatus.ABSTAIN
    losses = reconstruct_pre_action_loss(bundle)
    assert all(loss.total_pre_action_loss_rmb is None for loss in losses)
    summary = summarize_episode(losses)
    assert summary.rmb_summary["q95"] is None
    assert summary.rmb_summary["cvar90"] is None


def test_adapter_rejects_m1_structural_identity_mismatch(m1_scenario_factory) -> None:
    scenario = m1_scenario_factory()
    broken = replace(
        scenario.joint_samples[0],
        r_ob_minutes=scenario.joint_samples[0].r_ob_minutes + 5.0,
    )
    scenario = replace(
        scenario,
        joint_samples=(broken,) + scenario.joint_samples[1:],
    )
    with pytest.raises(ValueError, match="M2_R_OB_IDENTITY_FAILED"):
        build_m2_input(
            scenario,
            passenger_context=_passenger(),
            resource_context=_resource(),
            valuation_context=_valuation(),
        )
