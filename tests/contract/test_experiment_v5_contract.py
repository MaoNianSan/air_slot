from datetime import date
from pathlib import Path

import pytest

from exp.common.contracts import RuntimeMode, default_cross_contract
from exp.common.rng import response_rng_key, stable_uniform
from exp.common.split import assign_v5_split, validate_episode_split
from exp.exp1.runner import Exp1Runner
from exp.exp2.metrics import formal_multi_action_gate, reference_objective_selection_penalty
from exp.exp2.representations import corrupt_scenario_lineage, point_collapse
from exp.exp3.ablations import transformed_ablation
from exp.exp4.portability import portability_hard_gates
from formal.artifacts import load_formal_bundle, write_formal_bundle
from formal.pipeline import _m3_registry_hash, run_formal_pipeline
from model.M1.semantics import total_takeoff_delay_minutes
from model.common.errors import ContractError


def test_cross_contract_is_v5_single_source_of_truth():
    contract = default_cross_contract()
    assert contract.principal_dataset == "data2_2019"
    assert contract.portability_dataset == "data1_2019"
    assert contract.hidden_size_candidates == (8, 16, 32)
    assert contract.lead_times_minutes == (480, 420, 360, 300, 240, 180, 120, 60, 30, 15)
    assert contract.paper_full_scenarios == 1000
    assert set(contract.rng_streams) == {
        "m1_scenario", "m3_m4_response", "exp2_lineage_corruption",
        "bootstrap", "llm_case_selection", "llm_repetition",
    }


def test_v5_split_is_episode_safe():
    assert assign_v5_split(date(2019, 9, 30)) == "development"
    assert assign_v5_split(date(2019, 10, 1)) == "final_test"
    with pytest.raises(ContractError, match="EPISODE_CROSSES_V5_SPLIT"):
        validate_episode_split([
            {"episode_id": "e1", "episode_date": "2019-09-30"},
            {"episode_id": "e1", "episode_date": "2019-10-01"},
        ])


def test_delay_identity_is_d_ob_plus_d_tx_per_scenario():
    # Manuscript identity (reconciliation 2026-08-19): D_TO = D_OB + D_TX.
    d_to = total_takeoff_delay_minutes(
        t_ob_minutes=80, t_tx_minutes=30,
        scheduled_ob_minutes=90, taxi_reference_minutes=15,
    )
    d_ob = max(0, 80 - 90)
    d_tx = max(0, 30 - 15)
    assert d_to == d_ob + d_tx
    assert d_to == 15
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=-5, t_tx_minutes=30, taxi_reference_minutes=15
    ) == 15
    assert total_takeoff_delay_minutes(
        delta_ob_minutes=12.5, t_tx_minutes=7.5, taxi_reference_minutes=5.0
    ) == 15.0


def test_point_collapse_is_a_coherent_observed_scenario():
    scenarios = (
        {"scenario_id": 0, "scenario_weight": .25, "r_ib_minutes": 4,
         "r_ob_minutes": 10, "t_tx_minutes": 2},
        {"scenario_id": 1, "scenario_weight": .75, "r_ib_minutes": 8,
         "r_ob_minutes": 20, "t_tx_minutes": 6},
    )
    point = point_collapse(scenarios)
    selected = next(row for row in scenarios if row["scenario_id"] == point["selected_scenario_id"])
    assert tuple(point[name] for name in ("r_ib_minutes", "r_ob_minutes", "t_tx_minutes")) == tuple(
        selected[name] for name in ("r_ib_minutes", "r_ob_minutes", "t_tx_minutes"))


def test_corruption_q_zero_is_exact_and_q_one_preserves_marginals():
    scenarios = tuple({"episode_id": "e", "decision_node_id": "n", "scenario_id": index,
                       "scenario_weight": .25, "r_ib_minutes": index,
                       "r_ob_minutes": index + 10, "t_tx_minutes": index + 20}
                      for index in range(4))
    aligned, aligned_audit = corrupt_scenario_lineage(
        scenarios, global_seed=7, episode_id="e", decision_node_id="n", corruption_q=0)
    corrupted, audit = corrupt_scenario_lineage(
        scenarios, global_seed=7, episode_id="e", decision_node_id="n", corruption_q=1)
    assert aligned == scenarios
    assert aligned_audit["marginals_preserved"] is True
    assert audit["marginals_preserved"] is True
    for field in ("r_ib_minutes", "r_ob_minutes", "t_tx_minutes"):
        assert sorted(row[field] for row in corrupted) == sorted(row[field] for row in scenarios)


def test_selection_penalty_scores_variant_choice_under_reference():
    result = reference_objective_selection_penalty(
        {"A00": 10.0, "A01": 8.0}, {"A00": 5.0, "A01": 7.0})
    assert result["selected_action"] == "A00"
    assert result["reference_action"] == "A01"
    assert result["ReferenceObjectiveSelectionPenalty"] == 2.0


def test_formal_multi_action_claim_gate_does_not_change_formal_rules():
    assert formal_multi_action_gate(99)["claim_gate"] == "SCENARIO_CONDITIONED_DECISION_VALUE_ANALYSIS"
    assert formal_multi_action_gate(100)["principal_authoritative_ranking_claim"] is True
    assert formal_multi_action_gate(500)["claim_gate"] == "STRONG_AUTHORITATIVE_RANKING_CLAIM_ALLOWED"


def test_exp3_coverage_ablation_preserves_unsupported_null():
    formal = {"consequence_rows": [{"component": "P_time", "value": None, "support": "ABSTAIN"}]}
    result = transformed_ablation(formal, "NO_MATERIAL_COVERAGE_GATE")
    assert result["consequence_rows"][0]["value"] is None
    assert result["unsupported_value_policy"] == "PRESERVE_NULL_NOT_ZERO"


def test_response_rng_key_excludes_decision_time_and_is_stable():
    key = response_rng_key(7, "e", 1, "A01", "success")
    assert len(key) == 5
    assert stable_uniform("m3_m4_response", *key) == stable_uniform("m3_m4_response", *key)


def test_formal_artifact_is_write_once_and_hash_checked(tmp_path: Path):
    path = tmp_path / "artifacts" / "formal" / "bundle.json"
    bundle = run_formal_pipeline([{
        "episode_id": "e", "decision_node_id": "n",
        "decision_time": "2019-08-01T00:00:00+00:00",
        "information_cutoff": "2019-08-01T00:00:00+00:00",
        "m1_scenarios": (), "m2_consequences": (), "m3_actions": (), "m4_decision": {},
    }])
    write_formal_bundle(path, bundle)
    loaded = load_formal_bundle(path)
    assert loaded.bundle_hash == bundle.bundle_hash
    with pytest.raises(ContractError, match="FORMAL_ARTIFACT_IMMUTABLE_OVERWRITE"):
        write_formal_bundle(path, bundle)


def test_m3_registry_hash_uses_action_registry_digest():
    from pathlib import Path

    from model.M3.registry import ActionRegistry

    registry = ActionRegistry.load(Path("registries/action_templates.yaml"))
    assert _m3_registry_hash(registry) == registry.digest()
    assert _m3_registry_hash(registry.model_dump(mode="json")) == registry.digest()


def test_paper_full_requires_explicit_approval():
    with pytest.raises(ContractError, match="PAPER_FULL_EXPLICIT_APPROVAL_REQUIRED"):
        Exp1Runner().run([{"episode_id": "e", "metric": 1}], smoke=True,
                         runtime_mode=RuntimeMode.PAPER_FULL.value, split="FINAL_TEST")


def test_data1_portability_hard_gates():
    assert portability_hard_gates()["DATA1_PORTABILITY_STATUS"] == "PASS"
    assert portability_hard_gates(substitutions=({"declared": False},))["DATA1_PORTABILITY_STATUS"] == "FAIL"
