from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import SupportState

from exp.jatm_s34.e1_information_gain import _select


def _signal(node_id: str, score: float, kind: SignalKind) -> PrioritySignal:
    return PrioritySignal(
        signal_type=kind,
        episode_id=f"episode-{node_id}",
        chain_id=f"chain-{node_id}",
        node_id=node_id,
        representation_id="HISTORY_H16:JOINT",
        score=score,
        support=SupportState.SUPPORTED,
        status=TypedStatus.SUPPORTED,
        comparison_support_mass=1.0,
        comparison_support_threshold=0.9,
    )


def test_e1_selector_keeps_shared_queue_and_reports_replacement():
    comparator = [_signal("a", 3.0, SignalKind.DELAY), _signal("b", 1.0, SignalKind.DELAY)]
    consequence = [_signal("a", 1.0, SignalKind.CONSEQUENCE), _signal("b", 2.0, SignalKind.CONSEQUENCE)]
    result = _select(comparator, consequence, q=0.3)
    assert result["n"] == 2
    assert result["k"] == 1
    assert result["overlap"] == 0
    assert result["replacement"] == 1
    assert result["retained_consequence"] == 0.5
