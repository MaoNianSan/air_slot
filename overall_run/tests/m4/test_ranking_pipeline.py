from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from src.m4 import run_m4_synthetic_integration, write_formal_artifact
from src.m4.contracts import DecisionLane, M4ContractError
from src.m4.ranking import build_authoritative_ranking
from src.ranking_contract import RANKING_DEPTHS, real_ranking_rows


def _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides, stage="t1"):
    bundle, losses = m4_input_factory()
    return run_m4_synthetic_integration(
        bundle,
        losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping={"TURNAROUND": stage},
        opportunity_overrides=opportunity_overrides,
    )


def test_one_authoritative_sort(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    longest = artifact.ranking_views[5].dropna(subset=["action_id"])["action_id"].tolist()
    for depth in RANKING_DEPTHS:
        current = artifact.ranking_views[depth].dropna(subset=["action_id"])["action_id"].tolist()
        assert current == longest[: min(depth, len(longest))]


def test_ranking_depths_1_2_3_5(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    assert tuple(artifact.ranking_views) == RANKING_DEPTHS
    assert [len(artifact.ranking_views[depth]) for depth in RANKING_DEPTHS] == [1, 2, 3, 5]


def test_prefix_consistency(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    assert len(artifact.ranking_prefix_frame) == sum(RANKING_DEPTHS)


def test_A00_unique(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    for view in artifact.ranking_views.values():
        assert view["action_id"].eq("A00").sum() <= 1


def test_null_padding(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides, stage="t3"
    )
    padding = artifact.ranking_views[5][artifact.ranking_views[5]["is_padding"]]
    assert padding["action_id"].isna().all()
    assert padding[["score", "expected_residual", "cvar_residual"]].isna().all().all()


def test_padding_excluded_from_metrics(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides, stage="t3"
    )
    real = real_ranking_rows(artifact.ranking_prefix_frame)
    assert real["action_id"].notna().all()
    assert not real["is_padding"].any()


def test_conditional_not_used_to_fill_formal(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    lanes = artifact.action_frame.set_index("action_id")["decision_lane"]
    ranked = set(real_ranking_rows(artifact.ranking_prefix_frame)["action_id"].astype(str))
    conditional = set(lanes[lanes.eq("CONDITIONAL")].index.astype(str))
    assert ranked.isdisjoint(conditional)


def test_scenario_not_used_to_fill_formal(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    lanes = artifact.action_frame.set_index("action_id")["decision_lane"]
    ranked = set(real_ranking_rows(artifact.ranking_prefix_frame)["action_id"].astype(str))
    scenario = set(lanes[lanes.eq("SCENARIO")].index.astype(str))
    assert ranked.isdisjoint(scenario)


def test_stable_tie_break(cfg, m4_input_factory, m3_artifact, opportunity_overrides) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    items = []
    for item in artifact.action_evaluations:
        lane = DecisionLane.FORMAL if item.action_id in {"A12", "A22"} else DecisionLane.CONDITIONAL
        tied = replace(
            item,
            decision_lane=lane,
            risk_score=1.0,
            expected_total_post_loss_rmb=2.0,
            cvar90_post_loss_rmb=3.0,
            expected_implementation_cost_rmb=4.0,
        )
        items.append(tied)
    full, _, _ = build_authoritative_ranking(tuple(reversed(items)))
    assert full["action_id"].tolist() == ["A12", "A22"]


def test_zero_formal_candidate_fixed_width_output(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    no_formal = tuple(
        replace(item, decision_lane=DecisionLane.CONDITIONAL)
        for item in artifact.action_evaluations
    )
    full, prefixes, views = build_authoritative_ranking(no_formal)
    assert full.empty
    assert prefixes["is_padding"].all()
    assert all(len(views[depth]) == depth for depth in RANKING_DEPTHS)


def test_synthetic_integration_has_21_actions_and_four_lanes(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(
        cfg, m4_input_factory, m3_artifact, opportunity_overrides, stage="t3"
    )
    assert len(artifact.action_frame) == 21
    assert set(artifact.action_frame["decision_lane"]) == {
        "FORMAL", "CONDITIONAL", "SCENARIO", "EXCLUDED"
    }
    assert artifact.episode_frame.iloc[0]["result_status"] == "TEST_ONLY_VALID"
    assert artifact.test_only and not artifact.publication_allowed


def test_synthetic_output_cannot_be_written_formally(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    with pytest.raises(M4ContractError, match="FORMAL_OUTPUT_FORBIDDEN"):
        write_formal_artifact(artifact, tmp_path / "output" / "m4")
    assert not (tmp_path / "output" / "m4" / "m4_manifest.json").exists()


def test_action_and_episode_output_schema(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    assert {
        "decision_lane", "reason_codes", "risk_score", "expected_total_post_loss_rmb",
        "cvar90_post_loss_rmb", "net_benefit_probability_vs_a00",
    }.issubset(artifact.action_frame.columns)
    assert {
        "result_status", "publication_allowed", "ranking_at_1", "ranking_at_5",
        "top1_action_id", "a00_rank",
    }.issubset(artifact.episode_frame.columns)
