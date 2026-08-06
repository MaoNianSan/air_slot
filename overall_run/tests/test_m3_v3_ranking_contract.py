from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.skip(
    "LEGACY_AUDIT_ONLY: V3 ranking integration awaits the formal M4 migration",
    allow_module_level=True,
)

from src.config import load_config
from src.legacy.m3_v3_audit import (
    BURDEN_ONLY_TEST_FIXTURE_IDS,
    FORMAL_ACTION_IDS,
    burden_only_test_parameters,
    generate_m3_library,
    load_actions,
)
from src.m4_evaluation import derive_ranking_views
from src.m4_screening import screen_physical_actions


ROOT = Path(__file__).resolve().parents[1]


def _config_actions():
    cfg = load_config(ROOT, "fast")
    return cfg, load_actions(cfg.scientific)


def test_v3_action_library_and_fixture_separation() -> None:
    cfg, actions = _config_actions()
    assert cfg.scientific["m3"]["response_parameter_version"] == "M3_RESPONSE_V3_EXPANDED"
    assert len(actions) == len(FORMAL_ACTION_IDS) == 26
    assert len(set(actions)) == 26
    assert not (BURDEN_ONLY_TEST_FIXTURE_IDS & set(actions))
    assert set(burden_only_test_parameters()["action_id"]) == BURDEN_ONLY_TEST_FIXTURE_IDS


def test_a00_identity_fixed_seed_and_no_duplicate_parameters() -> None:
    cfg, actions = _config_actions()
    first = generate_m3_library(actions, 128, 20260731, cfg.scientific)
    second = generate_m3_library(dict(reversed(list(actions.items()))), 128, 20260731, cfg.scientific)
    assert np.all(first.recovery_rates["A00"] == 0.0)
    assert np.all(first.implementation_costs_rmb["A00"] == 0.0)
    assert first.sample_hash == second.sample_hash
    comparable = first.parameter_table.drop(columns=["action_id", "parameter_source", "parameter_version"])
    assert not comparable.duplicated().any()
    audit = ROOT.parent / "reports" / "M3_V3_DOMINANCE_AUDIT.csv"
    assert audit.exists()
    dominance = pd.read_csv(audit)
    assert not dominance["unconditional_dominance"].any()
    assert not dominance["near_duplicate"].any()


def test_typed_gates_and_fail_closed_missing_gate() -> None:
    _, actions = _config_actions()
    snapshot = pd.DataFrame([{
        "episode_id": "e1", "snapshot_id": "s1", "flight_id": "f1", "airport": "EHAM",
        "snapshot_stage": "t1", "airport_flow_pressure": 0.1,
    }])
    base = {
        "episode_id": "e1", "snapshot_id": "s1", "capacity_threshold": 10.0,
        "capacity_reference_p05": 0.0, "capacity_reference_p95": 1.0,
        "action_window_open": True, "action_window_margin": 100.0,
        "lead_time_margin": 100.0, "authority_allowed": True,
        "resource_available_f": 1.0, "resource_available_p": 1.0, "resource_available_r": 1.0,
        "authority_profile_id": "PUBLIC_RULE_V3",
        "aircraft_swap_available": True, "rotation_reassignment_available": True,
        "standby_aircraft_available": True, "crew_swap_available": True,
        "standby_crew_available": True, "crew_reposition_available": True,
        "gate_reassignment_available": True, "ground_support_available": True,
        "cancellation_authority_available": True, "network_reset_authority_available": True,
        "aircraft_group_compatible": True, "crew_qualification_compatible": True,
    }
    rules = pd.DataFrame([{**base, "action_id": action_id} for action_id in actions])
    passed = screen_physical_actions(rules, snapshot, actions, np.array([True]))
    assert passed.audit.set_index("action_id").loc[["A71", "A81", "A61", "A62"], "physical_feasible"].all()
    rules["aircraft_swap_available"] = rules["aircraft_swap_available"].astype("boolean")
    rules.loc[rules["action_id"].eq("A71"), "aircraft_swap_available"] = pd.NA
    failed = screen_physical_actions(rules, snapshot, actions, np.array([True])).audit.set_index("action_id")
    assert not bool(failed.loc["A71", "physical_feasible"])
    assert failed.loc["A71", "typed_resource_status"] == "MISSING"


def test_ranking_prefix_padding_and_shuffle_invariance() -> None:
    full = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "rank": 1, "action_id": "A11", "score": 1.0, "expected_residual": .8, "cvar_component": 1.2},
        {"episode_id": "e1", "snapshot_id": "s1", "rank": 2, "action_id": "A00", "score": 2.0, "expected_residual": 1.8, "cvar_component": 2.2},
        {"episode_id": "e1", "snapshot_id": "s1", "rank": 3, "action_id": "A21", "score": 3.0, "expected_residual": 2.8, "cvar_component": 3.2},
    ])
    views = derive_ranking_views(full)
    shuffled = derive_ranking_views(full.sample(frac=1, random_state=7))
    for ranking_k in (1, 2, 3, 5):
        assert views[ranking_k].equals(shuffled[ranking_k])
    assert views[1]["action_id"].tolist() == views[2]["action_id"].tolist()[:1]
    assert views[2]["action_id"].tolist() == views[3]["action_id"].tolist()[:2]
    assert views[3]["action_id"].tolist() == views[5]["action_id"].tolist()[:3]
    assert views[5]["action_id"].dropna().tolist().count("A00") == 1
    assert views[5]["is_padding"].sum() == 2
    assert views[5].loc[views[5]["is_padding"], "action_id"].isna().all()
    assert views[5]["effective_action_count"].iat[0] == 3
    assert not bool(views[5]["full_k_support"].iat[0])
