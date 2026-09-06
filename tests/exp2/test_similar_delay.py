import pandas as pd
import pytest

from exp.exp2.protocol import COMPONENTS
from exp.exp2.similar_delay import aggregate_episode_pairs, build_similar_delay_pairs


def _row(episode, node, stage, delay, rank, z):
    return {
        "episode_id": episode,
        "decision_node_id": node,
        "operational_stage": stage,
        "delay_to_mean": delay,
        "consequence_rank_pct": rank,
        **{f"Z_{component}": z for component in COMPONENTS},
    }


def test_pair_contract_boundaries_and_base_rank_inheritance():
    frame = pd.DataFrame(
        [
            _row("A", "a1", "PRE_IB", 10, 0.05, 1),
            _row("A", "a2", "PRE_IB", 12, 0.95, 2),
            _row("B", "b1", "PRE_IB", 15, 0.75, 4),
            _row("C", "c1", "PRE_IB", 15.001, 0.25, 8),
            _row("D", "d1", "POST_IB_PRE_OB", 10, 0.50, 3),
        ]
    )
    pairs = build_similar_delay_pairs(frame, caliper=5.0)
    assert not (
        (pairs["original_episode_a"] == "A") & (pairs["original_episode_b"] == "A")
    ).any()
    assert set(pairs["operational_stage"]) == {"PRE_IB"}
    ab = pairs.loc[
        (pairs["original_episode_a"] == "A") & (pairs["original_episode_b"] == "B")
    ]
    assert len(ab) == 2
    assert sorted(ab["abs_delay_gap"]) == [3.0, 5.0]
    a1b = ab.loc[ab["node_a"].eq("a1") | ab["node_b"].eq("a1")].iloc[0]
    assert a1b["abs_consequence_rank_gap"] == pytest.approx(0.70)
    assert not (
        (pairs["original_episode_a"] == "A")
        & (pairs["original_episode_b"] == "C")
        & (pairs["node_a"].eq("a1") | pairs["node_b"].eq("a1"))
    ).any()


def test_unordered_duplicate_removed_and_episode_pair_median_is_correct():
    frame = pd.DataFrame(
        [
            _row("A", "a1", "PRE_IB", 10, 0.1, 1),
            _row("A", "a2", "PRE_IB", 11, 0.3, 3),
            _row("B", "b1", "PRE_IB", 12, 0.9, 5),
        ]
    )
    pairs = build_similar_delay_pairs(frame, caliper=5)
    summary = aggregate_episode_pairs(pairs)
    assert len(summary) == 1
    assert summary.iloc[0]["qualifying_node_pair_count"] == 2
    assert summary.iloc[0]["abs_consequence_rank_gap"] == pytest.approx(0.7)
    assert summary.iloc[0]["abs_Z_F_continuity"] == pytest.approx(3.0)
