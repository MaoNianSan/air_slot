from __future__ import annotations

from dataclasses import replace

import pytest

from overall_run.src.m2 import (
    build_m2_input,
    build_m2_input_from_pre,
    evaluate_joint_scenarios,
    reconstruct_pre_action_loss,
    summarize_episode,
)
from overall_run.src.m2.contracts import (
    AvailabilityStatus,
    M2InputStatus,
    PassengerContext,
)
from overall_run.src.failures import M3ContractMismatch
from overall_run.src.pipeline import run_experiment

from .test_m2_rules_and_units import valuation


def test_pre_to_m2_direct_structural_compact(
    m2_pre_bundle, m2_scenario_context_factory
) -> None:
    scenario, expected_context = m2_scenario_context_factory()
    bundle = build_m2_input_from_pre(
        m2_pre_bundle, scenario, valuation_context=valuation()
    )
    assert bundle.input_status is M2InputStatus.VALID
    assert bundle.normalization_version == expected_context.normalization_version
    assert bundle.context_provenance["resource_scarcity"]["transformation"] == "ONE_MINUS_UNIT_INTERVAL"
    losses = reconstruct_pre_action_loss(bundle)
    assert all(loss.sample_weight == 0.25 for loss in losses)
    assert all(
        loss.extra_offblock_wait_minutes
        == bundle.joint_scenarios[loss.sample_id].r_ob_minutes
        for loss in losses
    )
    assert all(
        loss.total_pre_action_loss_rmb == loss.total_constructed_units
        for loss in losses
    )
    summary = summarize_episode(losses)
    assert summary.rmb_summary["mean"] is not None
    assert summary.rmb_summary["cvar90"] is not None
    assert summary.formal_cvar90_available is True
    assert summary.m4_gate_status == "READY_FOR_M4_CONTRACT"
    assert sum(
        value for value in summary.channel_loss_shares.values() if value is not None
    ) == pytest.approx(1.0)


def test_unsupported_subitems_are_not_relabelled_as_zero(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    support = dict(context.context_support)
    for field in ("passenger_load_proxy", "connection_slack", "connection_pressure"):
        support[field] = AvailabilityStatus.UNSUPPORTED
    context = replace(
        context,
        passenger_context=PassengerContext(),
        context_support=support,
    )
    bundle = build_m2_input(scenario, context, valuation_context=valuation())
    assert bundle.input_status is M2InputStatus.ABSTAIN
    loss = reconstruct_pre_action_loss(bundle)[0]
    assert loss.passenger_delay_quantity is None
    assert loss.passenger_loss_rmb is None
    assert loss.total_pre_action_loss_rmb is None


def test_unresolved_overflow_abstains_and_blocks_formal_tail(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory(
        tail_status="TAIL_UNRESOLVED", overflow=True
    )
    bundle = build_m2_input(scenario, context, valuation_context=valuation())
    assert bundle.input_status is M2InputStatus.ABSTAIN
    assert bundle.audit_context.unresolved_sample_ids == (0,)
    losses = reconstruct_pre_action_loss(bundle)
    assert losses[0].total_pre_action_loss_rmb is None
    assert losses[0].resolved_only_total_pre_action_loss_rmb is None
    assert all(
        loss.total_pre_action_loss_rmb is None for loss in losses
    )
    assert all(
        loss.resolved_only_total_pre_action_loss_rmb is not None
        for loss in losses[1:]
    )
    summary = summarize_episode(losses)
    assert summary.rmb_summary["q95"] is None
    assert summary.rmb_summary["cvar90"] is None
    assert summary.rmb_summary["resolved_only_q95"] is not None
    assert summary.rmb_summary["resolved_only_cvar90"] is not None
    assert summary.unresolved_probability == 0.25
    assert summary.m4_gate_status == "M2_TAIL_NOT_READY_FOR_M4"


def test_adapter_rejects_m1_structural_identity_mismatch(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    broken = replace(
        scenario.joint_samples[0],
        r_ob_minutes=scenario.joint_samples[0].r_ob_minutes + 5.0,
    )
    scenario = replace(
        scenario,
        joint_samples=(broken,) + scenario.joint_samples[1:],
    )
    with pytest.raises(ValueError, match="M2_R_OB_IDENTITY_FAILED"):
        build_m2_input(scenario, context, valuation_context=valuation())


def test_joint_scenario_evaluation_does_not_change_sampling_model(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    bundle = build_m2_input(scenario, context, valuation_context=valuation())
    losses = reconstruct_pre_action_loss(bundle)
    result = evaluate_joint_scenarios(bundle, losses)
    assert result["sampling_model_changed"] is False
    assert result["dependence_mode"] == "CONDITIONAL_INDEPENDENCE_WITH_STRUCTURAL_COUPLING"
    assert set(result["joint_tail_frequency"]) == {
        "R_OB_GT_30_AND_T_TX_GT_15",
        "TURN_GT_0_AND_EXTRA_TAXI_GT_15",
        "D_OB_GT_30_AND_D_TO_GT_60",
    }


def test_m3_contract_mismatch_remains_real() -> None:
    with pytest.raises(M3ContractMismatch, match="M3_CONTRACT_MISMATCH"):
        run_experiment(None, "fast")
