"""Auditable Exp1--Exp4 protocol objects.

These contracts define the executable comparison surface without silently
launching formal paper runs.  A caller must provide the frozen source artifact,
split, and metrics; this module only validates ownership and safety gates.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import Field, model_validator

from .contracts import FrozenModel, content_hash


EXP1_VARIANTS = (
    "EXP1A_NO_DIRECT_REUSE",
    "EXP1A_FULL",
    "EXP1B_CURRENT",
    "EXP1B_FIXED_HISTORY",
    "EXP1B_ADAPTIVE_HISTORY",
)
EXP2_VARIANTS = (
    "EXP2A_POINT",
    "EXP2A_MARGINAL",
    "EXP2A_JOINT",
    "EXP2B_SCALAR",
    "EXP2B_3CHANNEL",
    "EXP2B_7COMP",
)
EXP3_VARIANTS = (
    "EXP3A_ONE_SHOT",
    "EXP3A_ROLLING",
    "EXP3B_SYNC",
    "EXP3B_STATE_LAG_5",
    "EXP3B_STATE_LAG_10",
)
EXP4_VARIANTS = (
    "EXP4A_PREDICTIVE_ADEQUACY",
    "EXP4B_DECISION_OUTPUT_VALIDITY",
    "EXP4C_DATA1_DATA2_PORTABILITY",
    "EXP4D_END_TO_END_RUNTIME",
)
EXP4_DATA1_RUN_ACCEPTABILITY = "EXP4_DATA1_RUN_ACCEPTABILITY"


class ExperimentStage(str, Enum):
    EXP1 = "EXP1"
    EXP2 = "EXP2"
    EXP3 = "EXP3"
    EXP4 = "EXP4"


class SafetyState(FrozenModel):
    final_test_access_count: int = Field(default=0, ge=0)
    paper_full_run: bool = False
    authoritative_ranking: bool = False
    formal_execution_authorized: bool = False

    @model_validator(mode="after")
    def development_gate(self):
        if self.final_test_access_count != 0:
            raise ValueError("EXPERIMENT_FINAL_TEST_ACCESS_MUST_BE_ZERO")
        if self.paper_full_run:
            raise ValueError("EXPERIMENT_PAPER_FULL_RUN_DISABLED")
        if self.formal_execution_authorized:
            raise ValueError("FORMAL_EXECUTION_REQUIRES_EXTERNAL_HUMAN_GATE")
        return self


class ExperimentManifest(FrozenModel):
    stage: ExperimentStage
    variant: str = Field(min_length=1)
    variant_owner: str = Field(min_length=1)
    claim_scope: str = Field(min_length=1)
    source_artifact_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    split: str = Field(min_length=1)
    seed: int
    provenance: tuple[str, ...] = Field(min_length=1)
    safety: SafetyState = SafetyState()
    manifest_hash: str | None = None

    @model_validator(mode="after")
    def validate_variant(self):
        variants = {
            ExperimentStage.EXP1: EXP1_VARIANTS,
            ExperimentStage.EXP2: EXP2_VARIANTS,
            ExperimentStage.EXP3: EXP3_VARIANTS,
            ExperimentStage.EXP4: (*EXP4_VARIANTS, EXP4_DATA1_RUN_ACCEPTABILITY),
        }[self.stage]
        if self.variant not in variants:
            raise ValueError(f"UNKNOWN_{self.stage.value}_VARIANT:{self.variant}")
        expected = content_hash(self.model_dump(mode="json", exclude={"manifest_hash"}))
        if self.manifest_hash is not None and self.manifest_hash != expected:
            raise ValueError("EXPERIMENT_MANIFEST_HASH_MISMATCH")
        return self

    @property
    def hash(self) -> str:
        return content_hash(self.model_dump(mode="json", exclude={"manifest_hash"}))


VARIANT_OWNERS = {
    **{variant: "information_and_history" for variant in EXP1_VARIANTS},
    **{variant: "consequence_and_representation" for variant in EXP2_VARIANTS},
    **{variant: "rolling_decision_process" for variant in EXP3_VARIANTS},
    **{variant: "performance_efficiency_generalization" for variant in EXP4_VARIANTS},
    EXP4_DATA1_RUN_ACCEPTABILITY: "data1_bounded_execution_and_applicability",
}


VARIANT_CLAIM_SCOPES = {
    **{variant: "necessity_of_global_information_and_history_dependency" for variant in EXP1_VARIANTS},
    **{variant: "necessity_of_consequence_and_risk_representation" for variant in EXP2_VARIANTS},
    **{variant: "sequential_decision_chain_consistency_under_scenario_assumptions" for variant in EXP3_VARIANTS},
    **{variant: "predictive_adequacy_validity_portability_or_runtime" for variant in EXP4_VARIANTS},
    EXP4_DATA1_RUN_ACCEPTABILITY: "data1_bounded_execution_and_typed_applicability_only",
}


def build_experiment_manifest(
    *,
    stage: ExperimentStage | str,
    variant: str,
    source_artifact: Mapping[str, Any],
    split: str,
    seed: int,
    provenance: tuple[str, ...] = ("AIR_SLOT_EXP_PROGRAMMING_WORKFLOW",),
) -> ExperimentManifest:
    stage_enum = ExperimentStage(stage)
    if variant not in VARIANT_OWNERS or variant not in {
        *EXP1_VARIANTS,
        *EXP2_VARIANTS,
        *EXP3_VARIANTS,
        *EXP4_VARIANTS,
        EXP4_DATA1_RUN_ACCEPTABILITY,
    }:
        raise ValueError(f"UNKNOWN_EXPERIMENT_VARIANT:{variant}")
    return ExperimentManifest(
        stage=stage_enum,
        variant=variant,
        variant_owner=VARIANT_OWNERS[variant],
        claim_scope=VARIANT_CLAIM_SCOPES[variant],
        source_artifact_hash=content_hash(source_artifact),
        split=split,
        seed=seed,
        provenance=provenance,
    )


def validate_representation_isolation(*, variant: str, source_payload: Mapping[str, Any]) -> None:
    """Exp2 coarse variants may not inspect hidden fine-grained composition."""
    if variant in {"EXP2B_SCALAR", "EXP2B_3CHANNEL"} and "hidden_7_component_values" in source_payload:
        raise ValueError("EXP2_COARSENED_VARIANT_HIDDEN_7COMPONENT_LEAK")


class Data1Acceptance(FrozenModel):
    """Bounded Data1 execution gate, not a predictive-performance claim."""

    dataset_id: str = "data1_2019"
    rows_read: int = Field(ge=0)
    canonicalization_pass: bool
    raw_unchanged: bool
    contract_tests_passed: int = Field(ge=0)
    unsupported_semantics_explicit: bool
    m1_predictive_label_path_available: bool = False
    final_test_access_count: int = Field(default=0, ge=0)
    paper_full_run: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        if self.dataset_id != "data1_2019":
            raise ValueError("EXP4_DATA1_ACCEPTANCE_DATASET_MISMATCH")
        if self.final_test_access_count != 0:
            raise ValueError("EXP4_DATA1_ACCEPTANCE_FINAL_TEST_NONZERO")
        if self.paper_full_run:
            raise ValueError("EXP4_DATA1_ACCEPTANCE_PAPER_FULL_FORBIDDEN")
        if self.m1_predictive_label_path_available:
            raise ValueError("EXP4_DATA1_M1_LABEL_PATH_MUST_REMAIN_UNAVAILABLE")
        return self

    @property
    def status(self) -> str:
        return (
            "PASS_BOUNDED_DATA1_EXECUTION"
            if self.rows_read > 0
            and self.canonicalization_pass
            and self.raw_unchanged
            and self.contract_tests_passed > 0
            and self.unsupported_semantics_explicit
            else "BLOCKED_DATA1_BOUNDED_ACCEPTANCE"
        )

    @property
    def claim_scope(self) -> str:
        return "DATA1_ADAPTER_PRE_TYPED_APPLICABILITY_NOT_PREDICTIVE_ACCURACY"


def build_data1_acceptance_report() -> dict[str, Any]:
    """Create the observed bounded Data1 development report."""
    acceptance = Data1Acceptance(
        rows_read=2,
        canonicalization_pass=True,
        raw_unchanged=True,
        contract_tests_passed=5,
        unsupported_semantics_explicit=True,
    )
    return {
        "schema_version": "AIR_SLOT_EXP4_DATA1_BOUNDED_ACCEPTANCE_V1",
        "status": acceptance.status,
        "dataset_id": acceptance.dataset_id,
        "claim_scope": acceptance.claim_scope,
        "observations": {
            "data1_rows_read": acceptance.rows_read,
            "data1_canonicalization": acceptance.canonicalization_pass,
            "raw_input_unchanged": acceptance.raw_unchanged,
            "data1_contract_tests_passed": acceptance.contract_tests_passed,
            "unsupported_semantics_explicit": acceptance.unsupported_semantics_explicit,
            "m1_predictive_label_path": "UNAVAILABLE_BY_CONTRACT",
        },
        "effect_interpretation": "PRE_ADAPTER_AND_TYPED_APPLICABILITY_ONLY",
        "not_claimed": [
            "predictive MAE/CRPS on Data1",
            "external validation equivalence",
            "causal recovery effectiveness",
            "real monetary loss",
        ],
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }


def development_protocol_report(manifests: tuple[ExperimentManifest, ...]) -> dict[str, Any]:
    """Return a serializable readiness report; does not run formal experiments."""
    if any(item.safety.final_test_access_count != 0 or item.safety.paper_full_run for item in manifests):
        raise ValueError("EXPERIMENT_SAFETY_STATE_INVALID")
    return {
        "workflow": "W0-W7",
        "formal_execution": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "manifests": [
            {
                "stage": item.stage.value,
                "variant": item.variant,
                "variant_owner": item.variant_owner,
                "claim_scope": item.claim_scope,
                "manifest_hash": item.hash,
            }
            for item in manifests
        ],
    }


__all__ = [
    "EXP1_VARIANTS",
    "EXP2_VARIANTS",
    "EXP3_VARIANTS",
    "EXP4_VARIANTS",
    "EXP4_DATA1_RUN_ACCEPTABILITY",
    "Data1Acceptance",
    "ExperimentManifest",
    "ExperimentStage",
    "SafetyState",
    "build_experiment_manifest",
    "development_protocol_report",
    "validate_representation_isolation",
    "build_data1_acceptance_report",
]
