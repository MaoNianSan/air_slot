"""PRE decision-environment boundary tests (Phase 1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from model.PRE.decision_environment import (
    ACTIONABLE_STAGES,
    NON_ACTIONABLE_STAGES,
    CanonicalNodeChoice,
    action_stage_class,
    assert_split_isolation,
    build_decision_evidence,
    choose_canonical_node,
    evidence_support,
    is_actionable,
    validate_no_future_evidence,
)
from model.common.decision_contracts import (
    DecisionEvidence,
    EvidenceItem,
    SplitName,
    StaticReference,
)
from model.common.enums import (
    DecisionTimeRole,
    EvidenceClass,
    OperationalStage,
    SupportState,
)
from model.common.errors import ContractError


T0 = datetime(2019, 3, 1, 12, 0, tzinfo=timezone.utc)
_UNSET = object()


def _item(
    record_id: str = "record-1",
    *,
    role: DecisionTimeRole = DecisionTimeRole.INFERENCE_EVIDENCE,
    offset_minutes: float = 0.0,
    support: SupportState = SupportState.SUPPORTED,
    evidence_class: EvidenceClass = EvidenceClass.DIRECT,
    availability_time=_UNSET,
) -> EvidenceItem:
    if availability_time is _UNSET:
        availability_time = T0 + timedelta(minutes=offset_minutes)
    return EvidenceItem(
        record_id=record_id,
        chain_id="chain-1",
        node_id="node-1",
        scientific_object="T_IB_REMAINING",
        availability_time=availability_time,
        decision_time_role=role,
        evidence_class=evidence_class,
        support=support,
    )


def test_no_future_evidence_rejects_late_inference_evidence():
    validate_no_future_evidence(
        decision_time=T0,
        items=(_item("ok", offset_minutes=0.0),),
    )
    with pytest.raises(ContractError) as error:
        validate_no_future_evidence(
            decision_time=T0,
            items=(_item("late", offset_minutes=5.0),),
        )
    assert "PRE_FUTURE_EVIDENCE:late" in str(error.value)


def test_factual_replay_evidence_is_retrospective_only():
    validate_no_future_evidence(
        decision_time=T0,
        items=(
            _item(
                "replay-known",
                role=DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE,
                offset_minutes=0.0,
            ),
        ),
    )
    with pytest.raises(ContractError) as error:
        validate_no_future_evidence(
            decision_time=T0,
            items=(
                _item(
                    "replay-early",
                    role=DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE,
                    offset_minutes=30.0,
                ),
            ),
        )
    assert "PRE_FUTURE_FACTUAL_EVIDENCE:replay-early" in str(error.value)


def test_inference_evidence_requires_availability_and_aware_timestamps():
    with pytest.raises(ContractError) as error:
        validate_no_future_evidence(
            decision_time=T0,
            items=(_item("no-availability", availability_time=None),),
        )
    assert "PRE_EVIDENCE_WITHOUT_AVAILABILITY:no-availability" in str(error.value)

    with pytest.raises(ContractError) as error:
        validate_no_future_evidence(
            decision_time=T0,
            items=(_item("naive", availability_time=datetime(2019, 3, 1, 12, 0)),),
        )
    assert "PRE_NAIVE_TIMESTAMP" in str(error.value)


def test_information_cutoff_may_not_exceed_decision_time():
    with pytest.raises(ContractError) as error:
        validate_no_future_evidence(
            decision_time=T0,
            items=(),
            information_cutoff=T0 + timedelta(minutes=15),
        )
    assert "PRE_INFORMATION_CUTOFF_AFTER_DECISION_TIME" in str(error.value)


def test_canonical_node_is_chosen_before_support_is_evaluated():
    choice = choose_canonical_node(
        (
            CanonicalNodeChoice(
                node_id="node-late-supported",
                stage=OperationalStage.POST_IB_PRE_OB,
                decision_time=T0 + timedelta(minutes=20),
                supported=True,
            ),
            CanonicalNodeChoice(
                node_id="node-canonical-unsupported",
                stage=OperationalStage.POST_IB_PRE_OB,
                decision_time=T0,
                supported=False,
                reason_codes=("PRE_EVIDENCE_ABSTAIN",),
            ),
        )
    )
    assert choice.node_id == "node-canonical-unsupported"
    assert choice.supported is False

    tie = choose_canonical_node(
        (
            CanonicalNodeChoice(
                node_id="node-b",
                stage=OperationalStage.PRE_IB,
                decision_time=T0,
                supported=True,
            ),
            CanonicalNodeChoice(
                node_id="node-a",
                stage=OperationalStage.PRE_IB,
                decision_time=T0,
                supported=True,
            ),
        )
    )
    assert tie.node_id == "node-a"

    with pytest.raises(ContractError) as error:
        choose_canonical_node(())
    assert "PRE_NO_CANONICAL_NODE_FOR_STAGE" in str(error.value)


@pytest.mark.parametrize("boundary", (SplitName.DEVELOPMENT, SplitName.TEST))
def test_split_isolation_blocks_the_other_partition(boundary):
    other = "test" if boundary is SplitName.DEVELOPMENT else "development"
    assert_split_isolation(
        split=boundary,
        referenced_splits=("train", "calibration", boundary.value),
    )
    with pytest.raises(ContractError) as error:
        assert_split_isolation(split=boundary, referenced_splits=(other,))
    assert "PRE_SPLIT_ISOLATION_VIOLATION" in str(error.value)


def test_evidence_support_uses_inference_evidence_only():
    assert evidence_support(()) is SupportState.ABSTAIN
    assert (
        evidence_support((_item("outcome", role=DecisionTimeRole.EVAL_OUTCOME),))
        is SupportState.ABSTAIN
    )
    assert (
        evidence_support(
            (
                _item("d1", support=SupportState.SUPPORTED),
                _item("d2", support=SupportState.DEGRADED),
            )
        )
        is SupportState.DEGRADED
    )
    assert (
        evidence_support(
            (
                _item("d1", support=SupportState.SUPPORTED),
                _item("d2", support=SupportState.ABSTAIN),
            )
        )
        is SupportState.ABSTAIN
    )
    assert (
        evidence_support((_item("d1", support=SupportState.SUPPORTED),))
        is SupportState.SUPPORTED
    )


def test_stage_actionability_rule_is_canonical():
    assert is_actionable(OperationalStage.PRE_IB) is True
    assert is_actionable(OperationalStage.POST_IB_PRE_OB) is True
    assert is_actionable(OperationalStage.POST_OB_PRE_TO) is False
    assert is_actionable(OperationalStage.COMPLETED) is False
    assert action_stage_class(OperationalStage.PRE_IB) == "PRE"
    assert action_stage_class(OperationalStage.POST_IB_PRE_OB) == "TURN"
    assert action_stage_class(OperationalStage.POST_OB_PRE_TO) == "TAXI"
    assert action_stage_class(OperationalStage.COMPLETED) == "COMP"
    assert set(ACTIONABLE_STAGES).isdisjoint(NON_ACTIONABLE_STAGES)


def test_decision_evidence_carries_evidence_support_only():
    envelope = build_decision_evidence(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        decision_time=T0,
        information_cutoff=T0,
        stage=OperationalStage.POST_IB_PRE_OB,
        split=SplitName.DEVELOPMENT,
        dynamic_evidence=(_item("d1"),),
        scheduled_milestones=("IN_BLOCK", "OFF_BLOCK"),
        observed_milestones=("IN_BLOCK", "OFF_BLOCK"),
        static_references=(
            StaticReference(
                reference_id="SCHEDULE-REF",
                source_id="BTS_SCHEDULE",
                reference_version="2019-H1",
            ),
        ),
    )
    assert envelope.support is SupportState.SUPPORTED
    assert envelope.availability is SupportState.SUPPORTED
    assert envelope.missing_milestones == ()
    assert envelope.split is SplitName.DEVELOPMENT
    assert envelope.evidence_support is envelope.support
    assert "comparison_support_mass" not in DecisionEvidence.model_fields
    assert "m_cs" not in DecisionEvidence.model_fields


@pytest.mark.parametrize(
    "ceiling,expected_reasons",
    (
        (EvidenceClass.DIRECT, ()),
        (EvidenceClass.UNSUPPORTED, ("PRE_EVIDENCE_CEILING_EXCEEDED:d1",)),
    ),
)
def test_envelope_records_ceiling_and_milestone_gaps(ceiling, expected_reasons):
    envelope = build_decision_evidence(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        decision_time=T0,
        information_cutoff=T0,
        stage=OperationalStage.PRE_IB,
        split=SplitName.TRAIN,
        dynamic_evidence=(_item("d1"),),
        scheduled_milestones=("IN_BLOCK", "OFF_BLOCK"),
        observed_milestones=("IN_BLOCK",),
        support_ceiling=ceiling,
    )
    assert envelope.reason_codes == expected_reasons
    assert envelope.missing_milestones == ("OFF_BLOCK",)


def test_envelope_is_not_supported_without_inference_evidence():
    envelope = build_decision_evidence(
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        decision_time=T0,
        information_cutoff=T0,
        stage=OperationalStage.COMPLETED,
        split=SplitName.CALIBRATION,
        dynamic_evidence=(
            _item("replay", role=DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE),
            _item("outcome", role=DecisionTimeRole.EVAL_OUTCOME, offset_minutes=240.0),
        ),
    )
    assert envelope.support is SupportState.ABSTAIN
    assert envelope.availability is SupportState.SUPPORTED
    assert envelope.inference_record_count == 0
    assert envelope.reason_codes == ("PRE_NO_SUPPORTED_INFERENCE_EVIDENCE",)


def test_envelope_rejects_evidence_from_another_chain():
    foreign = EvidenceItem(
        record_id="foreign",
        chain_id="chain-2",
        node_id="node-1",
        scientific_object="T_IB_REMAINING",
        availability_time=T0,
        decision_time_role=DecisionTimeRole.INFERENCE_EVIDENCE,
        evidence_class=EvidenceClass.DIRECT,
        support=SupportState.SUPPORTED,
    )
    with pytest.raises(ValidationError) as error:
        build_decision_evidence(
            episode_id="episode-1",
            chain_id="chain-1",
            node_id="node-1",
            decision_time=T0,
            information_cutoff=T0,
            stage=OperationalStage.PRE_IB,
            split=SplitName.DEVELOPMENT,
            dynamic_evidence=(foreign,),
        )
    assert "DECISION_EVIDENCE_ITEM_IDENTITY_MISMATCH" in str(error.value)
