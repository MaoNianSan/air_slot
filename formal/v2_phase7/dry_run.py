"""Gate-A synthetic and Development-safe scientific smoke pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.decision_contracts import (
    DecisionEvaluation,
    EvaluationFamily,
)
from model.common.enums import OperationalStage, SupportState

from . import constants as C
from .errors import TypedBlocker, _require
from .access_audit import open_access_epoch
from .release import make_release, validate_release_schema


def _dry_run_attention() -> dict[str, Any]:
    from model.M3.stage1 import attention_capacity_k, select_paired_attention

    candidates = (
        ("episode-a", "chain-a", "node-a"),
        ("episode-b", "chain-b", "node-b"),
        ("episode-c", "chain-c", "node-c"),
        ("episode-d", "chain-d", "node-d"),
        ("episode-e", "chain-e", "node-e"),
    )
    delay = tuple(
        PrioritySignal(
            signal_type=SignalKind.DELAY,
            episode_id=episode_id,
            chain_id=chain_id,
            node_id=node_id,
            representation_id=C.REFERENCE_REPRESENTATION_ID,
            score=float(index),
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        for index, (episode_id, chain_id, node_id) in enumerate(candidates, start=1)
    )
    consequence = tuple(
        PrioritySignal(
            signal_type=SignalKind.CONSEQUENCE,
            episode_id=episode_id,
            chain_id=chain_id,
            node_id=node_id,
            representation_id=C.REFERENCE_REPRESENTATION_ID,
            score=float(6 - index),
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        for index, (episode_id, chain_id, node_id) in enumerate(candidates, start=1)
    )
    rows = []
    for q in C.Q_GRID:
        delay_decision, consequence_decision = select_paired_attention(
            delay,
            consequence,
            q=q,
        )
        _require(
            delay_decision.k == consequence_decision.k
            == attention_capacity_k(q, len(candidates)),
            "GATE_A_STAGE1_CAPACITY_MISMATCH",
            q,
        )
        rows.append(
            {
                "q": q,
                "k": delay_decision.k,
                "delay_selected": [
                    item.node_id for item in delay_decision.entries if item.selected
                ],
                "consequence_selected": [
                    item.node_id
                    for item in consequence_decision.entries
                    if item.selected
                ],
            }
        )

    abstaining = PrioritySignal(
        signal_type=SignalKind.CONSEQUENCE,
        episode_id="episode-z",
        chain_id="chain-z",
        node_id="node-z",
        representation_id=C.REFERENCE_REPRESENTATION_ID,
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        comparison_support_mass=0.20,
        comparison_support_threshold=0.90,
        reason_codes=("M2_COMMON_SUPPORT_BELOW_THRESHOLD",),
    )
    mixed = select_paired_attention(
        tuple(delay)
        + (
            PrioritySignal(
                signal_type=SignalKind.DELAY,
                episode_id="episode-z",
                chain_id="chain-z",
                node_id="node-z",
                representation_id=C.REFERENCE_REPRESENTATION_ID,
                score=None,
                support=SupportState.ABSTAIN,
                status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
                comparison_support_mass=0.20,
                comparison_support_threshold=0.90,
            ),
        ),
        tuple(consequence) + (abstaining,),
        q=C.NOMINAL_Q,
    )[1]
    _require(
        all(entry.node_id != "node-z" for entry in mixed.entries),
        "GATE_A_ABSTAINING_NODE_NOT_EXCLUDED",
    )
    return {
        "status": "PASS",
        "q_grid": list(C.Q_GRID),
        "nominal_q": C.NOMINAL_Q,
        "capacity_rows": rows,
        "abstaining_node_typed": True,
    }


def _dry_run_stage2_and_typed() -> dict[str, Any]:
    from model.M2.consequence_service import (
        ConsequenceReferenceBinding,
        M2ConsequenceService,
    )
    from model.M2.scientific_registry import load_active_v2_cu_registry
    from model.M3.solver import solve_with_highs
    from model.M3.stage2 import action_grid, solve_recovery
    from model.M3.transition import TransitionContext
    from model.common.decision_contracts import (
        HeadroomSummary,
        HistoryScope,
        StateRepresentationSpec,
        StateScenario,
        StateScenarioSet,
        TemporalKind,
        UncertaintyKind,
    )

    registry = load_active_v2_cu_registry()
    binding = ConsequenceReferenceBinding(
        reference_id="GATE_A_SYNTHETIC_NODE",
        turnaround_reference_minutes=C.NOMINAL_TURNAROUND_Q20,
        taxi_reference_minutes=0.0,
        expected_pax=150.0,
        connection_share=0.35,
        downstream_exposure=1.2,
    )
    service = M2ConsequenceService(registry, {"gate-a-node": binding})
    representation = StateRepresentationSpec(
        temporal=TemporalKind.HISTORY,
        uncertainty=UncertaintyKind.JOINT,
        history_capacity=16,
        history_scope=HistoryScope.FULL_PREFIX,
    )
    scenarios = (
        StateScenario(
            scenario_id=0,
            scenario_weight=0.5,
            stage=OperationalStage.PRE_IB,
            t_ib_minutes=620.0,
            d_ob_minutes=90.0,
            d_tx_minutes=15.0,
            d_to_minutes=105.0,
        ),
        StateScenario(
            scenario_id=1,
            scenario_weight=0.5,
            stage=OperationalStage.PRE_IB,
            t_ib_minutes=650.0,
            d_ob_minutes=110.0,
            d_tx_minutes=20.0,
            d_to_minutes=130.0,
        ),
    )
    state_set = StateScenarioSet(
        episode_id="gate-a-episode",
        chain_id="gate-a-chain",
        node_id="gate-a-node",
        stage=OperationalStage.PRE_IB,
        representation=representation,
        scenarios=scenarios,
    )
    context = TransitionContext(
        sobt_minutes=600.0,
        turnaround_lower_bound_minutes=C.NOMINAL_TURNAROUND_Q20,
    )
    headroom = HeadroomSummary(
        u_max=C.NOMINAL_U_MAX,
        turnaround_lower_bound_q=C.NOMINAL_TURNAROUND_Q20,
        turnaround_quantile=0.20,
        headroom_quantile=0.90,
        headroom_positive_n=10,
        source_id="GATE_A_SYNTHETIC_NOT_SCIENTIFIC_SUPPORT",
        floor_to_minutes=5.0,
    )
    parity = solve_with_highs(
        state_set,
        context=context,
        service=service,
        headroom_summary=headroom,
    )
    _require(parity.u_star_parity, "GATE_A_HIGHS_ENUMERATION_ACTION_DISAGREEMENT")
    _require(parity.objective_parity, "GATE_A_HIGHS_ENUMERATION_OBJECTIVE_DISAGREEMENT")
    _require(
        parity.recoverable_value_parity,
        "GATE_A_HIGHS_ENUMERATION_VALUE_DISAGREEMENT",
    )
    _require(
        parity.recoverable_value_formal
        >= -C.M3_NUMERICAL_COMPARISON_TOLERANCE,
        "GATE_A_NEGATIVE_RECOVERABLE_VALUE",
    )
    _require(
        parity.u_star_formal in action_grid(C.NOMINAL_U_MAX),
        "GATE_A_ACTION_OUTSIDE_SPECIFICATION_GRID",
    )

    action_grid_contracts = {
        name: list(action_grid(u_max))
        for name, u_max in C.U_MAX_BY_SPECIFICATION.items()
    }
    _require(
        action_grid_contracts["Q80"][-1] == 25.0
        and action_grid_contracts["nominal"][-1] == 45.0
        and action_grid_contracts["Q95"][-1] == 75.0,
        "GATE_A_SPECIFICATION_DEPENDENT_GRID_INVALID",
    )

    non_actionable = solve_recovery(
        StateScenarioSet(
            episode_id="gate-a-taxi",
            chain_id="gate-a-taxi-chain",
            node_id="gate-a-taxi",
            stage=OperationalStage.POST_OB_PRE_TO,
            representation=representation,
            scenarios=(
                StateScenario(
                    scenario_id=0,
                    scenario_weight=1.0,
                    stage=OperationalStage.POST_OB_PRE_TO,
                    t_ib_minutes=10.0,
                    d_ob_minutes=5.0,
                    d_tx_minutes=0.0,
                    d_to_minutes=5.0,
                ),
            ),
        ),
        context=context,
        service=service,
    )
    _require(
        non_actionable.actionable_status is TypedStatus.NOT_ACTIONABLE,
        "GATE_A_TAXI_COMP_NOT_ACTIONABLE",
    )
    _require(non_actionable.u_star == 0.0, "GATE_A_TAXI_COMP_POSITIVE_ACTION")
    _require(
        non_actionable.recoverable_value is None,
        "GATE_A_TAXI_COMP_UNDEFINED_VALUE_NOT_TYPED",
    )

    undefined = DecisionEvaluation(
        reference_id="reference",
        comparator_id="comparator",
        cohort_id="empty-or-zero",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=0.0,
        reference_recoverable_value=0.0,
        L_rec=None,
        A0=None,
        A5=None,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE,
    )
    _require(
        undefined.value_status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE
        and undefined.L_rec is None,
        "GATE_A_TYPED_UNDEFINED_NOT_PRESERVED",
    )
    empty_attention = DecisionEvaluation(
        reference_id="reference",
        comparator_id="comparator",
        cohort_id="empty-reference-cohort",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=0.0,
        reference_attention_value=0.0,
        L_att=None,
        support_status=SupportState.ABSTAIN,
        value_status=TypedStatus.N_A_NOT_DEFINED,
    )
    _require(
        empty_attention.value_status is TypedStatus.N_A_NOT_DEFINED,
        "GATE_A_EMPTY_COHORT_TYPED_STATE_MISSING",
    )

    reference_attention = DecisionEvaluation(
        reference_id="reference",
        comparator_id="reference",
        cohort_id="reference",
        family=EvaluationFamily.ATTENTION,
        delta_attention_value=0.0,
        reference_attention_value=1.0,
        L_att=0.0,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )
    reference_recovery = DecisionEvaluation(
        reference_id="reference",
        comparator_id="reference",
        cohort_id="reference",
        family=EvaluationFamily.RECOVERY,
        delta_recovery_objective=0.0,
        reference_recoverable_value=1.0,
        L_rec=0.0,
        A0=1.0,
        A5=1.0,
        support_status=SupportState.SUPPORTED,
        value_status=TypedStatus.SUPPORTED,
    )
    _require(
        reference_attention.L_att == 0.0
        and reference_recovery.L_rec == 0.0
        and reference_recovery.A0 == reference_recovery.A5 == 1.0,
        "GATE_A_REFERENCE_INVARIANTS_NOT_PRESERVED",
    )

    return {
        "status": "PASS",
        "formal_solver": parity.formal_solver,
        "parity_oracle": parity.parity_oracle,
        "u_star_formal": parity.u_star_formal,
        "u_star_oracle": parity.u_star_oracle,
        "objective_absolute_error": parity.objective_absolute_error,
        "recoverable_value_absolute_error": parity.recoverable_value_absolute_error,
        "recoverable_value_formal": parity.recoverable_value_formal,
        "tie_break_applied": parity.tie_break_applied,
        "near_tie_candidate_count": parity.near_tie_candidate_count,
        "action_grid_by_specification": action_grid_contracts,
        "typed_states": {
            "NOT_ACTIONABLE": True,
            "UNDEFINED_ZERO_RECOVERABLE_VALUE": True,
            "N/A_NOT_DEFINED": True,
        },
        "reference_invariants": {
            "L_att": reference_attention.L_att,
            "L_rec": reference_recovery.L_rec,
            "A0": reference_recovery.A0,
            "A5": reference_recovery.A5,
        },
        "reference_authority": {
            "reference_representation_id": C.REFERENCE_REPRESENTATION_ID,
            "H_C_STAR": C.REFERENCE_AUTHORITY,
            "R_STAR": C.STAGE2_INFORMATION_COHORT,
        },
    }


def run_dry_run() -> dict[str, Any]:
    """Run the Gate-A synthetic and Development-safe scientific smoke."""

    try:
        from validation.m3_enumeration_highs_parity import run_cases as parity_cases
    except Exception as error:  # pragma: no cover - environment failure path
        raise TypedBlocker("GATE_A_ENVIRONMENT_IMPORT_FAILED", str(error)) from error

    parity = parity_cases()
    _require(
        parity.get("status") == "PASS",
        "GATE_A_M3_PARITY_DRY_RUN_FAILED",
        parity,
    )
    attention = _dry_run_attention()
    stage2 = _dry_run_stage2_and_typed()
    with tempfile.TemporaryDirectory(prefix="air_slot_phase7_gate_a_") as directory:
        audit_path = Path(directory) / "PHASE7_ACCESS_AUDIT.json"
        release = make_release()
        first = open_access_epoch(
            audit_path,
            release,
            timestamp="2026-09-19T00:00:00+00:00",
        )
        second = open_access_epoch(
            audit_path,
            release,
            timestamp="2026-09-19T00:00:01+00:00",
        )
        _require(
            first["access_epoch_id"] == second["access_epoch_id"],
            "GATE_A_ACCESS_EPOCH_ID_NOT_STABLE",
        )
        _require(
            second["retry_within_same_epoch"] is True
            and second["phase7_increment"] == 1
            and second["current_total"] == 2,
            "GATE_A_ACCESS_EPOCH_RETRY_INCREMENTED",
        )
    return {
        "status": "PASS",
        "scope": "SYNTHETIC_AND_DEVELOPMENT_SAFE_FIXTURES_ONLY",
        "final_test_data_read": False,
        "q4_raw_read": False,
        "legacy_final_test_result_tree_read": False,
        "parity": parity,
        "attention": attention,
        "stage2": stage2,
        "release_schema": validate_release_schema(make_release()),
        "access_epoch_idempotence": {
            "status": "PASS",
            "same_epoch_retry_increment": 0,
            "epoch_increment": C.PHASE7_ACCESS_INCREMENT,
            "current_total": C.PHASE7_CURRENT_TOTAL,
            "one_epoch_per_release": True,
        },
    }


__all__ = [
    "_dry_run_attention",
    "_dry_run_stage2_and_typed",
    "run_dry_run",
]
