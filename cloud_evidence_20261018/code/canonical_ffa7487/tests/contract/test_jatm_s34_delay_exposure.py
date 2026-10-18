from model.M2.contracts import ScientificContextValue, SourceType
from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import EvidenceClass, SupportState
from model.PRE import ConstructionType
from exp.jatm_s34.delay_exposure import (
    DOWNSTREAM_EXPOSURE_FORMULA,
    PASSENGER_TIME_FORMULA,
    build_delay_exposure_scores,
)


def _signal() -> PrioritySignal:
    return PrioritySignal(
        signal_type=SignalKind.DELAY,
        episode_id="episode-1",
        chain_id="chain-1",
        node_id="node-1",
        representation_id="HISTORY_H8:JOINT",
        score=12.0,
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=0.95,
        comparison_support_threshold=0.90,
    )


def _reference(object_id: str, value: float, unit: str) -> ScientificContextValue:
    return ScientificContextValue(
        object_id=object_id,
        value=value,
        unit=unit,
        support_state=SupportState.SUPPORTED,
        evidence_class=EvidenceClass.DERIVED,
        construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
        reference_period="2019-H1",
        freeze_id=f"freeze-{object_id}",
        source_type=SourceType.DATA,
        reference_source=f"artifact-{object_id}",
    )


def test_approved_delay_exposure_views_are_separate_and_lineaged():
    passenger, downstream = build_delay_exposure_scores(
        _signal(),
        expected_passengers_per_flight=_reference("pax", 100.0, "passengers_per_flight"),
        expected_downstream_exposure=_reference("downstream", 2.0, "legs"),
    )
    assert passenger.formula == PASSENGER_TIME_FORMULA
    assert passenger.score == 1200.0
    assert passenger.unit == "passenger_minutes_proxy"
    assert downstream.formula == DOWNSTREAM_EXPOSURE_FORMULA
    assert downstream.score == 24.0
    assert downstream.unit == "exposure_minutes_proxy"
    assert passenger.status is TypedStatus.SUPPORTED
    assert passenger.reference_lineage
    assert downstream.reference_lineage


def test_abstained_reference_does_not_zero_fill():
    reference = _reference("pax", 100.0, "passengers_per_flight").model_copy(
        update={
            "value": None,
            "support_state": SupportState.ABSTAIN,
            "reason_code": "NO_COMMON_SUPPORT",
        }
    )
    passenger, downstream = build_delay_exposure_scores(
        _signal(),
        expected_passengers_per_flight=reference,
        expected_downstream_exposure=_reference("downstream", 2.0, "legs"),
    )
    assert passenger.score is None
    assert passenger.status is TypedStatus.ABSTAIN_NO_EVIDENCE
    assert downstream.score == 24.0
