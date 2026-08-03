from __future__ import annotations

import pandas as pd

from downstream_common import model_change_lineage
from ranking_contract import build_ranking_prefixes, full_ranking_from_scores
import pytest

from src.pipeline_analysis import (
    CandidateSetContractError,
    _ranking_decisions,
    validate_candidate_sets,
)


def test_overall_adv_ranking_1235_classification() -> None:
    scores = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A00", "action_family": "null", "score": 2.0, "expected_residual": 2.0, "channel_contribution_F": 1.0, "priority": 0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "score": 1.0, "expected_residual": 1.0, "channel_contribution_F": 2.0, "priority": 1},
    ])
    cohort = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    global_prefixes, _ = build_ranking_prefixes(
        cohort, full_ranking_from_scores(scores, "score")
    )
    global_full = full_ranking_from_scores(scores, "score")
    policies, comparison = _ranking_decisions(
        scores, global_full, global_prefixes, cohort
    )
    assert set(comparison["ranking_k"]) == {1, 2, 3, 5}
    assert comparison.loc[comparison["ranking_k"].eq(1), "set_disagreement"].iloc[0]
    assert policies.loc[policies["is_padding"], "action_id"].isna().all()


def test_global_local_candidate_mismatch_rejected() -> None:
    global_candidates = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11"},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A12"},
    ])
    local_candidates = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11"},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A13"},
    ])
    with pytest.raises(CandidateSetContractError) as caught:
        validate_candidate_sets(global_candidates, local_candidates)
    assert caught.value.details["mismatch_episode_count"] == 1
    assert caught.value.details["global_only_actions"][0]["action_id"] == "A12"
    assert caught.value.details["local_only_actions"][0]["action_id"] == "A13"
    assert (
        caught.value.details["candidate_source_hash_global"]
        != caught.value.details["candidate_source_hash_local"]
    )


def test_same_candidate_different_topk_set_classified() -> None:
    scores = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "score": 1.0, "expected_residual": 1.0, "channel_contribution_F": 3.0, "priority": 1},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A12", "action_family": "hold", "score": 2.0, "expected_residual": 2.0, "channel_contribution_F": 1.0, "priority": 2},
    ])
    cohort = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    global_full = full_ranking_from_scores(scores, "score")
    global_prefixes, _ = build_ranking_prefixes(cohort, global_full)
    _, comparison = _ranking_decisions(
        scores, global_full, global_prefixes, cohort
    )
    assert comparison.loc[
        comparison["ranking_k"].eq(1), "comparison_class"
    ].iloc[0] == "DIFFERENT_SET"


def test_lineage_tracks_M1_M3_M4_versions() -> None:
    lineage = model_change_lineage({
        "m1_feature_contract_version": "M1_PREVIOUS_LEG_V1",
        "m3_action_library_version": "M3_RESPONSE_V3_EXPANDED_PROVISIONAL",
        "m3_formal_action_count": 26,
        "ranking_contract_version": "M4_RANKING_1235_V1_PROVISIONAL",
        "ranking_depths": [1, 2, 3, 5],
    })
    assert lineage["m1_feature_contract_version"] == "M1_PREVIOUS_LEG_V1"
    assert lineage["m3_formal_action_count"] == 26
    assert lineage["ranking_depths"] == [1, 2, 3, 5]
