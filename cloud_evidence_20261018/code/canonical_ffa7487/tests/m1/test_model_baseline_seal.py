"""Regression gates for the frozen model baseline seal.

These tests exercise the active overflow contract and verify that finite raw
overflow values are not clipped before a complete seven-component M4 risk
evaluation.  They use synthetic values only; no data or model artifacts are
materialized here.
"""

from math import isfinite

import torch

from model.M1.contracts import (
    HazardBinContract,
    HurdleQuantileContract,
    M1V2Scenario,
)
from model.M1.pipeline import M1Pipeline
from model.M1.scenario_layer.sampler import ancestral_sample_v2
from model.M4.m3_action_interface import (
    ComparisonScopeStatus,
    ComparisonSupportRequirement,
    ConsequenceComparisonScope,
    M4ActionEnvelopeInput,
)
from model.M4.residual_risk import evaluate_residual_risk, load_active_risk_policy
from model.M4.scientific_registry import load_active_rmb_mapping
from model.M3.action_response import ResponseSourceType, ResponseSupportClass
from model.M3.contracts import InstantiationState
from model.M3.action_response import EligibilityState
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.enums import SupportState
from model.common.identity import content_id


def _contract(target: str, maximum: int) -> HurdleQuantileContract:
    return HurdleQuantileContract(
        target_name=target,
        max_finite_minutes=maximum,
        bin_width_minutes=5,
        quantile_levels=(0.1, 0.3, 0.5, 0.7, 0.9),
        upper_tail_policy="FINITE_SUPPORT_BINS_PLUS_EXPLICIT_TAIL_CLASS",
    )


def _hash(seed: str) -> str:
    return content_id({"seed": seed})


def _m4_overflow_envelope() -> M4ActionEnvelopeInput:
    mapping = load_active_rmb_mapping()
    scope = ConsequenceComparisonScope(
        scope_id="MODEL_BASELINE_SEAL_SYNTHETIC_SCOPE",
        component_ids=CONSEQUENCE_COMPONENTS,
        support_requirements={
            component: ComparisonSupportRequirement.NON_ABSTAIN_FINITE_CU
            for component in CONSEQUENCE_COMPONENTS
        },
        valuation_measurement_registry_id=mapping.registry_id,
        version="MODEL_BASELINE_SEAL_SYNTHETIC_V1",
        provenance=("MODEL_BASELINE_SEAL_SYNTHETIC",),
        status=ComparisonScopeStatus.FROZEN,
    )
    # The first component carries the D_OB overflow scalar and the second the
    # D_TX overflow scalar.  Values are deliberately left above finite support.
    values = (181.0, 61.0, 1.0, 1.0, 1.0, 1.0, 1.0)
    scenario = {
        "scenario_id": 0,
        "scenario_weight": 1.0,
        "components": tuple(
            {
                "component_id": component,
                "C_a_CU": value,
                "support_state": SupportState.SUPPORTED.value,
                "baseline_cu_artifact_id": _hash(f"cu:{component}"),
                "baseline_reference_lineage_hash": _hash(f"ref:{component}"),
            }
            for component, value in zip(CONSEQUENCE_COMPONENTS, values, strict=True)
        ),
    }
    return M4ActionEnvelopeInput(
        episode_id="baseline-seal-synthetic",
        decision_node_id="node-0",
        action_id="A00",
        action_family="null",
        instantiation_state=InstantiationState.FORMED,
        eligibility_state=EligibilityState.ELIGIBLE,
        opportunity_state="NOT_REQUIRED",
        eligibility_id=_hash("eligibility"),
        response_support=ResponseSupportClass.SUPPORTED,
        response_rule_id="M3_A00_SYNTHETIC",
        response_rule_hash=_hash("response-rule"),
        response_source_type=ResponseSourceType.OPERATIONAL_RULE,
        response_source_references=("MODEL_BASELINE_SEAL_SYNTHETIC",),
        response_parameter_version="MODEL_BASELINE_SEAL_SYNTHETIC_V1",
        response_freeze_id="MODEL_BASELINE_SEAL_SYNTHETIC",
        response_provenance=("MODEL_BASELINE_SEAL_SYNTHETIC",),
        scenario_ids=(0,),
        scenario_weights=(1.0,),
        scenario_consequences=(scenario,),
        comparison_scope=scope,
        m3_envelope_hash=_hash("m3-envelope"),
    )


def test_active_overflow_classifier_preserves_finite_and_overflow_states():
    t_ib = HazardBinContract(bin_width_minutes=5, max_finite_minutes=360)
    d_ob = _contract("D_OB", 180)
    d_tx = _contract("D_TX", 60)

    for contract, finite_values, overflow_values in (
        (t_ib, (359.0, 360.0), (360.001, 365.0)),
        (d_ob, (179.0, 180.0), (180.001, 185.0)),
        (d_tx, (59.0, 60.0), (60.001, 65.0)),
    ):
        assert all(contract.tail_state(contract.encode(value)) is None for value in finite_values)
        assert all(
            contract.tail_state(contract.encode(value)) == "OVERFLOW"
            for value in overflow_values
        )


def test_observed_continuous_overflow_scalars_retain_metadata():
    pipeline = M1Pipeline.smoke(input_size=4)
    history = pipeline.model.encode_history(
        torch.zeros(1, 1, 4), torch.ones(1, dtype=torch.long)
    )
    rows = ancestral_sample_v2(
        pipeline.model,
        history,
        pipeline.contracts,
        episode_id="baseline-seal-observed-overflow",
        decision_node_id="node-0",
        stage="COMPLETED",
        observed={
            "T_IB_A00": "2019-01-01T06:05:00+00:00",
            "D_OB": 180.001,
            "D_TX": 60.001,
        },
        count=1,
        seed=7,
        target_support={
            name: SupportState.SUPPORTED.value
            for name in ("T_IB_A00", "D_OB", "D_TX")
        },
        decision_time_utc="2019-01-01T00:00:00+00:00",
    )
    assert len(rows) == 1
    assert rows[0].d_ob_minutes == 180.001
    assert rows[0].d_tx_minutes == 60.001
    assert rows[0].overflow_t_ib
    assert rows[0].overflow_d_ob
    assert rows[0].overflow_d_tx


def test_finite_overflow_scalars_reach_m4_cvar_without_clipping():
    d_ob = _contract("D_OB", 180)
    d_tx = _contract("D_TX", 60)
    scenario = M1V2Scenario(
        episode_id="baseline-seal-synthetic",
        decision_node_id="node-0",
        scenario_id=0,
        scenario_weight=1.0,
        operational_stage="COMPLETED",
        decision_time_utc="2019-01-01T00:00:00+00:00",
        t_ib_a00_utc="2019-01-01T00:30:00+00:00",
        d_ob_minutes=181.0,
        d_tx_minutes=61.0,
        d_ob_support=SupportState.SUPPORTED.value,
        d_tx_support=SupportState.SUPPORTED.value,
        t_ib_support=SupportState.SUPPORTED.value,
        scenario_seed_key="synthetic-overflow",
        overflow_d_ob=d_ob.tail_state(d_ob.encode(181.0)) == "OVERFLOW",
        overflow_d_tx=d_tx.tail_state(d_tx.encode(61.0)) == "OVERFLOW",
    )
    assert scenario.d_ob_minutes == 181.0
    assert scenario.d_tx_minutes == 61.0
    assert scenario.overflow_d_ob and scenario.overflow_d_tx

    result = evaluate_residual_risk(
        _m4_overflow_envelope(),
        monetary_mapping=load_active_rmb_mapping(),
        risk_policy=load_active_risk_policy(),
    )
    assert result.numerical_state.value == "DEFINED"
    assert result.monetary_loss_cvar_alpha is not None
    assert isfinite(result.monetary_loss_cvar_alpha)
    assert result.scenario_losses[0].component_losses[0].C_a_CU == 181.0
    assert result.scenario_losses[0].component_losses[1].C_a_CU == 61.0

