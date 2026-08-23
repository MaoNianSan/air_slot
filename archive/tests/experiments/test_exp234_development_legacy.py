"""Focused tests for the Exp2-Exp4 Development execution outputs.

Offline only: validates manifests, partition hashes, final-test guards, the
M4 material-coverage block, and the M2-layer self-consistency evidence.
"""

import json
from hashlib import sha256
from pathlib import Path

import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_exp2_manifest_contract_and_hash():
    manifest = _load("EXP2_DEVELOPMENT_V1.json")
    assert manifest["schema_version"] == "EXP2_DEVELOPMENT_V1"
    assert manifest["node_count"] == 1824
    assert manifest["formal_available_nodes"] == 1824
    assert manifest["reference_evaluator"] == (
        "ALIGNED_DISTRIBUTIONAL_FULL_FIXED_FORMAL_SCOPE_FULL_DECISION_CONTRACT"
    )
    assert manifest["corruption_q"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert manifest["fast_m2_path_equivalence"]["status"] == "PASS"
    assert manifest["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["PAPER_FULL_RUN"] is False
    assert "M4_MATERIAL_COVERAGE_UNFROZEN" in manifest["blocked_subcomponents"]
    assert manifest["authoritative_ranking_claim"]["status"] == "BLOCKED"
    assert _hash(ROOT / manifest["partition"]["path"]) == manifest["partition"]["hash"]


def test_exp2_q0_self_consistency_and_monotonicity():
    manifest = _load("EXP2_DEVELOPMENT_V1.json")
    q0 = manifest["aggregate"]["corrupted_q000"]
    assert q0["mean_action_gap_distortion"] == 0.0
    assert q0["mean_pairwise_ranking_reversal_rate"] == 0.0
    assert q0["mean_top1_disagreement"] == 0.0
    assert q0["mean_ranking_at_3_overlap"] == 1.0
    distortions = [
        manifest["aggregate"][f"corrupted_q{q:03d}"]["mean_action_gap_distortion"]
        for q in (0, 25, 50, 75, 100)
    ]
    assert distortions == sorted(distortions)
    point = manifest["aggregate"]["point_full"]
    assert point["mean_action_gap_distortion"] > distortions[-1]


def test_exp3_manifest_contract_and_m4_block():
    manifest = _load("EXP3_DEVELOPMENT_V1.json")
    assert manifest["schema_version"] == "EXP3_DEVELOPMENT_V1"
    audit = manifest["formal_feasibility_audit"]
    assert audit["candidate_cohort"] == 1824
    assert audit["numerically_evaluable_cohort"] == 1824
    assert audit["no_authoritative_decision_cohort"] == 1824
    assert manifest["m4_blocker"] == "M4_MATERIAL_COVERAGE_UNFROZEN"
    assert all(
        item["run"] == "NOT_RUN_M4_BLOCKED" for item in manifest["ablations"].values()
    )
    assert manifest["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["PAPER_FULL_RUN"] is False
    assert _hash(ROOT / manifest["partition"]["path"]) == manifest["partition"]["hash"]


def test_exp4_manifest_contract_and_m4_block():
    manifest = _load("EXP4_DEVELOPMENT_V1.json")
    assert manifest["schema_version"] == "EXP4_DEVELOPMENT_V1"
    assert manifest["node_count"] == 1824
    assert manifest["sensitivities"] == ["LOW", "BASE", "HIGH"]
    assert manifest["m4_ranking"]["status"] == "NOT_RUN"
    assert manifest["m4_ranking"]["blocker"] == "M4_MATERIAL_COVERAGE_UNFROZEN"
    assert manifest["deployability"]["status"] == "NOT_RUN"
    assert manifest["portability_hard_gates"]["DATA1_PORTABILITY_STATUS"] == "PASS"
    assert manifest["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["PAPER_FULL_RUN"] is False
    assert _hash(ROOT / manifest["partition"]["path"]) == manifest["partition"]["hash"]


def test_audit_cases_schema_and_strata():
    payload = _load("EXP234_LLM_AUDIT_CASES.json")
    audit = payload["audit"]
    cases = payload["cases"]
    assert audit["case_count"] == len(cases) == 1824
    assert sum(audit["strata_counts"].values()) == len(cases)
    for case in cases[:50]:
        assert set(case) >= {
            "case_id", "episode_id", "decision_node_id", "stratum", "decision_time",
            "operational_stage", "admissible_operational_state",
            "m2_consequence_profile", "recommended_action", "m4_lane", "m4_blocker",
        }
        assert case["m4_lane"] == "NOT_RUN"
        assert case["m4_blocker"] == "M4_MATERIAL_COVERAGE_UNFROZEN"
        assert case["stratum"] in {
            "formal_non_null_top1", "formal_a00_top1",
            "relaxed_only_invalidated_top1", "scenario_conditional_close_call",
        }
