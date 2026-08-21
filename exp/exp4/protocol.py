"""Exp4 adequacy protocol declarations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EVALUATION_LEAD_MINUTES = (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
MODEL_HORIZON_MINUTES = (0, 15, 60)


class PredictiveBaseline(str, Enum):
    HISTORICAL = "HISTORICAL"
    LIGHTGBM_FAST = "LIGHTGBM_FAST"
    RANDOM_FOREST = "RANDOM_FOREST"
    STATE_AWARE_FULL = "STATE_AWARE_FULL"


EXP4A_PREDICTIVE_ADEQUACY = "EXP4A_PREDICTIVE_ADEQUACY"
EXP4B_DECISION_OUTPUT_VALIDITY = "EXP4B_DECISION_OUTPUT_VALIDITY"
EXP4B_LLM_AUXILIARY_AUDIT = "EXP4B_LLM_AUXILIARY_AUDIT"
EXP4C_DATA1_DATA2_PORTABILITY = "EXP4C_DATA1_DATA2_PORTABILITY"
EXP4D_END_TO_END_RUNTIME = "EXP4D_END_TO_END_RUNTIME"
EXP4D_SHARED_STATE = "EXP4D_SHARED_STATE"
EXP4D_RECOMPUTED_STATE = "EXP4D_RECOMPUTED_STATE"
EXP4_VARIANTS = (
    EXP4A_PREDICTIVE_ADEQUACY, EXP4B_DECISION_OUTPUT_VALIDITY,
    EXP4B_LLM_AUXILIARY_AUDIT, EXP4C_DATA1_DATA2_PORTABILITY,
    EXP4D_END_TO_END_RUNTIME, EXP4D_SHARED_STATE, EXP4D_RECOMPUTED_STATE,
)

LEGACY_EXP4_VARIANTS = (
    "RISK_POLICY_SENSITIVITY", "NORMATIVE_VALUATION_SENSITIVITY",
    "SCENARIO_RESPONSE_SENSITIVITY", "ROLL_SENSITIVITY",
    "MONTE_CARLO_CONVERGENCE", "OPERATIONAL_BOUNDARY",
    "DATA1_PORTABILITY", "DEPLOYABILITY_STATE_AWARE_FAST",
)


def variant_definition(variant_id: str) -> dict:
    definitions = {
        EXP4A_PREDICTIVE_ADEQUACY: ("Exp4A", "predictive_adequacy_across_lead_time", ("M1_TARGETS", "SPLIT", "OBSERVATIONS")),
        EXP4B_DECISION_OUTPUT_VALIDITY: ("Exp4B", "decision_output_admissibility", ("M1", "M2", "M3", "M4", "hard_validity_rules")),
        EXP4B_LLM_AUXILIARY_AUDIT: ("Exp4B", "llm_auxiliary_audit", ("decision_output", "schema", "sample_contract")),
        EXP4C_DATA1_DATA2_PORTABILITY: ("Exp4C", "evidence_environment", ("semantic_support_contract", "split", "lead_time_intersection")),
        EXP4D_END_TO_END_RUNTIME: ("Exp4D", "end_to_end_runtime", ("pipeline", "hardware", "thread_settings")),
        EXP4D_SHARED_STATE: ("Exp4D", "shared_state_reuse_appendix_diagnostic", ("scientific_inputs", "outputs")),
        EXP4D_RECOMPUTED_STATE: ("Exp4D", "recomputed_state_appendix_diagnostic", ("scientific_inputs", "outputs")),
    }
    if variant_id not in definitions:
        if variant_id in LEGACY_EXP4_VARIANTS:
            return {"variant_id": variant_id, "claim_scope": "LEGACY_OR_APPENDIX_ONLY", "subexperiment": "LEGACY"}
        raise KeyError(f"EXP4_VARIANT_UNKNOWN:{variant_id}")
    subexperiment, changed_factor, fixed_factor = definitions[variant_id]
    return {
        "variant_id": variant_id, "subexperiment": subexperiment,
        "changed_factor": changed_factor, "fixed_factor": fixed_factor,
        "claim_scope": "SYSTEM_ADEQUACY_ONLY",
    }


@dataclass(frozen=True)
class Exp4Protocol:
    variant_id: str

    @property
    def definition(self) -> dict:
        return variant_definition(self.variant_id)


__all__ = [
    "EXP4A_PREDICTIVE_ADEQUACY", "EXP4B_DECISION_OUTPUT_VALIDITY",
    "EXP4B_LLM_AUXILIARY_AUDIT", "EXP4C_DATA1_DATA2_PORTABILITY",
    "EXP4D_END_TO_END_RUNTIME", "EXP4D_SHARED_STATE", "EXP4D_RECOMPUTED_STATE",
    "EVALUATION_LEAD_MINUTES", "MODEL_HORIZON_MINUTES", "PredictiveBaseline",
    "EXP4_VARIANTS", "LEGACY_EXP4_VARIANTS", "Exp4Protocol", "variant_definition",
]
