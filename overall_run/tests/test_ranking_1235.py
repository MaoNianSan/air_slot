from __future__ import annotations

import pandas as pd

from src.ranking_contract import (
    RANKING_DEPTHS,
    build_ranking_prefixes,
    compare_ranking_prefixes,
    full_ranking_from_scores,
    real_ranking_rows,
)


def _scores() -> pd.DataFrame:
    return pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A00", "action_family": "null", "value": 5.0, "priority": 0, "expected_residual": 5.0, "cvar_component": 6.0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "value": 4.0, "priority": 1, "expected_residual": 4.0, "cvar_component": 5.0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A21", "action_family": "retime", "value": 4.0, "priority": 2, "expected_residual": 4.0, "cvar_component": 5.0},
    ])


def _universe() -> pd.DataFrame:
    return _scores()[["episode_id", "snapshot_id"]].drop_duplicates()


def test_ranking_depths_are_1_2_3_5_and_prefixes_of_one_sort() -> None:
    full = full_ranking_from_scores(_scores(), "value")
    all_k, views = build_ranking_prefixes(_universe(), full)
    assert tuple(views) == RANKING_DEPTHS
    assert views[1].loc[0, "action_id"] == "A11"
    longest = views[5].dropna(subset=["action_id"])["action_id"].tolist()
    for depth in RANKING_DEPTHS:
        real = views[depth].dropna(subset=["action_id"])["action_id"].tolist()
        assert real == longest[: min(depth, len(longest))]
    assert len(all_k) == sum(RANKING_DEPTHS)


def test_fixed_width_A00_uniqueness_and_null_padding() -> None:
    all_k, views = build_ranking_prefixes(
        _universe(), full_ranking_from_scores(_scores(), "value")
    )
    for depth, view in views.items():
        assert len(view) == depth
        assert view["action_id"].eq("A00").sum() <= 1
        padding = view[view["is_padding"]]
        assert padding["action_id"].isna().all()
        assert padding[["score", "expected_residual", "cvar_residual"]].isna().all().all()
    assert real_ranking_rows(all_k)["action_id"].notna().all()


def test_padding_excluded_from_comparison_metrics_and_k1_matches_legacy() -> None:
    full = full_ranking_from_scores(_scores(), "value")
    global_k, views = build_ranking_prefixes(_universe(), full)
    local_scores = _scores().assign(value=[5.0, 4.5, 4.0])
    local_k, _ = build_ranking_prefixes(
        _universe(), full_ranking_from_scores(local_scores, "value")
    )
    comparison = compare_ranking_prefixes(global_k, local_k)
    assert views[1].loc[0, "action_id"] == full.sort_values("rank").iloc[0]["action_id"]
    assert set(comparison["ranking_k"]) == set(RANKING_DEPTHS)
    assert comparison["overlap_rate"].between(0, 1).all()
    assert comparison.loc[comparison["ranking_k"].eq(5), "padding_count_global"].iloc[0] == 2
    assert comparison.loc[comparison["ranking_k"].eq(5), "overlap_rate"].iloc[0] == 1.0


def test_same_set_different_order_and_different_set() -> None:
    global_k, _ = build_ranking_prefixes(
        _universe(), full_ranking_from_scores(_scores(), "value")
    )
    reordered = _scores().assign(value=[5.0, 4.0, 3.0])
    local_k, _ = build_ranking_prefixes(
        _universe(), full_ranking_from_scores(reordered, "value")
    )
    comparison = compare_ranking_prefixes(global_k, local_k).set_index("ranking_k")
    assert comparison.loc[3, "comparison_class"] == "SAME_SET_DIFFERENT_ORDER"

    different = _scores().copy()
    different.loc[different["action_id"].eq("A21"), "action_id"] = "A31"
    different.loc[different["action_family"].eq("retime"), "action_family"] = "passenger"
    local_k, _ = build_ranking_prefixes(
        _universe(), full_ranking_from_scores(different, "value")
    )
    comparison = compare_ranking_prefixes(global_k, local_k).set_index("ranking_k")
    assert comparison.loc[3, "comparison_class"] == "DIFFERENT_SET"


def test_stable_tie_break() -> None:
    scores = _scores().sample(frac=1.0, random_state=17).reset_index(drop=True)
    first = full_ranking_from_scores(scores, "value")["action_id"].tolist()
    second = full_ranking_from_scores(
        scores.sample(frac=1.0, random_state=23).reset_index(drop=True), "value"
    )["action_id"].tolist()
    assert first == second == ["A11", "A21", "A00"]


def test_expected_residual_is_second_tie_break() -> None:
    scores = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "value": 1.0, "expected_residual": 4.0, "priority": 1, "expected_implementation_cost_rmb": 1.0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A12", "action_family": "hold", "value": 1.0, "expected_residual": 3.0, "priority": 2, "expected_implementation_cost_rmb": 99.0},
    ])
    ranked = full_ranking_from_scores(scores, "value")
    assert ranked["action_id"].tolist() == ["A12", "A11"]


def test_zero_candidate_episode_has_fixed_width_padding() -> None:
    universe = pd.DataFrame([{"episode_id": "e0", "snapshot_id": "s0"}])
    all_k, views = build_ranking_prefixes(universe, pd.DataFrame())
    assert len(all_k) == sum(RANKING_DEPTHS)
    assert all_k["is_padding"].all()
    assert all_k["action_id"].isna().all()
    assert all_k[["score", "expected_residual", "cvar_residual"]].isna().all().all()
    assert all_k["rank_status"].eq("UNAVAILABLE").all()
    assert views[1].loc[0, "effective_action_count"] == 0
