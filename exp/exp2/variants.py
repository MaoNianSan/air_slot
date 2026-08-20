"""Frozen Exp2 representation variant registry."""

from __future__ import annotations

from exp.common.registry import VariantDefinition, VariantRegistry


EXP2A_COLLAPSED = "EXP2A_COLLAPSED"
EXP2A_MARGINAL = "EXP2A_MARGINAL"
EXP2A_JOINT = "EXP2A_JOINT"
EXP2B_SCALAR = "EXP2B_SCALAR"
EXP2B_CHANNEL = "EXP2B_CHANNEL"
EXP2B_COMPONENT = "EXP2B_COMPONENT"

EXP2A_VARIANTS = (EXP2A_COLLAPSED, EXP2A_MARGINAL, EXP2A_JOINT)
EXP2B_VARIANTS = (EXP2B_SCALAR, EXP2B_CHANNEL, EXP2B_COMPONENT)
EXP2_VARIANT_IDS = EXP2A_VARIANTS + EXP2B_VARIANTS

EXP2_METRICS = (
    "STATE_CRPS",
    "DECISION_ACTION_DISAGREEMENT",
    "DECISION_RANKING_CHANGE",
    "DECISION_RISK_DIFFERENCE",
    "DECISION_CVAR_DIFFERENCE",
)


def build_exp2_variant_registry() -> VariantRegistry:
    """Return the immutable metadata surface for the six frozen contrasts."""

    shared_fixed = (
        "M1_MODEL_AND_CALIBRATION_ARTIFACT",
        "M2_CONSEQUENCE_ARTIFACT",
        "M3_ACTION_SET",
        "M3_RESPONSE_REGISTRY",
        "M4_MONETARY_MAPPING",
        "M4_RISK_POLICY",
        "DATASET_COHORT",
        "RANDOM_SEED",
    )
    definitions = (
        VariantDefinition(
            variant_id=EXP2A_COLLAPSED,
            description="Collapse the frozen joint M1 scenario distribution to its weighted deterministic expectation.",
            changed_factor="M1_SCENARIO_INFORMATION_STRUCTURE_COLLAPSED",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="INFORMATION_SUFFICIENCY_CONTRAST_ONLY_NO_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2A_MARGINAL,
            description="Preserve each weighted M1 marginal while removing cross-variable scenario association.",
            changed_factor="M1_SCENARIO_INFORMATION_STRUCTURE_MARGINAL",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="INFORMATION_SUFFICIENCY_CONTRAST_ONLY_NO_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2A_JOINT,
            description="Preserve the frozen weighted M1 joint scenarios without transformation.",
            changed_factor="M1_SCENARIO_INFORMATION_STRUCTURE_JOINT",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="REFERENCE_REPRESENTATION_ONLY_NO_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2B_SCALAR,
            description="Represent each frozen M2 consequence as one scalar aggregate with explicit support propagation.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_SCALAR",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="CONSEQUENCE_RESOLUTION_CONTRAST_ONLY_NO_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2B_CHANNEL,
            description="Aggregate the frozen seven M2 components into Flight, Passenger, and Resource channels.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_CHANNEL",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="CONSEQUENCE_RESOLUTION_CONTRAST_ONLY_NO_MODEL_SUPERIORITY",
        ),
        VariantDefinition(
            variant_id=EXP2B_COMPONENT,
            description="Preserve all seven frozen M2 consequence components and their support lineage.",
            changed_factor="M2_CONSEQUENCE_RESOLUTION_COMPONENT",
            fixed_factor=shared_fixed,
            allowed_metrics=EXP2_METRICS,
            claim_scope="REFERENCE_REPRESENTATION_ONLY_NO_MODEL_SUPERIORITY",
        ),
    )
    return VariantRegistry(definitions)


EXP2_VARIANT_REGISTRY = build_exp2_variant_registry()


__all__ = [
    "EXP2A_COLLAPSED",
    "EXP2A_JOINT",
    "EXP2A_MARGINAL",
    "EXP2A_VARIANTS",
    "EXP2B_CHANNEL",
    "EXP2B_COMPONENT",
    "EXP2B_SCALAR",
    "EXP2B_VARIANTS",
    "EXP2_METRICS",
    "EXP2_VARIANT_IDS",
    "EXP2_VARIANT_REGISTRY",
    "build_exp2_variant_registry",
]
