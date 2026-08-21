"""Exp1 information-role variants.

Only the two frozen questions are active: direct downstream reuse and
history-mediated state formation. Legacy warning/context variants remain
available as explicitly labelled compatibility aliases only.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any

from model.common.errors import ContractError
from model.common.identity import content_id


class Exp1Variant(str, Enum):
    EXP1A_NO_DIRECT_REUSE = "EXP1A_NO_DIRECT_REUSE"
    EXP1A_FULL = "EXP1A_FULL"
    EXP1B_CURRENT = "EXP1B_CURRENT"
    EXP1B_FIXED_HISTORY_30 = "EXP1B_FIXED_HISTORY_30"
    EXP1B_ADAPTIVE_HISTORY = "EXP1B_ADAPTIVE_HISTORY"


EXP1A_VARIANTS = (Exp1Variant.EXP1A_NO_DIRECT_REUSE.value, Exp1Variant.EXP1A_FULL.value)
EXP1B_VARIANTS = (
    Exp1Variant.EXP1B_CURRENT.value,
    Exp1Variant.EXP1B_FIXED_HISTORY_30.value,
    Exp1Variant.EXP1B_ADAPTIVE_HISTORY.value,
)
EXP1_VARIANTS = EXP1A_VARIANTS + EXP1B_VARIANTS

LEGACY_EXP1_VARIANTS = (
    "empirical", "current", "fixed_history", "adaptive_history",
    "independent_heads", "leakage_diagnostic", "EXP1A_CONTEXT_NEUTRALIZED",
    "EXP1C_SHARED_STATE", "EXP1C_RECOMPUTED_STATE",
)


def variant_definition(variant_id: str) -> dict[str, Any]:
    definitions = {
        Exp1Variant.EXP1A_NO_DIRECT_REUSE.value: {
            "subexperiment": "Exp1A", "changed_factor": "direct_current_information_reuse",
            "fixed_factor": ("PRE", "M1", "M2", "M3", "M4", "action_library", "support_rules"),
            "claim_scope": "INFORMATION_ROLE_NECESSITY_ONLY",
        },
        Exp1Variant.EXP1A_FULL.value: {
            "subexperiment": "Exp1A", "changed_factor": "direct_current_information_reuse",
            "fixed_factor": ("PRE", "M1", "M2", "M3", "M4", "action_library", "support_rules"),
            "claim_scope": "INFORMATION_ROLE_REFERENCE_ONLY",
        },
        Exp1Variant.EXP1B_CURRENT.value: {
            "subexperiment": "Exp1B", "changed_factor": "history_representation_current",
            "fixed_factor": ("M1_architecture", "M1_heads", "targets", "calibration", "M2", "M3", "M4"),
            "claim_scope": "HISTORY_DEPENDENCE_ONLY",
        },
        Exp1Variant.EXP1B_FIXED_HISTORY_30.value: {
            "subexperiment": "Exp1B", "changed_factor": "history_representation_fixed_30_minutes",
            "fixed_factor": ("M1_architecture", "M1_heads", "targets", "calibration", "M2", "M3", "M4"),
            "claim_scope": "HISTORY_DEPENDENCE_SENSITIVITY_ONLY",
        },
        Exp1Variant.EXP1B_ADAPTIVE_HISTORY.value: {
            "subexperiment": "Exp1B", "changed_factor": "history_representation_adaptive",
            "fixed_factor": ("M1_architecture", "M1_heads", "targets", "calibration", "M2", "M3", "M4"),
            "claim_scope": "HISTORY_DEPENDENCE_REFERENCE_ONLY",
        },
    }
    try:
        return {"variant_id": variant_id, **definitions[variant_id]}
    except KeyError as exc:
        raise ContractError("EXP1_VARIANT_UNKNOWN") from exc


def information_mask(variant: str) -> dict[str, str]:
    """Field-level direct-reuse contract for Exp1A."""
    if variant == Exp1Variant.EXP1A_FULL.value:
        return {
            "baseline_consequence": "DIRECT_REUSE_ALLOWED",
            "aligned_scenario_id_weight": "DIRECT_REUSE_ALLOWED",
            "action_identity": "STRUCTURALLY_REQUIRED",
            "minimal_actionability_facts": "STRUCTURALLY_REQUIRED",
            "execution_window_facts": "STRUCTURALLY_REQUIRED",
            "support_provenance": "STRUCTURALLY_REQUIRED",
            "upstream_hidden_history": "DIRECT_REUSE_ALLOWED",
            "raw_weather_context": "DIRECT_REUSE_ALLOWED",
            "realized_outcomes": "BLOCKED",
            "future_information": "BLOCKED",
        }
    if variant == Exp1Variant.EXP1A_NO_DIRECT_REUSE.value:
        return {
            "baseline_consequence": "DIRECT_REUSE_ALLOWED",
            "aligned_scenario_id_weight": "DIRECT_REUSE_ALLOWED",
            "action_identity": "STRUCTURALLY_REQUIRED",
            "minimal_actionability_facts": "STRUCTURALLY_REQUIRED",
            "execution_window_facts": "STRUCTURALLY_REQUIRED",
            "support_provenance": "STRUCTURALLY_REQUIRED",
            "upstream_hidden_history": "BLOCKED",
            "raw_weather_context": "BLOCKED",
            "realized_outcomes": "BLOCKED",
            "future_information": "BLOCKED",
        }
    raise ContractError("EXP1_INFORMATION_MASK_ONLY_APPLIES_TO_EXP1A")


def construct_exp1_variant(formal_artifact: dict, variant: str) -> dict:
    """Copy-isolated compatibility transformation for old callers."""
    aliases = {
        "current": Exp1Variant.EXP1B_CURRENT.value,
        "fixed_history": Exp1Variant.EXP1B_FIXED_HISTORY_30.value,
        "adaptive_history": Exp1Variant.EXP1B_ADAPTIVE_HISTORY.value,
        "EXP1A_FULL": Exp1Variant.EXP1A_FULL.value,
        "EXP1A_NO_DIRECT_REUSE": Exp1Variant.EXP1A_NO_DIRECT_REUSE.value,
    }
    canonical = aliases.get(variant, variant)
    if canonical not in EXP1_VARIANTS and variant not in LEGACY_EXP1_VARIANTS:
        raise ContractError("EXP1_VARIANT_UNKNOWN")
    before = content_id(formal_artifact)
    transformed = deepcopy(formal_artifact)
    transformed["evaluation_variant"] = variant
    transformed["protocol_variant"] = canonical
    transformed["variant_definition"] = variant_definition(canonical) if canonical in EXP1_VARIANTS else {
        "variant_id": canonical, "claim_scope": "LEGACY_OR_APPENDIX_ONLY"
    }
    transformed["information_mask"] = information_mask(canonical) if canonical in EXP1A_VARIANTS else None
    transformed["headline"] = canonical in EXP1_VARIANTS
    transformed["legacy_or_appendix_only"] = canonical not in EXP1_VARIANTS
    if content_id(formal_artifact) != before:
        raise ContractError("EXP1_MUTATED_FORMAL_ARTIFACT")
    return transformed


__all__ = ["EXP1A_VARIANTS", "EXP1B_VARIANTS", "EXP1_VARIANTS", "Exp1Variant",
           "LEGACY_EXP1_VARIANTS", "construct_exp1_variant", "information_mask", "variant_definition"]
