"""M4 common-basis evaluator tests (V2 Phase 4)."""

from __future__ import annotations

import pytest

from model.M3.stage1 import select_attention
from model.M4.evaluation import (
    AttentionEvaluation,
    RecoveryEvaluation,
    aggregate_attention_evaluations,
    aggregate_recovery_evaluations,
    evaluate_attention_allocation,
    evaluate_recovery_loss,
)
from model.common.decision_contracts import (
    DecisionEvaluation,
    EvaluationFamily,
    PrioritySignal,
    SignalKind,
    TypedStatus,
)
from model.common.enums import SupportState
from model.common.errors import ContractError


def _decision(
    kind: SignalKind,
    scores: dict[str, float],
    *,
    q: float = 0.10,
):
    signals = tuple(
        PrioritySignal(
            signal_type=kind,
            episode_id="episode-1",
            chain_id="chain-1",
            node_id=node_id,
            representation_id="HISTORY_H16:JOINT",
            score=score,
            support=SupportState.SUPPORTED,
            status=TypedStatus.SUPPORTED,
            comparison_support_mass=0.95,
            comparison_support_threshold=0.90,
        )
        for node_id, score in sorted(scores.items())
    )
    return select_attention(signals, q=q)


def _attention_pair():
    reference_priority = {"n1": 10.0, "n2": 8.0, "n3": 2.0, "n4": 1.0}
    reference = _decision(SignalKind.CONSEQUENCE, reference_priority)
    comparator = _decision(
        SignalKind.DELAY, {"n1": 1.0, "n2": 9.0, "n3": 0.0, "n4": 0.0}
    )
    return reference_priority, reference, comparator


def _evaluation_pair():
    return evaluate_attention_allocation(
        cohort_id="COHORT_A",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:DELAY",
        reference_decision=_attention_pair()[1],
        comparator_decision=_attention_pair()[2],
        reference_priority=_attention_pair()[0],
    )


def test_attention_loss_uses_reference_consequence_basis() -> None:
    reference_priority, reference, comparator = _attention_pair()
    evaluation = evaluate_attention_allocation(
        cohort_id="COHORT_A",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:DELAY",
        reference_decision=reference,
        comparator_decision=comparator,
        reference_priority=reference_priority,
    )
    assert evaluation.reference_shortlist == ("n1",)
    assert evaluation.comparator_shortlist == ("n2",)
    assert evaluation.reference_attention_value == pytest.approx(10.0)
    assert evaluation.comparator_attention_value == pytest.approx(8.0)
    assert evaluation.delta_attention_value == pytest.approx(2.0)
    assert evaluation.L_att == pytest.approx(0.2)
    assert evaluation.overlap_count == 0
    assert evaluation.entered == ("n2",)
    assert evaluation.displaced == ("n1",)
    assert evaluation.diagnostics["coverage_total_reference"] == pytest.approx(
        10.0 / 21.0
    )
    assert evaluation.diagnostics["coverage_total_comparator"] == pytest.approx(
        8.0 / 21.0
    )
    assert evaluation.kendall_tau is not None
    assert evaluation.spearman_rho is not None

    contract = evaluation.contract_record()
    assert contract.family is EvaluationFamily.ATTENTION
    assert contract.L_att == pytest.approx(0.2)
    assert "L_total" not in DecisionEvaluation.model_fields


def test_attention_domain_coverage_is_reported_separately() -> None:
    reference_priority, reference, comparator = _attention_pair()
    domain_scores = {
        "n1": {"F": 10.0, "P": 0.0, "R": 0.0},
        "n2": {"F": 0.0, "P": 8.0, "R": 0.0},
        "n3": {"F": 0.0, "P": 0.0, "R": 2.0},
        "n4": {"F": 0.0, "P": 0.0, "R": 1.0},
    }
    evaluation = evaluate_attention_allocation(
        cohort_id="COHORT_A",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:DELAY",
        reference_decision=reference,
        comparator_decision=comparator,
        reference_priority=reference_priority,
        reference_domain_scores=domain_scores,
    )
    assert evaluation.diagnostics["coverage_F_reference"] == pytest.approx(1.0)
    assert evaluation.diagnostics["coverage_F_comparator"] == pytest.approx(0.0)
    assert evaluation.diagnostics["coverage_P_reference"] == pytest.approx(0.0)
    assert evaluation.diagnostics["coverage_P_comparator"] == pytest.approx(1.0)
    assert evaluation.diagnostics["coverage_R_reference"] == pytest.approx(0.0)
    assert evaluation.diagnostics["coverage_R_comparator"] == pytest.approx(0.0)


def test_zero_reference_attention_value_is_typed_not_zero_filled() -> None:
    reference_priority = {"n1": 0.0, "n2": 0.0, "n3": 0.0, "n4": 0.0}
    reference = _decision(SignalKind.CONSEQUENCE, reference_priority)
    comparator = _decision(
        SignalKind.DELAY, {"n1": 0.0, "n2": 1.0, "n3": 0.0, "n4": 0.0}
    )
    evaluation = evaluate_attention_allocation(
        cohort_id="COHORT_ZERO",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:DELAY",
        reference_decision=reference,
        comparator_decision=comparator,
        reference_priority=reference_priority,
    )
    assert evaluation.reference_attention_value == 0.0
    assert evaluation.L_att is None
    assert evaluation.status is TypedStatus.N_A_NOT_DEFINED
    assert "M4_ATTENTION_REFERENCE_VALUE_ZERO" in evaluation.reason_codes
    contract = evaluation.contract_record()
    assert contract.L_att is None
    assert contract.value_status is TypedStatus.N_A_NOT_DEFINED
    assert contract.support_status is SupportState.ABSTAIN


def test_attention_requires_one_shared_candidate_queue() -> None:
    reference = _decision(
        SignalKind.CONSEQUENCE, {"n1": 1.0, "n2": 2.0, "n3": 3.0}
    )
    comparator = _decision(SignalKind.DELAY, {"n1": 1.0, "n2": 2.0})
    with pytest.raises(ContractError, match="M4_ATTENTION_CANDIDATE_QUEUE_MISMATCH"):
        evaluate_attention_allocation(
            cohort_id="COHORT_A",
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:DELAY",
            reference_decision=reference,
            comparator_decision=comparator,
            reference_priority={"n1": 1.0, "n2": 2.0, "n3": 3.0},
        )


def test_recovery_loss_uses_fixed_cohort_and_reference_objective() -> None:
    fixed_cohort = ("n1", "n2", "n3", "n4", "n5")
    reference_actions = {"n1": 5.0, "n2": 0.0, "n3": 10.0, "n4": 5.0, "n5": 0.0}
    comparator_actions = {"n1": 0.0, "n2": 5.0, "n3": 5.0, "n4": 10.0, "n5": 0.0}
    reference_objectives = {
        ("n1", 5.0): 2.0,
        ("n1", 0.0): 2.5,
        ("n2", 0.0): 1.0,
        ("n2", 5.0): 1.2,
        ("n3", 10.0): 1.0,
        ("n3", 5.0): 1.4,
        ("n4", 5.0): 0.5,
        ("n4", 10.0): 0.9,
        ("n5", 0.0): 0.3,
    }
    recoverable_values = {"n1": 0.5, "n2": 0.2, "n3": 0.4, "n4": 0.1, "n5": 0.0}
    evaluation = evaluate_recovery_loss(
        cohort_id="R_STAR",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        fixed_cohort=fixed_cohort,
        reference_actions=reference_actions,
        comparator_actions=comparator_actions,
        reference_objectives=reference_objectives,
        reference_recoverable_values=recoverable_values,
    )
    assert evaluation.delta_objectives == {
        "n1": pytest.approx(0.5),
        "n2": pytest.approx(0.2),
        "n3": pytest.approx(0.4),
        "n4": pytest.approx(0.4),
        "n5": pytest.approx(0.0),
    }
    assert evaluation.reference_recoverable_value == pytest.approx(1.2)
    assert evaluation.delta_recovery_objective == pytest.approx(1.5)
    assert evaluation.L_rec == pytest.approx(1.25)
    assert evaluation.A0 == pytest.approx(0.2)
    assert evaluation.A5 == pytest.approx(1.0)
    assert evaluation.activation_events == {
        "MISSED_ACTIVATION": 1,
        "FALSE_ACTIVATION": 1,
        "UNDER_RECOVERY": 1,
        "OVER_RECOVERY": 1,
    }
    contract = evaluation.contract_record()
    assert contract.family is EvaluationFamily.RECOVERY
    assert contract.L_rec == pytest.approx(1.25)
    assert contract.delta_recovery_objective == pytest.approx(1.5)
    assert "L_total" not in DecisionEvaluation.model_fields


def test_zero_reference_recoverable_value_is_typed() -> None:
    evaluation = evaluate_recovery_loss(
        cohort_id="R_STAR",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        fixed_cohort=("n1",),
        reference_actions={"n1": 5.0},
        comparator_actions={"n1": 0.0},
        reference_objectives={("n1", 5.0): 1.0, ("n1", 0.0): 2.0},
        reference_recoverable_values={"n1": 0.0},
    )
    assert evaluation.reference_recoverable_value == 0.0
    assert evaluation.delta_recovery_objective == pytest.approx(1.0)
    assert evaluation.L_rec is None
    assert evaluation.status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE
    contract = evaluation.contract_record()
    assert contract.L_rec is None
    assert contract.value_status is TypedStatus.UNDEFINED_ZERO_RECOVERABLE_VALUE


def test_recovery_requires_reference_objective_for_comparator_action() -> None:
    with pytest.raises(
        ContractError, match="M4_RECOVERY_COMPARATOR_OBJECTIVE_MISSING"
    ):
        evaluate_recovery_loss(
            cohort_id="R_STAR",
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            fixed_cohort=("n1",),
            reference_actions={"n1": 5.0},
            comparator_actions={"n1": 7.0},
            reference_objectives={("n1", 5.0): 1.0},
            reference_recoverable_values={"n1": 1.0},
        )


def test_recovery_requires_fixed_cohort_keys() -> None:
    with pytest.raises(ContractError, match="M4_COMPARATOR_ACTIONS_KEY_MISMATCH"):
        evaluate_recovery_loss(
            cohort_id="R_STAR",
            reference_id="HISTORY_H16:JOINT",
            comparator_id="HISTORY_H16:POINT",
            fixed_cohort=("n1", "n2"),
            reference_actions={"n1": 5.0, "n2": 0.0},
            comparator_actions={"n1": 5.0},
            reference_objectives={
                ("n1", 5.0): 1.0,
                ("n2", 0.0): 1.0,
            },
            reference_recoverable_values={"n1": 1.0, "n2": 0.0},
        )


def test_aggregate_attention_loss_is_ratio_of_summed_values() -> None:
    first = _evaluation_pair()
    second = evaluate_attention_allocation(
        cohort_id="COHORT_B",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:DELAY",
        reference_decision=_decision(
            SignalKind.CONSEQUENCE,
            {"m1": 100.0, "m2": 99.0, "m3": 0.0, "m4": 0.0},
        ),
        comparator_decision=_decision(
            SignalKind.DELAY,
            {"m1": 0.0, "m2": 100.0, "m3": 0.0, "m4": 0.0},
        ),
        reference_priority={"m1": 100.0, "m2": 99.0, "m3": 0.0, "m4": 0.0},
    )
    aggregate = aggregate_attention_evaluations((first, second))
    assert aggregate.delta_attention_value == pytest.approx(3.0)
    assert aggregate.reference_attention_value == pytest.approx(110.0)
    assert aggregate.L_att == pytest.approx(3.0 / 110.0)
    assert aggregate.L_att != pytest.approx((0.2 + 1.0 / 100.0) / 2.0)


def test_aggregate_recovery_loss_is_ratio_of_summed_values() -> None:
    first = evaluate_recovery_loss(
        cohort_id="R_A",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        fixed_cohort=("n1",),
        reference_actions={"n1": 5.0},
        comparator_actions={"n1": 0.0},
        reference_objectives={("n1", 5.0): 1.0, ("n1", 0.0): 1.5},
        reference_recoverable_values={"n1": 0.5},
    )
    second = evaluate_recovery_loss(
        cohort_id="R_B",
        reference_id="HISTORY_H16:JOINT",
        comparator_id="HISTORY_H16:POINT",
        fixed_cohort=("m1",),
        reference_actions={"m1": 5.0},
        comparator_actions={"m1": 5.0},
        reference_objectives={("m1", 5.0): 2.0},
        reference_recoverable_values={"m1": 1.5},
    )
    aggregate = aggregate_recovery_evaluations((first, second))
    assert aggregate.delta_recovery_objective == pytest.approx(0.5)
    assert aggregate.reference_recoverable_value == pytest.approx(2.0)
    assert aggregate.L_rec == pytest.approx(0.25)
    assert aggregate.A0 == pytest.approx(0.5)
    assert aggregate.A5 == pytest.approx(1.0)


def test_detailed_evaluation_models_have_no_total_loss() -> None:
    assert "L_total" not in AttentionEvaluation.model_fields
    assert "L_total" not in RecoveryEvaluation.model_fields
    assert "L_total" not in DecisionEvaluation.model_fields
