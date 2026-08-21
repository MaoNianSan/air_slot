"""Frozen Exp2 information-sufficiency variant registry."""

from __future__ import annotations

from exp.common.registry import VariantDefinition, VariantRegistry


EXP2A_POINT = "EXP2A_POINT"
EXP2A_MARGINAL = "EXP2A_MARGINAL"
EXP2A_JOINT = "EXP2A_JOINT"
EXP2B_SCALAR = "EXP2B_SCALAR"
EXP2B_3CHANNEL = "EXP2B_3CHANNEL"
EXP2B_7COMP = "EXP2B_7COMP"

# Compatibility names are intentionally aliases, never active protocol IDs.
EXP2A_COLLAPSED = EXP2A_POINT
EXP2B_CHANNEL = EXP2B_3CHANNEL
EXP2B_COMPONENT = EXP2B_7COMP

EXP2A_VARIANTS = (EXP2A_POINT, EXP2A_MARGINAL, EXP2A_JOINT)
EXP2B_VARIANTS = (EXP2B_SCALAR, EXP2B_3CHANNEL, EXP2B_7COMP)
EXP2_VARIANT_IDS = EXP2A_VARIANTS + EXP2B_VARIANTS

LEGACY_EXP2_VARIANT_ALIASES = {
    "EXP2A_COLLAPSED": EXP2A_POINT,
    "EXP2B_CHANNEL": EXP2B_3CHANNEL,
    "EXP2B_COMPONENT": EXP2B_7COMP,
}

EXP2_METRICS = (
    "STATE_REPRESENTATION_LINEAGE_PRESERVED",
    "CRPS",
    "BRIER",
    "CALIBRATION",
    "COVERAGE",
    "VARIOGRAM_SCORE",
    "TOP1_ACTION_DISAGREEMENT",
    "ACTION_FAMILY_COMPOSITION",
    "COMPLETE_REFERENCE_J_DIAGNOSTIC",
)


def normalize_variant_id(variant_id: str) -> str:
    value = LEGACY_EXP2_VARIANT_ALIASES.get(variant_id, variant_id)
    if value not in EXP2_VARIANT_IDS:
        raise KeyError(f"EXP2_VARIANT_UNKNOWN:{variant_id}")
    return value


def build_exp2_variant_registry() -> VariantRegistry:
    """Return metadata for representation-only paired comparisons."""
    shared = (
        "FULL_ADAPTIVE_M1_ARTIFACT",
        "M2_SEVEN_COMPONENT_SOURCE",
        "DIRECT_INFORMATION_PERMISSION",
        "ACTION_LIBRARY",
        "ACTION_AVAILABILITY",
        "SUPPORT_PROVENANCE_GATE",
        "DATASET_COHORT",
        "SEED",
    )
    definitions = (
        VariantDefinition(
            variant_id=EXP2A_POINT,
            description="One coherent weighted joint scenario selected from the frozen M1 artifact.",
            changed_factor="M1_UNCERTAINTY_REPRESENTATION_POINT",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="UNDER_REPRESENTATION_CONTRAST_NOT_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2A_MARGINAL,
            description="Primitive marginals retained while cross-target scenario alignment is broken.",
            changed_factor="M1_UNCERTAINTY_REPRESENTATION_MARGINAL",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="DEPENDENCE_ABLATION_NOT_WEAKER_PREDICTOR",
        ),
        VariantDefinition(
            variant_id=EXP2A_JOINT,
            description="Full aligned frozen scenarios retaining dependence and samplewise derived delay identity.",
            changed_factor="M1_UNCERTAINTY_REPRESENTATION_JOINT",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="COMPLETE_REPRESENTATION_REFERENCE_NOT_GROUND_TRUTH_ACTION",
        ),
        VariantDefinition(
            variant_id=EXP2B_SCALAR,
            description="Seven-component consequence representation coarsened to one total with train-frozen response coarsening.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_SCALAR",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="MECHANISM_COARSENING_CONTRAST_ONLY",
        ),
        VariantDefinition(
            variant_id=EXP2B_3CHANNEL,
            description="Seven components coarsened to Flight, Passenger, and Resource channels.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_3CHANNEL",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="MECHANISM_COARSENING_CONTRAST_ONLY",
        ),
        VariantDefinition(
            variant_id=EXP2B_7COMP,
            description="All seven frozen M2 consequence mechanisms retained through action evaluation.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_7COMP",
            fixed_factor=shared,
            allowed_metrics=EXP2_METRICS,
            claim_scope="COMPLETE_MECHANISM_REFERENCE_NOT_GROUND_TRUTH_ACTION",
        ),
    )
    return VariantRegistry(definitions)


EXP2_VARIANT_REGISTRY = build_exp2_variant_registry()


__all__ = [
    "EXP2A_COLLAPSED", "EXP2A_JOINT", "EXP2A_MARGINAL", "EXP2A_POINT",
    "EXP2A_VARIANTS", "EXP2B_3CHANNEL", "EXP2B_7COMP", "EXP2B_CHANNEL",
    "EXP2B_COMPONENT", "EXP2B_SCALAR", "EXP2B_VARIANTS", "EXP2_METRICS",
    "EXP2_VARIANT_IDS", "EXP2_VARIANT_REGISTRY", "LEGACY_EXP2_VARIANT_ALIASES",
    "build_exp2_variant_registry", "normalize_variant_id",
]
