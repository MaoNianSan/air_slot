from __future__ import annotations

from dataclasses import replace

import pytest

from src.m4 import (
    adapt_m4_inputs,
    assign_decision_lane,
    build_evidence_context,
    evaluate_opportunity,
    evaluate_stage,
    run_m4_synthetic_integration,
)
from src.m4.contracts import DecisionLane, M4ContractError
from src.m4.stage_adapter import StageCompatibility


def _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides, *, stage="t1"):
    return run_m4_synthetic_integration(
        bundle,
        losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping={"TURNAROUND": stage},
        opportunity_overrides=opportunity_overrides,
    )


def test_flow_pressure_not_resource_availability(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(provenance_updates={
        "resource_availability": {
            "source_field": "airport_flow_pressure",
            "transformation": "ONE_MINUS_UNIT_INTERVAL",
        },
    })
    with pytest.raises(M4ContractError, match="PRESSURE_TO_RESOURCE"):
        build_evidence_context(bundle)


def test_ground_occupancy_not_handler_availability(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(provenance_updates={
        "ground_handler_availability": {"source_field": "ground_occupancy_proxy"},
    })
    with pytest.raises(M4ContractError, match="OCCUPANCY_TO_HANDLER"):
        build_evidence_context(bundle)


def test_scenario_parameter_never_formal(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory(provenance_updates={
        "execution_window_margin": {"evidence_type": "SCENARIO_PARAMETER"},
    })
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    row = artifact.action_frame.set_index("action_id").loc["A12"]
    assert row["decision_lane"] == "SCENARIO"


def test_unsupported_critical_field_not_formal(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory(provenance_updates={
        "execution_window_margin": {"evidence_type": "UNSUPPORTED"},
    })
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A12", "decision_lane"] != "FORMAL"


def test_proxy_not_labeled_observed(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(provenance_updates={
        "passenger_load_proxy": {
            "evidence_type": "EMPIRICAL_REFERENCE",
            "proxy_labeled_observed": True,
        },
    })
    with pytest.raises(M4ContractError, match="PROXY_TO_OBSERVED"):
        build_evidence_context(bundle)


def test_external_standard_requires_assumption_match(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory(provenance_updates={
        "passenger_care_rule": {
            "evidence_type": "EXTERNAL_STANDARD",
            "assumption_match_status": "MISMATCH",
        },
    })
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides, stage="t3")
    row = artifact.action_frame.set_index("action_id").loc["A33"]
    assert row["decision_lane"] == "SCENARIO"
    assert "PRE_ASSUMPTION_MISMATCH" in row["reason_codes"]


def test_no_future_observed_chain(m4_input_factory) -> None:
    bundle, _ = m4_input_factory(provenance_updates={
        "downstream_leg_count": {
            "evidence_type": "EMPIRICAL_REFERENCE",
            "future_observed_chain_used": True,
        },
    })
    with pytest.raises(M4ContractError, match="FUTURE_OBSERVED_CHAIN"):
        build_evidence_context(bundle)


def test_missing_not_zero_filled(m4_input_factory, replace_loss) -> None:
    bundle, losses = m4_input_factory()
    subitems = dict(losses[0].subitem_loss_rmb)
    subitems["F_TURN"] = None
    broken = (replace_loss(losses[0], subitem_loss_rmb=subitems), *losses[1:])
    from src.m4 import validate_m2_inputs

    with pytest.raises(M4ContractError, match="VALUE_MISSING_OR_INVALID"):
        validate_m2_inputs(bundle, broken)


def test_taxi_action_not_formal_when_reference_unsupported(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A13", "decision_lane"] == "SCENARIO"


def test_rebooking_not_formal_without_supply_support(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A31", "decision_lane"] == "SCENARIO"


def test_stage_mapping_is_explicit(m4_input_factory, m3_artifact) -> None:
    bundle, losses = m4_input_factory()
    adapted = adapt_m4_inputs(
        bundle,
        losses,
        m3_artifact,
        stage_mapping={"TURNAROUND": "t1"},
        stage_mapping_version="TEST_STAGE_V1",
        stage_mapping_test_only=True,
    )
    action = m3_artifact.action_catalog["A12"]
    result = evaluate_stage(
        action,
        source_stage=adapted.snapshot_stage,
        mapping=adapted.stage_mapping,
        mapping_version=adapted.stage_mapping_version,
        mapping_test_only=True,
    )
    assert result.configured and result.mapped_stage == "t1" and result.applicable


def test_stage_mapping_not_guessed(m4_input_factory, m3_artifact) -> None:
    bundle, losses = m4_input_factory()
    adapted = adapt_m4_inputs(bundle, losses, m3_artifact)
    result = evaluate_stage(
        m3_artifact.action_catalog["A12"],
        source_stage=adapted.snapshot_stage,
        mapping=None,
        mapping_version=None,
        mapping_test_only=False,
    )
    assert not result.configured
    assert result.reason_code == "STAGE_CONTRACT_NOT_FROZEN"


def test_unfrozen_stage_contract_blocks_non_A00_formal(
    cfg, m4_input_factory, m3_artifact
) -> None:
    bundle, losses = m4_input_factory()
    artifact = run_m4_synthetic_integration(
        bundle, losses, m3_artifact, cfg.scientific
    )
    row = artifact.action_frame.set_index("action_id").loc["A12"]
    assert row["decision_lane"] != "FORMAL"
    assert "STAGE_CONTRACT_NOT_FROZEN" in row["reason_codes"]


def test_stage_not_applicable_excluded(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides, stage="t3")
    assert artifact.action_frame.set_index("action_id").loc["A12", "decision_lane"] == "EXCLUDED"


def test_formal_supported_not_formal_when_parameters_unfrozen(
    m4_input_factory, m3_artifact
) -> None:
    bundle, losses = m4_input_factory()
    adapted = adapt_m4_inputs(bundle, losses, m3_artifact)
    adapted = replace(adapted, test_only=False)
    action = m3_artifact.action_catalog["A12"]
    stage = StageCompatibility(True, True, "t1", "FORMAL_SUPPORTED", "FROZEN_TEST", False)
    opportunity = evaluate_opportunity(action, overrides={"A12": 1.0})
    lane, reasons = assign_decision_lane(
        action_id="A12", bundle=adapted, stage=stage, opportunity=opportunity
    )
    assert lane is DecisionLane.CONDITIONAL
    assert "M3_PARAMETER_NOT_FROZEN" in reasons


def test_partial_supported_not_automatically_formal(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A51", "decision_lane"] != "FORMAL"


def test_scenario_only_maps_scenario(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A71", "decision_lane"] == "SCENARIO"


def test_resource_dependency_maps_scenario_without_resource_data(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.action_frame.set_index("action_id").loc["A42", "decision_lane"] == "SCENARIO"


def test_passenger_proxy_maps_conditional_when_connection_not_formal(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides, stage="t3")
    assert artifact.action_frame.set_index("action_id").loc["A33", "decision_lane"] == "CONDITIONAL"


def test_test_only_never_publication_formal(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    bundle, losses = m4_input_factory()
    artifact = _artifact(cfg, bundle, losses, m3_artifact, opportunity_overrides)
    assert artifact.test_only is True
    assert artifact.publication_allowed is False


def test_contract_failure_maps_excluded(m4_input_factory, m3_artifact) -> None:
    bundle, losses = m4_input_factory()
    adapted = adapt_m4_inputs(bundle, losses, m3_artifact)
    action = m3_artifact.action_catalog["A12"]
    stage = StageCompatibility(False, False, None, "CONTRACT_MISMATCH", None, False)
    lane, _ = assign_decision_lane(
        action_id="A12",
        bundle=adapted,
        stage=stage,
        opportunity=evaluate_opportunity(action),
    )
    assert lane is DecisionLane.EXCLUDED
