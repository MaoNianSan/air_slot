"""A-SET (M3 minimal executable action-set freeze) contract tests."""

import json
from pathlib import Path

from exp.exp3.action_set_freeze import (
    FAMILY_MAP,
    build_action_set_frozen,
    family_orthogonality_table,
    family_support_sets,
    family_of,
    mechanism_signature,
    orthogonality_check_table,
    support_set,
)
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[2]


def _action(action_id, family, components, mechanism="MECH_X"):
    return {
        "action_id": action_id,
        "action_family": family,
        "affected_components": list(components),
        "executable_v2": True,
        "assumption_grounded": {
            "formula": "R_a(s) = 1",
            "mechanism": mechanism,
            "sensitivity_band": {"low": {}, "base": {}, "high": {}},
            "literature": ["DOI_1"],
        },
    }


def test_family_of_maps_registry_families():
    assert family_of({"action_family": "aircraft_recovery"}) == "AIRCRAFT_SWAP"
    assert family_of({"action_family": "crew_recovery"}) == "CREW_SWAP"
    assert family_of({"action_family": "timing"}) == "HOLD"
    assert family_of({"action_family": "flight_execution"}) == "PROPAGATION_BUFFER"
    assert family_of({"action_family": "passenger_recovery"}) == "PASSENGER_REASSIGNMENT"
    assert family_of({"action_family": "extreme_local_network"}) == "NETWORK_EXTREME"
    assert family_of({"action_family": "unknown"}) is None


def test_orthogonality_detects_identical_and_subset_pairs():
    actions = [
        _action("A1", "aircraft_recovery", ["F_execution", "R_operating"]),
        _action("A2", "aircraft_recovery", ["F_execution", "R_operating"]),
        _action("A3", "aircraft_recovery", ["F_execution"]),
    ]
    table = orthogonality_check_table(actions)
    assert len(table["identical_support_pairs"]) == 1
    assert {table["identical_support_pairs"][0]["action_a"], table["identical_support_pairs"][0]["action_b"]} == {"A1", "A2"}
    assert (
        table["identical_support_pairs"][0]["variant_label"]
        == "PARAMETRIC_VARIANTS_SAME_MECHANISM"
    )
    assert len(table["true_subset_pairs"]) == 2  # A3 subset of A1 and A2
    assert all(pair["retained"] is True for pair in table["true_subset_pairs"])
    assert all(
        pair["variant_label"] == "PARAMETRIC_VARIANTS_SAME_MECHANISM"
        for pair in table["true_subset_pairs"]
    )
    assert table["unmapped_actions"] == []


def test_family_support_sets_union_members():
    actions = [
        _action("A1", "aircraft_recovery", ["F_execution", "R_operating"]),
        _action("A2", "aircraft_recovery", ["F_continuity"]),
        _action("A3", "timing", ["P_time"]),
    ]
    supports = family_support_sets(actions)
    assert supports["AIRCRAFT_SWAP"] == frozenset({"F_execution", "R_operating", "F_continuity"})
    assert supports["HOLD"] == frozenset({"P_time"})


def test_family_orthogonality_reports_mutually_non_contained():
    actions = [
        _action("A1", "aircraft_recovery", ["F_execution"]),
        _action("A2", "crew_recovery", ["F_propagation"]),
        _action("A3", "timing", ["P_time"]),
    ]
    table = family_orthogonality_table(actions)
    assert table["status"] == "MUTUALLY_NON_CONTAINED"
    assert table["violating_pairs"] == []
    assert all(
        pair["containment"] == "MUTUALLY_NON_CONTAINED" for pair in table["pairwise"]
    )


def test_family_orthogonality_documents_nested_support():
    actions = [
        _action("A1", "aircraft_recovery", ["F_execution", "R_operating"]),
        _action("A2", "aircraft_recovery", ["F_continuity"]),
        _action("A3", "flight_execution", ["F_execution", "R_operating"]),
    ]
    table = family_orthogonality_table(actions)
    assert table["status"] == "NESTED_SUPPORT_DOCUMENTED"
    assert len(table["violating_pairs"]) == 1
    violation = table["violating_pairs"][0]
    assert violation["subset_family"] == "PROPAGATION_BUFFER"
    assert violation["superset_family"] == "AIRCRAFT_SWAP"
    assert "FAMILY_LEVEL_NESTED_SUPPORT" in violation["reason"]


def test_support_set_and_mechanism_signature():
    action = _action("A9", "timing", ["F_continuity", "P_time"], mechanism="HOLD")
    assert support_set(action) == frozenset({"F_continuity", "P_time"})
    assert mechanism_signature(action) == "HOLD"


def test_build_action_set_frozen_over_real_registry():
    design = json.loads((ROOT / "registries/m3_v2_action_response_design.json").read_text(encoding="utf-8"))
    block = build_action_set_frozen(design)
    assert block["status"] == "COMPLETED_ASSUMPTION_GROUNDED_ACTION_SET_FROZEN"
    assert block["formal_lane"] == "A00_ONLY"
    assert block["scenario_conditional_lane"] == "ALL_22_NON_A00"
    non_a00 = [a for a in design["responses"] if a["action_id"] != "A00"]
    assert len(non_a00) == 22
    # coverage: every mapped family executable; every action mapped
    assert all(value == "EXECUTABLE" for value in block["coverage"].values())
    assert block["interpretability"]["status"] == "PASS"
    assert block["orthogonality"]["unmapped_actions"] == []
    family_block = block["orthogonality"]["family_orthogonality"]
    assert family_block["schema_version"] == "M3_ACTION_FAMILY_ORTHOGONALITY_V1"
    assert set(family_block["family_support_sets"]) == set(FAMILY_MAP)
    # Frozen design reality: PROPAGATION_BUFFER is nested inside four other
    # families and AIRCRAFT_SWAP/CREW_SWAP inside HOLD; the check documents
    # this instead of claiming family-level mutual non-containment.
    assert family_block["status"] == "NESTED_SUPPORT_DOCUMENTED"
    nested = {
        (pair["subset_family"], pair["superset_family"])
        for pair in family_block["violating_pairs"]
    }
    assert nested == {
        ("AIRCRAFT_SWAP", "HOLD"),
        ("CREW_SWAP", "HOLD"),
        ("PROPAGATION_BUFFER", "AIRCRAFT_SWAP"),
        ("PROPAGATION_BUFFER", "CREW_SWAP"),
        ("PROPAGATION_BUFFER", "HOLD"),
        ("PROPAGATION_BUFFER", "NETWORK_EXTREME"),
    }
    assert all(
        pair["variant_label"] == "PARAMETRIC_VARIANTS_SAME_MECHANISM"
        for pair in (
            block["orthogonality"]["identical_support_pairs"]
            + block["orthogonality"]["true_subset_pairs"]
        )
    )
    total_ids = {a for members in block["family_map"].values() for a in members}
    assert total_ids == {a["action_id"] for a in non_a00}
    # deterministic freeze id
    assert block["freeze_id"] == content_id({k: v for k, v in block.items() if k != "freeze_id"})
    assert block["freeze_id"].startswith("sha256:")
    # registry now carries the frozen block
    assert design["action_set_frozen"]["freeze_id"] == block["freeze_id"]
