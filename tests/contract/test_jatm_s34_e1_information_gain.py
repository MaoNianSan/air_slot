from types import SimpleNamespace

from model.common.decision_contracts import PrioritySignal, SignalKind, TypedStatus
from model.common.enums import SupportState

from exp.jatm_s34.e1_information_gain import _clone_instance, _select, _summarize_stage


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


def _fake_node(node_id: str, *, episode_id: str = "episode", delay: float = 1.0, consequence: float = 1.0, included: bool = True):
    status = TypedStatus.SUPPORTED if included else TypedStatus.ABSTAIN_NO_COMMON_SUPPORT
    support = SimpleNamespace(
        included=included,
        supported_mass=1.0 if included else 0.0,
        threshold=0.9,
        status=status,
    )
    return SimpleNamespace(
        episode_id=episode_id,
        chain_id=f"chain-{episode_id}",
        node_id=node_id,
        delay_scores={"HISTORY_JOINT": delay if included else None},
        consequence_scores={"HISTORY_JOINT": consequence if included else None},
        stage=None,
        support=lambda _representation: support,
    )


def test_bootstrap_instance_ids_remain_distinct_when_an_episode_is_repeated():
    node = _fake_node("node")
    first = _clone_instance(node, replicate=3, occurrence=0)
    second = _clone_instance(node, replicate=3, occurrence=1)
    assert first.episode_id != second.episode_id
    assert first.chain_id != second.chain_id
    assert first.node_id != second.node_id
    factors = {node.node_id: (2.0, 1.0), first.node_id: (2.0, 1.0), second.node_id: (2.0, 1.0)}
    result = _summarize_stage((first, second), view="DELAY", q=0.3, factor_by_node=factors)
    assert result["n"] == 2
    assert result["k"] == 1


def test_e1_tie_break_and_sample_capacity_are_recomputed():
    comparator = [_signal("b", 1.0, SignalKind.DELAY), _signal("a", 1.0, SignalKind.DELAY)]
    consequence = [_signal("b", 2.0, SignalKind.CONSEQUENCE), _signal("a", 1.0, SignalKind.CONSEQUENCE)]
    result = _select(comparator, consequence, q=0.3)
    assert result["n"] == 2 and result["k"] == 1
    assert result["selected_view"] == ["a"]  # episode/node lexical tie-break


def test_e1_partial_abstain_and_zero_reference_denominator_are_typed():
    supported_delay = _signal("a", 1.0, SignalKind.DELAY)
    supported_consequence = _signal("a", 0.0, SignalKind.CONSEQUENCE)
    abstain_delay = PrioritySignal(
        signal_type=SignalKind.DELAY,
        episode_id="episode-b",
        chain_id="chain-b",
        node_id="b",
        representation_id="HISTORY_H16:JOINT",
        score=None,
        support=SupportState.ABSTAIN,
        status=TypedStatus.ABSTAIN_NO_COMMON_SUPPORT,
        comparison_support_mass=0.0,
        comparison_support_threshold=0.9,
        reason_codes=("MISSING_REFERENCE",),
    )
    abstain_consequence = abstain_delay.model_copy(update={"signal_type": SignalKind.CONSEQUENCE})
    result = _select([supported_delay, abstain_delay], [supported_consequence, abstain_consequence], q=0.3)
    assert result["n"] == 1 and result["abstain"] == 1
    assert result["abstain_reasons"] == {"MISSING_REFERENCE": 1}
    assert result["valid_reference_denominator"] is False
    assert result["retained_consequence"] is None
    assert result["attention_loss"] is None
