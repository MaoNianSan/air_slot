"""M3/M4 comparison-ranking materialization contract tests (V3 T4, 2026-08-26).

Fast synthetic tests only: no parquet reads, no model inference.  Covers the
frozen selection semantics (min J, tie-break action_id, A00 in the comparison
set, J-available actions only), the F7/F8 abstain rules carried from registry
v2, and the DEVELOPMENT_ONLY manifest contract (safety all zero,
paper_result=false, FINAL_TEST_ACCESS_COUNT=0).
"""

from __future__ import annotations

import json

import pandas as pd

from exp.exp3.m3_m4_ranking_records import (
    BAND_SCALE_FACTOR,
    SAFETY,
    aggregate_stats,
    materialize_records,
    recompute_rank,
    top1_summary,
)


def _row(
    action_id: str,
    j: float | None,
    node: str = "n1",
    band: str = "BASE",
    frozen_rank: int | None = None,
) -> dict:
    return {
        "episode_id": "ep1",
        "decision_node_id": node,
        "action_id": action_id,
        "action_family": None,
        "response_sensitivity": band,
        "eligibility_state": "TRUE",
        "response_support": "IDENTITY" if action_id == "A00" else "SCENARIO_ASSUMPTION",
        "diagnostic_support_status": "PARTIAL_DIAGNOSTIC" if j is not None else "NOT_RUN",
        "conditional_expected_constructed_eur": 10.0 if j is not None else None,
        "conditional_constructed_eur_cvar_alpha": 20.0 if j is not None else None,
        "conditional_residual_risk": j,
        "conditional_diagnostic_rank": frozen_rank,
        "p_itinerary_event_count": 0.0,
        "p_service_event_count": 0.0,
        "pending_monetary_event_status": "EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED",
        "ranking_authority": "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
        "monetary_ground_truth_claim": False,
        "causal_action_effect_claim": False,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_recompute_rank_min_j_tie_action_id():
    rows = [
        {"action_id": "A00", "residual_risk_objective": 40.0},
        {"action_id": "B01", "residual_risk_objective": 30.0},
        {"action_id": "C02", "residual_risk_objective": 30.0},
        {"action_id": "D03", "residual_risk_objective": None},
    ]
    ranks = recompute_rank(rows)
    assert ranks == {"A00": 3, "B01": 1, "C02": 2}
    tie = [
        {"action_id": "Z99", "residual_risk_objective": 25.0},
        {"action_id": "A01", "residual_risk_objective": 25.0},
        {"action_id": "A00", "residual_risk_objective": 40.0},
    ]
    assert recompute_rank(tie) == {"Z99": 2, "A01": 1, "A00": 3}


def test_recompute_rank_excludes_not_run():
    rows = [
        {"action_id": "A00", "residual_risk_objective": None},
        {"action_id": "B01", "residual_risk_objective": 12.0},
    ]
    ranks = recompute_rank(rows)
    assert ranks == {"B01": 1}
    assert "A00" not in ranks


def test_materialize_records_derives_rank_and_top1():
    source = _frame(
        [
            _row("A00", 40.0, frozen_rank=2),
            _row("B01", 30.0, frozen_rank=1),
            _row("C02", None),
            _row("A00", 41.0, node="n2", frozen_rank=3),
            _row("B01", 35.0, node="n2", frozen_rank=2),
            _row("C02", 20.0, node="n2", frozen_rank=1),
        ]
    )
    records = materialize_records(source)
    assert len(records) == 6
    by = records.set_index(["decision_node_id", "action_id"])
    assert by.loc[("n1", "B01"), "rank_position"] == 1
    assert bool(by.loc[("n1", "B01"), "top1"]) is True
    assert pd.isna(by.loc[("n1", "C02"), "rank_position"])
    assert pd.isna(by.loc[("n1", "C02"), "top1"])
    assert by.loc[("n2", "C02"), "rank_position"] == 1
    assert bool(by.loc[("n2", "C02"), "top1"]) is True
    assert by.loc[("n2", "A00"), "rank_position"] == 3


def test_materialize_records_keeps_support_and_discipline_fields():
    source = _frame(
        [
            _row("A00", 10.0, frozen_rank=2),
            _row("B01", 8.0, frozen_rank=1),
        ]
    )
    records = materialize_records(source)
    row = records[records["action_id"] == "A00"].iloc[0]
    assert row["response_support"] == "IDENTITY"
    assert row["pending_monetary_event_status"] == "EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED"
    assert row["ranking_authority"] == "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL"
    assert bool(row["monetary_ground_truth_claim"]) is False
    assert bool(row["causal_action_effect_claim"]) is False
    assert row["band"] == "BASE"
    assert row["band_scale_factor"] == 1.0


def test_top1_summary_and_aggregate_stats():
    source = _frame(
        [
            _row("A00", 40.0, frozen_rank=2),
            _row("B01", 30.0, frozen_rank=1),
            _row("C02", None),
            _row("A00", 10.0, node="n2", frozen_rank=1),
            _row("B01", 12.0, node="n2", frozen_rank=2),
        ]
    )
    records = materialize_records(source)
    summary = top1_summary(records)
    assert len(summary) == 2
    assert set(summary["top1_action_id"]) == {"B01", "A00"}
    stats = aggregate_stats(records, summary)
    assert stats["node_count"] == 2
    assert stats["ranked_nodes"] == 2
    assert stats["unranked_nodes"] == 0
    assert stats["top1_by_band"]["BASE"]["top1_a00_share"] == 0.5


def test_band_scale_factors_match_registry_v2():
    from pathlib import Path

    registry = json.loads(
        Path("registries/m4_eur_mapping_assumption_grounded_v2.json").read_text(encoding="utf-8")
    )
    first_bands = registry["ops_components"][0]["bands"]
    for band in first_bands:
        assert BAND_SCALE_FACTOR[band["band_id"]] == band["scale_factor"]
    components = {c["component_id"]: c for c in registry["ops_components"]}
    assert (
        components["P_itinerary"]["anchor_status"]
        == "ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY"
    )
    assert (
        components["P_service"]["anchor_status"]
        == "ABSTAIN_MONETARY_NOT_ANCHORED_EVENT_COUNTS_ONLY"
    )
    assert registry["rmb_reporting_system"] == "NOT_INSTANTIATED_NO_BETA_K_RMB"


def test_safety_contract():
    assert SAFETY["FINAL_TEST_ACCESS_COUNT"] == 0
    assert SAFETY["PAPER_FULL_RUN"] is False
    assert SAFETY["EXPERIMENT_RERUNS"] == 0
