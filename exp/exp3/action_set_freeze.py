"""M3 minimal executable action-set freeze (A-SET, decision 2026-08-24 R1).

Freeze criteria (Path-B supplement section 3, 2026-08-24; semantics tightened
by decision R1):
1. COVERAGE          - every mechanism family has >= 1 executable action
2. ORTHOGONALITY     - family-level: the check reports whether the family
                       support sets (union of member affected components)
                       are mutually non-contained; within-family identical /
                       subset pairs are marked PARAMETRIC_VARIANTS_SAME_MECHANISM
                       and retained for human review (nothing is dropped
                       silently).  No action-level orthogonality claim.
3. INTERPRETABILITY  - every action carries a mechanism formula, LOW/BASE/HIGH
                       sensitivity band, and literature DOI provenance

The block is ASSUMPTION_GROUNDED: executable responses enter the
SCENARIO/CONDITIONAL lane only; the FORMAL/authoritative lane stays A00-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model.common.identity import content_id


REGISTRY = Path("registries/m3_v2_action_response_design.json")

# Registry action_family -> canonical freeze family id.
FAMILY_MAP: dict[str, tuple[str, ...]] = {
    "AIRCRAFT_SWAP": ("aircraft_recovery", "ground_recovery"),
    "CREW_SWAP": ("crew_recovery",),
    "HOLD": ("timing", "capacity_coordination"),
    "PROPAGATION_BUFFER": ("flight_execution",),
    "PASSENGER_REASSIGNMENT": (
        "passenger_recovery", "passenger_service", "timing_passenger_coordination",
    ),
    "NETWORK_EXTREME": ("extreme_local_network",),
}

SAFETY = {
    "M1_TRAINING_RUNS": 0,
    "TUNING_RUNS": 0,
    "EXP2_RUNS": 0,
    "EXP3_RUNS": 0,
    "FINAL_TEST_ACCESS_COUNT": 0,
    "PAPER_FULL_RUN": False,
    "FULL": False,
}


def family_of(action: dict[str, Any]) -> str | None:
    for family, members in FAMILY_MAP.items():
        if action.get("action_family") in members:
            return family
    return None


def mechanism_signature(action: dict[str, Any]) -> str:
    grounded = action.get("assumption_grounded") or {}
    return str(grounded.get("mechanism", ""))


def support_set(action: dict[str, Any]) -> frozenset[str]:
    return frozenset(action.get("affected_components", []))


def family_support_sets(actions: list[dict[str, Any]]) -> dict[str, frozenset[str]]:
    """Union of member support sets per freeze family (family-level support)."""
    supports: dict[str, set[str]] = {}
    for action in actions:
        family = family_of(action)
        if family is None:
            continue
        supports.setdefault(family, set()).update(support_set(action))
    return {family: frozenset(components) for family, components in supports.items()}


def family_orthogonality_table(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Family-level support-set containment check across the freeze families.

    Decision R1: orthogonality is claimed only at family level (6 family
    support sets mutually non-contained).  Nested families are documented
    with an explicit reason instead of being silently dropped or relabeled.
    """
    supports = family_support_sets(actions)
    families = sorted(supports)
    pairwise: list[dict[str, Any]] = []
    violating: list[dict[str, Any]] = []
    for index, left in enumerate(families):
        for right in families[index + 1:]:
            left_support, right_support = supports[left], supports[right]
            entry = {
                "family_a": left,
                "family_b": right,
                "support_a": sorted(left_support),
                "support_b": sorted(right_support),
            }
            if left_support < right_support:
                entry.update({
                    "containment": "FAMILY_A_STRICT_SUBSET",
                    "subset_family": left,
                    "superset_family": right,
                    "reason": (
                        "FAMILY_LEVEL_NESTED_SUPPORT; family-level mutual "
                        "non-containment does not hold for this pair; "
                        "documented for human review, no silent drop"
                    ),
                })
                violating.append(entry)
            elif right_support < left_support:
                entry.update({
                    "containment": "FAMILY_B_STRICT_SUBSET",
                    "subset_family": right,
                    "superset_family": left,
                    "reason": (
                        "FAMILY_LEVEL_NESTED_SUPPORT; family-level mutual "
                        "non-containment does not hold for this pair; "
                        "documented for human review, no silent drop"
                    ),
                })
                violating.append(entry)
            elif left_support == right_support:
                entry.update({
                    "containment": "IDENTICAL_FAMILY_SUPPORT",
                    "reason": (
                        "IDENTICAL_FAMILY_SUPPORT; family-level mutual "
                        "non-containment does not hold for this pair; "
                        "documented for human review, no silent drop"
                    ),
                })
                violating.append(entry)
            else:
                entry.update({
                    "containment": "MUTUALLY_NON_CONTAINED",
                    "reason": (
                        "MUTUALLY_NON_CONTAINED; neither family support set "
                        "contains the other"
                    ),
                })
            pairwise.append(entry)
    return {
        "schema_version": "M3_ACTION_FAMILY_ORTHOGONALITY_V1",
        "status": (
            "MUTUALLY_NON_CONTAINED"
            if not violating
            else "NESTED_SUPPORT_DOCUMENTED"
        ),
        "family_support_sets": {
            family: sorted(components) for family, components in sorted(supports.items())
        },
        "pairwise": pairwise,
        "violating_pairs": violating,
    }


def orthogonality_check_table(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Within-family pairwise containment, marked as parametric variants (R1)."""
    subset_pairs: list[dict[str, Any]] = []
    identical_pairs: list[dict[str, Any]] = []
    by_family: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        by_family.setdefault(family_of(action) or "UNMAPPED", []).append(action)
    for family, members in sorted(by_family.items()):
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                left_id, right_id = left["action_id"], right["action_id"]
                left_support, right_support = support_set(left), support_set(right)
                if left_support == right_support:
                    identical_pairs.append({
                        "family": family,
                        "action_a": left_id,
                        "action_b": right_id,
                        "shared_mechanism": mechanism_signature(left),
                        "retained": True,
                        "variant_label": "PARAMETRIC_VARIANTS_SAME_MECHANISM",
                        "reason": (
                            "IDENTICAL_SUPPORT_AND_MECHANISM; registry distinguishes "
                            "the pair only by action_id/parameterization; retained for "
                            "human review of the parameterization difference; not "
                            "evidence for action-level orthogonality"
                        ),
                    })
                elif left_support < right_support:
                    subset_pairs.append({
                        "family": family,
                        "superset": right_id,
                        "subset": left_id,
                        "shared_mechanism": mechanism_signature(left),
                        "retained": True,
                        "variant_label": "PARAMETRIC_VARIANTS_SAME_MECHANISM",
                        "reason": (
                            "TRUE_SUBSET_SUPPORT; variant parameterization differs "
                            "by registry action_id; retained and documented, no "
                            "silent deduplication; not evidence for action-level "
                            "orthogonality"
                        ),
                    })
                elif right_support < left_support:
                    subset_pairs.append({
                        "family": family,
                        "superset": left_id,
                        "subset": right_id,
                        "shared_mechanism": mechanism_signature(left),
                        "retained": True,
                        "variant_label": "PARAMETRIC_VARIANTS_SAME_MECHANISM",
                        "reason": (
                            "TRUE_SUBSET_SUPPORT; variant parameterization differs "
                            "by registry action_id; retained and documented, no "
                            "silent deduplication; not evidence for action-level "
                            "orthogonality"
                        ),
                    })
    return {
        "schema_version": "M3_ACTION_SET_ORTHOGONALITY_CHECK_V1",
        "true_subset_pairs": subset_pairs,
        "identical_support_pairs": identical_pairs,
        "family_orthogonality": family_orthogonality_table(actions),
        "unmapped_actions": [
            action["action_id"] for action in actions if family_of(action) is None
        ],
    }


def build_action_set_frozen(design: dict[str, Any]) -> dict[str, Any]:
    """Build the A-SET freeze block from the M3 V2 action-response design."""
    non_a00 = [action for action in design["responses"] if action.get("action_id") != "A00"]
    if not non_a00:
        raise RuntimeError("M3_ACTION_SET_EMPTY_NON_A00")
    if design.get("formal_support_upgrade") is not False:
        raise RuntimeError("M3_ACTION_SET_FORMAL_UPGRADE_FORBIDDEN")
    if design.get("non_a00_v2_execution_enabled") is not True:
        raise RuntimeError("M3_ACTION_SET_NON_A00_EXECUTION_DISABLED")

    family_members: dict[str, list[str]] = {}
    coverage: dict[str, str] = {}
    for family in sorted(FAMILY_MAP):
        members = [a for a in non_a00 if family_of(a) == family]
        family_members[family] = [a["action_id"] for a in members]
        coverage[family] = (
            "EXECUTABLE"
            if any(a.get("executable_v2") is True for a in members)
            else ("REGISTERED_BUT_NOT_EXECUTABLE" if members else "NO_REGISTERED_ACTION")
        )

    interpretability_missing = [
        action["action_id"] for action in non_a00
        if not (
            (action.get("assumption_grounded") or {}).get("formula")
            and (action.get("assumption_grounded") or {}).get("sensitivity_band")
            and (action.get("assumption_grounded") or {}).get("literature")
        )
    ]

    block = {
        "schema_version": "M3_ACTION_SET_FROZEN_V1",
        "status": "COMPLETED_ASSUMPTION_GROUNDED_ACTION_SET_FROZEN",
        "criteria": ["COVERAGE", "ORTHOGONALITY", "INTERPRETABILITY"],
        "formal_lane": "A00_ONLY",
        "scenario_conditional_lane": "ALL_22_NON_A00",
        "family_map": family_members,
        "coverage": coverage,
        "interpretability": {
            "status": "PASS" if not interpretability_missing else "MISSING",
            "missing_action_ids": interpretability_missing,
        },
        "orthogonality": orthogonality_check_table(non_a00),
        "safety": dict(SAFETY),
    }
    block["freeze_id"] = content_id({
        key: value for key, value in block.items() if key != "freeze_id"
    })
    return block


def write_registry_block(root: Path | None = None) -> dict[str, Any]:
    root = (root or Path.cwd()).resolve()
    registry_path = root / REGISTRY
    design = json.loads(registry_path.read_text(encoding="utf-8"))
    block = build_action_set_frozen(design)
    design["action_set_frozen"] = block
    rendered = json.dumps(design, indent=2, sort_keys=True) + "\n"
    temporary = registry_path.with_suffix(".json.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(registry_path)
    return block


if __name__ == "__main__":
    result = write_registry_block()
    print(json.dumps({
        "status": result["status"],
        "freeze_id": result["freeze_id"],
        "coverage": result["coverage"],
        "subset_pairs": len(result["orthogonality"]["true_subset_pairs"]),
        "identical_pairs": len(result["orthogonality"]["identical_support_pairs"]),
    }, sort_keys=True))
