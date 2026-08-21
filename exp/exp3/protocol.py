"""Exp3 temporal/process protocol declarations."""

from __future__ import annotations

from dataclasses import dataclass


EXP3A_ONE_SHOT = "EXP3A_ONE_SHOT"
EXP3A_ROLLING = "EXP3A_ROLLING"
EXP3B_SYNC = "EXP3B_SYNC"
EXP3B_STATE_LAG_5 = "EXP3B_STATE_LAG_5"
EXP3B_STATE_LAG_10 = "EXP3B_STATE_LAG_10"
EXP3_VARIANTS = (
    EXP3A_ONE_SHOT, EXP3A_ROLLING, EXP3B_SYNC, EXP3B_STATE_LAG_5, EXP3B_STATE_LAG_10,
)

LEGACY_EXP3_VARIANTS = (
    "FULL_CONTRACT", "NO_EVIDENCE_DISTINCTION", "NO_MATERIAL_COVERAGE_GATE",
    "NO_INDUCED_CONSEQUENCE", "RISK_NEUTRAL",
)


def variant_definition(variant_id: str) -> dict:
    definitions = {
        EXP3A_ONE_SHOT: ("Exp3A", "recommendation_refresh_one_shot", ("PRE", "M1", "M2", "M3", "M4", "action_set")),
        EXP3A_ROLLING: ("Exp3A", "recommendation_refresh_rolling", ("PRE", "M1", "M2", "M3", "M4", "action_set")),
        EXP3B_SYNC: ("Exp3B", "state_vintage_current", ("current_direct_information", "action_set", "M1", "M2", "M3", "M4")),
        EXP3B_STATE_LAG_5: ("Exp3B", "state_vintage_lag_5", ("current_direct_information", "action_set", "M1", "M2", "M3", "M4")),
        EXP3B_STATE_LAG_10: ("Exp3B", "state_vintage_lag_10", ("current_direct_information", "action_set", "M1", "M2", "M3", "M4")),
    }
    if variant_id not in definitions:
        if variant_id in LEGACY_EXP3_VARIANTS:
            return {"variant_id": variant_id, "claim_scope": "LEGACY_OR_APPENDIX_ONLY", "subexperiment": "LEGACY"}
        raise KeyError(f"EXP3_VARIANT_UNKNOWN:{variant_id}")
    subexperiment, changed_factor, fixed_factor = definitions[variant_id]
    return {
        "variant_id": variant_id, "subexperiment": subexperiment,
        "changed_factor": changed_factor, "fixed_factor": fixed_factor,
        "claim_scope": "TEMPORAL_PROCESS_ONLY",
    }


@dataclass(frozen=True)
class Exp3Protocol:
    variant_id: str

    @property
    def definition(self) -> dict:
        return variant_definition(self.variant_id)


__all__ = [
    "EXP3A_ONE_SHOT", "EXP3A_ROLLING", "EXP3B_SYNC", "EXP3B_STATE_LAG_5",
    "EXP3B_STATE_LAG_10", "EXP3_VARIANTS", "LEGACY_EXP3_VARIANTS",
    "Exp3Protocol", "variant_definition",
]
