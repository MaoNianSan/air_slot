from __future__ import annotations

from pathlib import Path
import sys
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.skip(
    "LEGACY_AUDIT_ONLY: V3 channel-level response is not an active formal contract",
    allow_module_level=True,
)

from src.config import load_config
from src.m3 import (
    FORMAL_ACTION_IDS,
    STRESS_TEST_ACTION_IDS,
    _parameter_rows,
    generate_m3_library,
    load_actions,
)
from src.m4 import evaluate_m4, fit_m4, screen_physical_actions
from src.m3_reachability import resolve_action_reachability


def _rules(actions: dict[str, object]) -> pd.DataFrame:
    typed = sorted({gate for action in actions.values() for gate in action.typed_gates})
    rows = []
    for action_id in actions:
        row = {
            "episode_id": "e1", "snapshot_id": "s1", "action_id": action_id,
            "airport_flow_pressure": 20.0, "capacity_threshold": 100.0,
            "capacity_reference_p05": 10.0, "capacity_reference_p95": 80.0,
            "action_window_margin": 120.0, "action_window_open": True,
            "resource_profile_id": "normal", "authority_profile_id": "public_rule_v1",
            "authority_allowed": True, "lead_time_margin": 120.0,
        }
        for gate in typed:
            row[gate] = False
            row[f"{gate}_evidence_status"] = "UNSUPPORTED"
        rows.append(row)
    return pd.DataFrame(rows)


def _positive_rules(actions: dict[str, object]) -> pd.DataFrame:
    typed = sorted({gate for action in actions.values() for gate in action.typed_gates})
    rows = []
    for action_id in actions:
        row = {
            "episode_id": "e1", "snapshot_id": "s1", "action_id": action_id,
            "airport_flow_pressure": 0.0, "capacity_threshold": 100.0,
            "capacity_reference_p05": 0.0, "capacity_reference_p95": 100.0,
            "action_window_margin": 120.0, "action_window_open": True,
            "resource_available_f": 1.0, "resource_available_p": 1.0,
            "resource_available_r": 1.0, "resource_profile_id": "ample",
            "authority_profile_id": "strict_fixture", "authority_allowed": True,
            "lead_time_margin": 120.0,
        }
        for gate in typed:
            row[gate] = True
            row[f"{gate}_evidence_status"] = "OBSERVED"
        rows.append(row)
    return pd.DataFrame(rows)


def test_M3_V3_action_count_is_26_and_exact_action_set() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    assert len(actions) == 26
    assert set(actions) == FORMAL_ACTION_IDS
    assert not set(actions) & STRESS_TEST_ACTION_IDS


def test_all_actions_have_complete_schema_and_generate_draws() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    parameters = _parameter_rows(actions, cfg.scientific)
    required = {
        "mu_F", "mu_P", "mu_R", "K_F", "K_P", "K_R", "kappa_eta",
        "CV_K", "p_fail", "capacity_requirement", "window_requirement",
        "resource_requirement", "authority_requirement", "lead_time_requirement",
        "aircraft_requirement", "crew_requirement", "passenger_requirement",
        "airport_requirement", "priority", "family", "description", "provisional",
        "parameter_source",
    }
    assert required.issubset(parameters.columns)
    assert not parameters[list(required)].isna().any().any()
    artifact = generate_m3_library(actions, 32, 20260802, cfg.scientific)
    assert set(artifact.recovery_rates) == set(actions)
    assert all(artifact.recovery_rates[action].shape == (32, 3) for action in actions)


def test_all_actions_reach_M4_and_extreme_actions_fail_closed() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    snapshots = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    result = screen_physical_actions(
        _rules(actions), snapshots, actions, np.array([True]),
        cfg.scientific["m3"]["resource_profiles"],
    )
    assert set(result.audit["action_id"]) == set(actions)
    extreme = result.audit[result.audit["action_id"].isin(
        ["A61", "A62", "A71", "A72", "A73", "A81", "A82", "A83"]
    )]
    assert all(actions[action_id].typed_gates for action_id in extreme["action_id"])
    assert not extreme["physical_feasible"].any()
    assert extreme["gate_typed_status"].isin(["FAIL_CLOSED", "MISSING"]).all()


def test_V2_remains_reproducible_and_A61_A62_are_versioned() -> None:
    scientific = yaml.safe_load((ROOT / "config" / "scientific.yaml").read_text(encoding="utf-8"))
    actions = load_actions(scientific)
    first = generate_m3_library(actions, 16, 7, scientific)
    second = generate_m3_library(actions, 16, 7, scientific)
    assert first.sample_hash == second.sample_hash
    v2 = _parameter_rows(actions, scientific).set_index("action_id")
    assert v2.loc[["A61", "A62"], ["mu_F", "mu_P", "mu_R"]].eq(0).all().all()

    cfg = load_config(ROOT, mode="fast")
    v3 = _parameter_rows(load_actions(cfg.scientific), cfg.scientific).set_index("action_id")
    assert v3.loc[["A61", "A62"], ["mu_F", "mu_P", "mu_R"]].gt(0).any(axis=1).all()
    assert v3.loc["A61", "description"].startswith("CONTROLLED_CANCELLATION")


def test_m3_string_false_rejected() -> None:
    cfg = load_config(ROOT, mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"][1]["capacity_required"] = "false"
    with pytest.raises(RuntimeError, match="M3_BOOLEAN_FIELD_INVALID:A11:capacity_required"):
        load_actions(scientific)


def test_m3_string_true_rejected() -> None:
    cfg = load_config(ROOT, mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"][1]["capacity_required"] = "true"
    with pytest.raises(RuntimeError, match="M3_BOOLEAN_FIELD_INVALID:A11:capacity_required"):
        load_actions(scientific)


def test_m3_real_boolean_accepted() -> None:
    cfg = load_config(ROOT, mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"][1]["capacity_required"] = False
    actions = load_actions(scientific)
    assert actions["A11"].capacity_required is False


def test_m3_rule_string_boolean_rejected() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    rules = _rules(actions)
    rules["action_window_open"] = rules["action_window_open"].astype(object)
    rules.loc[rules["action_id"].eq("A11"), "action_window_open"] = "false"
    snapshots = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    with pytest.raises(RuntimeError, match="M3_BOOLEAN_FIELD_INVALID"):
        screen_physical_actions(
            rules,
            snapshots,
            actions,
            np.array([True]),
            cfg.scientific["m3"]["resource_profiles"],
        )


def test_all_26_actions_reach_scored_in_synthetic_positive_fixture() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    response = generate_m3_library(actions, 32, 20260802, cfg.scientific)
    synthetic = deepcopy(response)
    for action_id in actions:
        if action_id == "A00":
            continue
        synthetic.recovery_rates[action_id][:] = 1.0
        synthetic.implementation_costs_rmb[action_id][:] = 0.0
        synthetic.success[action_id][:] = True
    snapshots = pd.DataFrame([{
        "episode_id": "e1", "snapshot_id": "s1", "flight_id": "f1",
        "airport": "EHAM", "snapshot_stage": "t1",
    }])
    physical = screen_physical_actions(
        _positive_rules(actions),
        snapshots,
        actions,
        np.array([True]),
        cfg.scientific["m3"]["resource_profiles"],
    )
    costs = {
        channel: np.full((1, synthetic.n_samples), 1_000_000.0)
        for channel in ("F", "P", "R")
    }
    scores, _, candidates = evaluate_m4(
        snapshots,
        costs,
        physical.audit,
        actions,
        synthetic,
        fit_m4(cfg.scientific),
    )
    assert set(scores["action_id"]) == set(actions)
    assert candidates["is_evaluated"].all()


def test_m3_draws_are_invariant_to_action_iteration_order() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    reversed_actions = dict(reversed(list(actions.items())))
    first = generate_m3_library(actions, 32, 20260802, cfg.scientific)
    second = generate_m3_library(reversed_actions, 32, 20260802, cfg.scientific)
    assert first.sample_hash == second.sample_hash
    for action_id in actions:
        assert np.array_equal(first.recovery_rates[action_id], second.recovery_rates[action_id])
        assert np.array_equal(
            first.implementation_costs_rmb[action_id],
            second.implementation_costs_rmb[action_id],
        )


def test_zero_reachability_no_longer_uses_removed_recovery_ratio_gate() -> None:
    cfg = load_config(ROOT, mode="fast")
    actions = load_actions(cfg.scientific)
    candidates = pd.DataFrame([{
        "action_id": action_id,
        "evaluation_status": "DECISION_VALUE_REJECTED",
        "physical_rejection_codes": "PASS",
        "m2_cost_supported": True,
        "gate_typed": True,
        "is_evaluated": False,
    } for action_id in actions])
    resolved = resolve_action_reachability(candidates, actions, cfg.scientific).set_index(
        "action_id"
    )
    assert resolved.loc["A11", "zero_reachability_class"] == "EMPIRICALLY_UNREACHED_IN_FAST"
