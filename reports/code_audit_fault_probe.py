from __future__ import annotations

import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import yaml


PROJECT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT / "reports"
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from overall_adv.src.pipeline_analysis import (
    CandidateSetContractError,
    validate_candidate_sets,
)
from overall_run.src.config import load_config as load_run_config
from overall_run.src.m1_feature_contract import (
    M1FeatureContract,
    M1FeatureContractError,
)
from overall_run.src.m1_training import prepare_model_frame
from overall_run.src.m3 import generate_m3_library, load_actions
from overall_run.src.m4 import screen_physical_actions
from pre.src.pipeline_config import load_config as load_pre_config
from pre.src.predecessor_matcher import (
    PREDECESSOR_FEATURE_COLUMNS,
    apply_predecessor_support_rule,
    attach_predecessor_features_to_snapshots,
    build_predecessor_candidates,
    build_predecessor_features,
)
from ranking_contract import (
    RANKING_DEPTHS,
    build_ranking_prefixes,
    full_ranking_from_scores,
    validate_ranking_prefixes,
)


class _MovementReference:
    def resolve(self, row: pd.Series):
        return 100.0, "fixture", 10, ""


class _TurnaroundReference:
    def resolve(self, airport: str, aircraft_group: str, time_bin: str):
        return 60.0, 30.0, 30.0, 0.8, "fixture", 10


def _legs() -> pd.DataFrame:
    rows = [
        {
            "episode_id": "valid_old", "flight_id": "valid_old", "icao24": "abc123",
            "origin": "EHAM", "destination": "EDDF",
            "firstseen_utc": pd.Timestamp("2022-05-02T10:00:00Z"),
            "lastseen_utc": pd.Timestamp("2022-05-02T11:00:00Z"),
            "observed_movement_time": 60.0, "aircraft_group": "narrow_body",
            "typecode": "A320", "registration": "N12345",
            "state_day_complete": True, "firstseen_month": 5,
            "firstseen_time_bin": "06_12", "distance_bin": "500_1000",
            "origin_region": "NW_EUROPE", "destination_region": "CENTRAL_EUROPE",
            "region_pair": "NW_EUROPE__CENTRAL_EUROPE",
        },
        {
            "episode_id": "overlap", "flight_id": "overlap", "icao24": "abc123",
            "origin": "LEMD", "destination": "EDDF",
            "firstseen_utc": pd.Timestamp("2022-05-02T11:30:00Z"),
            "lastseen_utc": pd.Timestamp("2022-05-02T12:30:00Z"),
            "observed_movement_time": 60.0, "aircraft_group": "narrow_body",
            "typecode": "A320", "registration": "N12345",
            "state_day_complete": True, "firstseen_month": 5,
            "firstseen_time_bin": "06_12", "distance_bin": "500_1000",
            "origin_region": "IBERIA", "destination_region": "CENTRAL_EUROPE",
            "region_pair": "IBERIA__CENTRAL_EUROPE",
        },
        {
            "episode_id": "current", "flight_id": "current", "icao24": "abc123",
            "origin": "EDDF", "destination": "LEMD",
            "firstseen_utc": pd.Timestamp("2022-05-02T12:00:00Z"),
            "lastseen_utc": pd.Timestamp("2022-05-02T14:00:00Z"),
            "observed_movement_time": 120.0, "aircraft_group": "narrow_body",
            "typecode": "A320", "registration": "N12345",
            "state_day_complete": True, "firstseen_month": 5,
            "firstseen_time_bin": "12_18", "distance_bin": "1000_1500",
            "origin_region": "CENTRAL_EUROPE", "destination_region": "IBERIA",
            "region_pair": "CENTRAL_EUROPE__IBERIA",
        },
    ]
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


def _expect_error(call: Callable[[], object], contains: str) -> str:
    try:
        call()
    except Exception as exc:
        detail = f"{type(exc).__name__}:{exc}"
        if contains not in detail:
            raise AssertionError(f"wrong error: {detail}") from exc
        return detail
    raise AssertionError("expected rejection was not raised")


def case_r3_seconds() -> str:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "override.yaml"
        path.write_text(
            yaml.safe_dump({"predecessor_matching": {"gap_threshold_minutes": 94100.4}}),
            encoding="utf-8",
        )
        return _expect_error(
            lambda: load_pre_config(path, mode="fast"),
            "predecessor administrative ceiling below gap threshold",
        )


def case_unknown_pre_override() -> str:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "override.yaml"
        path.write_text("predecessor_matching:\n  foo:\n    bar: 1\n", encoding="utf-8")
        return _expect_error(
            lambda: load_pre_config(path, mode="fast"),
            "UNKNOWN_CONFIG_FIELD=predecessor_matching.foo",
        )


def case_overlap_backtrack() -> str:
    cfg = load_pre_config(mode="fast")
    result = apply_predecessor_support_rule(
        build_predecessor_candidates(_legs(), cfg), cfg
    )
    current = result[result["episode_id"].eq("current")].iloc[0]
    assert current["nearest_raw_candidate_id"] == "overlap"
    assert current["raw_candidate_rejection_reason"] == "TEMPORAL_OVERLAP"
    assert current["predecessor_flight_id"] == "valid_old"
    return f"selected={current['predecessor_flight_id']};depth={current['search_depth']}"


def case_decision_availability() -> str:
    cfg = load_pre_config(mode="fast")
    features = build_predecessor_features(
        _legs().query("episode_id != 'overlap'"),
        _MovementReference(),
        _TurnaroundReference(),
        cfg,
    )
    snapshots = pd.DataFrame([
        {"episode_id": "current", "snapshot_stage": "t1", "decision_time_utc": pd.Timestamp("2022-05-02T10:30:00Z")},
        {"episode_id": "current", "snapshot_stage": "t2", "decision_time_utc": pd.Timestamp("2022-05-02T11:30:00Z")},
        {"episode_id": "current", "snapshot_stage": "t3", "decision_time_utc": pd.Timestamp("2022-05-02T12:30:00Z")},
    ])
    attached = attach_predecessor_features_to_snapshots(snapshots, features)
    observed = dict(zip(attached["snapshot_stage"], attached["has_supported_predecessor"].astype(bool)))
    assert observed == {"t1": False, "t2": True, "t3": True}
    return str(observed)


def case_action_count() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"] = scientific["m3"]["actions"][:-1]
    return _expect_error(lambda: load_actions(scientific), "ACTION_LIBRARY_MISMATCH")


def case_duplicate_a00() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"].append(deepcopy(scientific["m3"]["actions"][0]))
    return _expect_error(lambda: load_actions(scientific), "M3_DUPLICATE_ACTION_ID")


def case_string_boolean() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m3"]["actions"][1]["capacity_required"] = "false"
    return _expect_error(
        lambda: load_actions(scientific),
        "M3_BOOLEAN_FIELD_INVALID:A11:capacity_required",
    )


def _ranking_fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    universe = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    scores = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A00", "action_family": "null", "score": 2.0, "expected_residual": 2.0, "priority": 0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "score": 1.0, "expected_residual": 1.0, "priority": 1},
    ])
    return universe, scores


def case_padding_a00() -> str:
    universe, scores = _ranking_fixture()
    all_k, _ = build_ranking_prefixes(
        universe, full_ranking_from_scores(scores, "score")
    )
    corrupted = all_k.copy()
    index = corrupted.index[corrupted["is_padding"].astype(bool)][0]
    corrupted.loc[index, "action_id"] = "A00"
    return _expect_error(
        lambda: validate_ranking_prefixes(corrupted),
        "RANKING_PADDING_ACTION_NON_NULL",
    )


def case_missing_typed_gate() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
    actions = load_actions(cfg.scientific)
    rules = _positive_rules(actions)
    rules["aircraft_swap_available"] = rules["aircraft_swap_available"].astype(object)
    mask = rules["action_id"].eq("A71")
    rules.loc[mask, "aircraft_swap_available"] = pd.NA
    rules.loc[mask, "aircraft_swap_available_evidence_status"] = pd.NA
    snapshots = pd.DataFrame([{"episode_id": "e1", "snapshot_id": "s1"}])
    audit = screen_physical_actions(
        rules,
        snapshots,
        actions,
        np.array([True]),
        cfg.scientific["m3"]["resource_profiles"],
    ).audit
    row = audit[audit["action_id"].eq("A71")].iloc[0]
    assert not bool(row["physical_feasible"])
    assert "TYPED_GATE_MISSING:aircraft_swap_available" in row["failure_codes"]
    return str(row["failure_codes"])


def case_feature_order() -> str:
    frame = pd.DataFrame({"numeric": [1.0], "category": ["A"]})
    contract = M1FeatureContract.build(frame, ["numeric", "category"], ["category"])
    swapped = frame[["category", "numeric"]]
    return _expect_error(
        lambda: contract.validate_feature_frame(swapped),
        "M1_INFERENCE_FEATURE_ORDER_MISMATCH",
    )


def case_future_successor() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
    scientific = deepcopy(cfg.scientific)
    scientific["m1"]["feature_allowlist"] = [
        *scientific["m1"].get("feature_allowlist", []),
        "future_successor_delay",
    ]
    snapshots = pd.DataFrame([{
        "episode_id": "e1", "flight_id": "f1", "snapshot_id": "s1",
        "decision_time": pd.Timestamp("2022-05-02T12:00:00Z"),
        "current_altitude": 10000.0, "future_successor_delay": 999.0,
    }])
    episodes = pd.DataFrame([{"episode_id": "e1", "y_movement_raw": 12.0}])
    _, features, _, _ = prepare_model_frame(snapshots, episodes, scientific)
    assert "future_successor_delay" not in features
    return ",".join(features)


def case_candidate_mismatch() -> str:
    global_candidates = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11"},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A12"},
    ])
    local_candidates = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11"},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A13"},
    ])
    try:
        validate_candidate_sets(global_candidates, local_candidates)
    except CandidateSetContractError as exc:
        assert exc.details["mismatch_episode_count"] == 1
        return str(exc)
    raise AssertionError("candidate mismatch accepted")


def case_expected_residual_tie() -> str:
    scores = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "score": 1.0, "expected_residual": 4.0, "priority": 1, "expected_implementation_cost_rmb": 1.0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A12", "action_family": "hold", "score": 1.0, "expected_residual": 3.0, "priority": 2, "expected_implementation_cost_rmb": 99.0},
    ])
    order = full_ranking_from_scores(scores, "score")["action_id"].tolist()
    assert order == ["A12", "A11"]
    return ",".join(order)


def case_seed_order() -> str:
    cfg = load_run_config(PROJECT / "overall_run", mode="fast")
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
    return first.sample_hash


def case_zero_candidate() -> str:
    universe = pd.DataFrame([{"episode_id": "e0", "snapshot_id": "s0"}])
    all_k, _ = build_ranking_prefixes(universe, pd.DataFrame())
    assert len(all_k) == sum(RANKING_DEPTHS) == 11
    assert all_k["is_padding"].all()
    assert all_k["action_id"].isna().all()
    return f"rows={len(all_k)}"


CASES = [
    ("R3 threshold minutes changed to seconds", "reject", "PRE config validator", case_r3_seconds),
    ("unknown PRE override field added", "reject", "PRE strict schema loader", case_unknown_pre_override),
    ("overlapping immediate leg masks older valid predecessor", "select valid_old", "M1 predecessor backtracking", case_overlap_backtrack),
    ("predecessor available after t1 but before t2", "t1 false; t2/t3 true", "snapshot availability gate", case_decision_availability),
    ("formal action count changed from 26 to 25", "reject", "M3 library loader", case_action_count),
    ("A00 duplicated in formal action inventory", "reject", "M3 action authority", case_duplicate_a00),
    ("M3 boolean false supplied as string", "reject", "M3 strict boolean schema", case_string_boolean),
    ("padding action_id changed from null to A00", "reject", "ranking validator", case_padding_a00),
    ("required M3 typed-gate column removed", "fail closed", "M4 physical screen", case_missing_typed_gate),
    ("training/inference feature order swapped", "reject", "M1 feature contract", case_feature_order),
    ("future successor field added to M1 allowlist", "exclude", "M1 prohibited-pattern contract", case_future_successor),
    ("overall_adv Global/Local candidate set mismatch", "reject", "candidate-set contract", case_candidate_mismatch),
    ("M4 score tie requires expected_residual tie-break", "A12 ranked first", "shared full ranking", case_expected_residual_tie),
    ("14-thread/action scheduling seed order changed", "scientific draws unchanged", "stable per-action M3 seed namespaces", case_seed_order),
    ("ranking boundary with 0 real candidates", "emit 11 padding rows for known key", "ranking prefix builder", case_zero_candidate),
]


def main() -> int:
    rows = []
    for injection, expected, mechanism, probe in CASES:
        try:
            detail = probe()
            status = "PASS"
        except Exception as exc:
            status = "FAIL"
            detail = f"{type(exc).__name__}:{exc}"
        rows.append({
            "injection": injection,
            "expected_detection": expected,
            "status": status,
            "mechanism": mechanism,
            "detail": detail,
        })
    frame = pd.DataFrame(rows)
    frame.to_csv(REPORTS / "FAULT_INJECTION_RESULTS.csv", index=False)
    (REPORTS / "FAULT_INJECTION_RESULTS.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    pass_count = int(frame["status"].eq("PASS").sum())
    fail_count = int(frame["status"].eq("FAIL").sum())
    status = "PASS" if fail_count == 0 and pass_count == len(CASES) else "FAIL"
    markdown = f"""# Fault Injection Audit

Audit date: 2026-08-02

FAULT_INJECTION_STATUS={status}
FAULT_INJECTION_PASS_COUNT={pass_count}
FAULT_INJECTION_FAIL_COUNT={fail_count}

{frame.to_markdown(index=False)}

The audit probe is `reports/code_audit_fault_probe.py`; it preserves all 15 active injections.
"""
    (REPORTS / "FAULT_INJECTION_AUDIT.md").write_text(markdown, encoding="utf-8")
    print(f"FAULT_INJECTION_STATUS={status}")
    print(f"FAULT_INJECTION_PASS_COUNT={pass_count}")
    print(f"FAULT_INJECTION_FAIL_COUNT={fail_count}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
