"""Focused tests for M1_SIGNED_DEVELOPMENT_SCENARIOS_V1 (Exp2-Exp4 scenario source).

Offline only: reads the generated artifact + manifest on disk, validates the
immutable contract, stage semantics, point-collapse behavior, RNG keys, and
the Final Test hard wall.  Does not rebuild anything.
"""

import json
from hashlib import sha256
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from model.M1.scenarios import _uniform

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
ARTIFACT_DIR = OUT / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
MANIFEST_PATH = OUT / "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1_MANIFEST.json"


def _hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_contract_and_final_test_wall():
    manifest = _manifest()
    assert manifest["schema_version"] == "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
    assert manifest["artifact_id"] == "M1_SIGNED_DEVELOPMENT_SCENARIOS_V1"
    assert manifest["decision_id"] == "AIR_SLOT_EXP234_SCENARIO_ARTIFACT_AND_LLM_EXECUTION"
    assert manifest["classification"] == "DERIVED_DOWNSTREAM_ARTIFACT_GENERATION"
    assert manifest["target_contract"] == ["R_IB", "DELTA_OB", "T_TX"]
    assert manifest["derived_values"] == ["R_OB", "T_OB", "T_TO", "D_TO"]
    assert manifest["H"] == 32
    assert manifest["W"] == 30
    assert manifest["history_representation"] == "FIXED_HISTORY"
    assert manifest["scenario_count"] == 250
    assert manifest["scenario_count_provenance"]["selected"] == 250
    assert manifest["episode_count"] == 128
    assert manifest["node_count"] == 1824
    assert manifest["split"] == "DEVELOPMENT"
    assert manifest["cross_split_count"] == 0
    assert manifest["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["PAPER_FULL_RUN"] is False
    assert manifest["artifact_hash"].startswith("sha256:")


def test_partition_hashes_and_row_counts():
    manifest = _manifest()
    node = pq.read_table(ARTIFACT_DIR / "node.parquet").to_pydict()
    scenario = pq.read_table(ARTIFACT_DIR / "scenario.parquet").to_pydict()
    assert len(node["episode_id"]) == 1824
    assert len(scenario["episode_id"]) == 1824 * 250
    assert _hash(ARTIFACT_DIR / "node.parquet") == manifest["partitions"][0]["hash"]
    assert _hash(ARTIFACT_DIR / "scenario.parquet") == manifest["partitions"][1]["hash"]
    assert len(set(node["episode_id"])) == 128
    assert len(set(scenario["episode_id"])) == 128


def test_stage_pattern_and_observed_semantics():
    node = pq.read_table(ARTIFACT_DIR / "node.parquet").to_pydict()
    stages = {}
    for stage, active_r_ib, active_delta, active_tx in zip(
        node["operational_stage"], node["active_r_ib"],
        node["active_delta_ob"], node["active_t_tx"],
    ):
        stages[stage] = stages.get(stage, 0) + 1
        if stage == "PRE_IB":
            assert active_r_ib and active_delta and active_tx
        elif stage == "POST_IB_PRE_OB":
            assert not active_r_ib and active_delta and active_tx
        elif stage == "POST_OB_PRE_TO":
            assert not active_r_ib and not active_delta and active_tx
        else:
            raise AssertionError(f"unexpected stage {stage}")
    assert stages == {"PRE_IB": 269, "POST_IB_PRE_OB": 1502, "POST_OB_PRE_TO": 53}
    for row in zip(node["operational_stage"], node["observed_r_ib"],
                   node["observed_delta_ob"], node["observed_t_tx"]):
        stage, r_ib, delta, tx = row
        if stage == "PRE_IB":
            assert r_ib is None and delta is None and tx is None
        elif stage == "POST_IB_PRE_OB":
            assert r_ib == 0.0 and delta is None and tx is None
        elif stage == "POST_OB_PRE_TO":
            assert r_ib == 0.0 and delta is not None and tx is None


def test_recovery_and_support_counts():
    manifest = _manifest()
    recovery = manifest["observed_recovery"]
    assert recovery["unobserved"] == 3864
    assert recovery["exact_verified"] == 1608
    assert recovery["realized_label_verified"] == 3864
    assert recovery["realized_label_mismatch"] == 0
    support = manifest["support_counts"]["target_support"]
    for target in ("R_IB", "DELTA_OB", "T_TX"):
        assert support[target] == {"SUPPORTED": 1824, "ABSTAIN": 0}
    assert manifest["abstain_counts"] == {
        "taxi_reference_nodes": 0, "schedule_missing_nodes": 0,
        "d_to_unavailable_scenarios": 0,
    }


def test_point_collapse_and_scenario_draw_semantics():
    node = pq.read_table(ARTIFACT_DIR / "node.parquet").to_pydict()
    scenario = pq.read_table(ARTIFACT_DIR / "scenario.parquet").to_pydict()
    by_node = {}
    for index, node_id in enumerate(scenario["decision_node_id"]):
        by_node.setdefault(node_id, []).append(index)
    node_by_id = {value: index for index, value in enumerate(node["decision_node_id"])}
    assert len(by_node) == 1824
    for node_id, positions in by_node.items():
        assert len(positions) == 250
        row = node_by_id[node_id]
        stage = node["operational_stage"][row]
        observed = {
            "R_IB": node["observed_r_ib"][row],
            "DELTA_OB": node["observed_delta_ob"][row],
            "T_TX": node["observed_t_tx"][row],
        }
        for position in positions:
            if stage == "PRE_IB":
                assert scenario["r_ib_minutes"][position] is not None
                assert scenario["delta_ob_minutes"][position] is not None
                assert scenario["t_tx_minutes"][position] is not None
            elif stage == "POST_IB_PRE_OB":
                assert scenario["r_ib_minutes"][position] == 0.0
                assert scenario["delta_ob_minutes"][position] is not None
                assert scenario["t_tx_minutes"][position] is not None
            elif stage == "POST_OB_PRE_TO":
                assert scenario["r_ib_minutes"][position] == 0.0
                assert scenario["delta_ob_minutes"][position] == observed["DELTA_OB"]
                assert scenario["t_tx_minutes"][position] is not None
            for target, key in (
                ("R_IB", "r_ib_minutes"), ("DELTA_OB", "delta_ob_minutes"),
                ("T_TX", "t_tx_minutes"),
            ):
                if observed[target] is not None:
                    assert scenario[key][position] == observed[target]
                    support_key = "ib_support" if target == "R_IB" else f"{target.lower()}_support"
                    assert scenario[support_key][position] == "SUPPORTED"


def test_scenario_rng_keys_match_frozen_uniform_contract():
    manifest = _manifest()
    seed = manifest["scenario_RNG_contract"]["seed"]
    assert seed == 20260813
    scenario = pq.read_table(ARTIFACT_DIR / "scenario.parquet").to_pydict()
    for index, (episode, scenario_id) in enumerate(zip(
        scenario["episode_id"], scenario["scenario_id"],
    )):
        if index % 5000 != 0:
            continue
        expected = "|".join(
            _uniform(seed, episode, scenario_id, target)[1]
            for target in ("R_IB", "DELTA_OB", "T_TX")
        )
        assert scenario["scenario_seed_key"][index] == expected
    # Scenario identity is (decision_node_id, scenario_id); uniforms are
    # keyed by episode_id so nodes of one episode reuse the frozen draws.
    assert len(set(zip(scenario["decision_node_id"], scenario["scenario_id"]))) == 1824 * 250
    assert all(value == 1.0 / 250 for value in scenario["scenario_weight"][:250])


def test_equivalence_evidence_is_pass():
    evidence = json.loads(
        (OUT / "EXP234_BATCHED_WARNING_EQUIVALENCE_V1.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "PASS"
    assert evidence["sampled_category_identity"] is True
    assert evidence["tail_flag_identity"] is True
    assert evidence["nodes_checked"] == 3
    assert evidence["final_test_access_count"] == 0
