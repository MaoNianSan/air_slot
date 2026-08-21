"""Shared execution context and result construction for Exp1--Exp4.

The experiment packages own scientific transformations. This module only
carries frozen identities, execution tier, split discipline, and the common
result envelope used after a protocol has completed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.identity import content_id

from .result_schema import ExperimentResult, MetricObservation, SupportStatus


class ExecutionTier(str, Enum):
    FAST = "FAST"
    MIDDLE = "MIDDLE"
    FULL = "FULL"


class ExperimentContext(BaseModel):
    """One immutable binding for a paired experiment execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str = Field(min_length=1)
    split: str = Field(min_length=1)
    execution_tier: ExecutionTier
    cohort: tuple[dict[str, Any], ...] = ()
    seed: int
    pre_binding: dict[str, str] = Field(default_factory=dict)
    m1_artifact: str = "UNBOUND"
    m2_artifact: str = "UNBOUND"
    m3_bundle: str = "UNBOUND"
    m4_policy: str = "UNBOUND"
    model_hashes: dict[str, str] = Field(default_factory=dict)
    registry_hashes: dict[str, str] = Field(default_factory=dict)
    config_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    scenario_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    lineage: dict[str, Any] = Field(default_factory=dict)
    shared_gates: dict[str, str] = Field(default_factory=dict)
    final_test_access_count: int = Field(default=0, ge=0)
    paper_full_run: bool = False

    @model_validator(mode="after")
    def protect_current_execution_boundary(self):
        if self.final_test_access_count != 0:
            raise ValueError("EXPERIMENT_CONTEXT_FINAL_TEST_ACCESS_MUST_BE_ZERO")
        if self.paper_full_run:
            raise ValueError("EXPERIMENT_CONTEXT_PAPER_FULL_FORBIDDEN")
        if self.execution_tier is ExecutionTier.FULL and self.split.upper() == "FINAL_TEST":
            raise ValueError("EXPERIMENT_CONTEXT_FINAL_TEST_REQUIRES_SEPARATE_AUTHORIZATION")
        return self

    @property
    def episode_count(self) -> int:
        return len({str(row.get("episode_id")) for row in self.cohort if row.get("episode_id") is not None})

    @property
    def node_count(self) -> int:
        return len({
            (str(row.get("episode_id")), str(row.get("decision_node_id")))
            for row in self.cohort
            if row.get("episode_id") is not None and row.get("decision_node_id") is not None
        })

    @property
    def context_hash(self) -> str:
        return content_id(self.model_dump(mode="json"))


def fast_context(*, dataset_id: str, split: str, seed: int, experiment_id: str) -> ExperimentContext:
    """Return a source-free fixture context for a FAST contract run."""
    lineage = {
        "execution_scope": "FAST_CONTRACT_FIXTURE_ONLY",
        "experiment_id": experiment_id,
        "realized_outcomes_entered_inference": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    return ExperimentContext(
        dataset_id=dataset_id,
        split=split,
        execution_tier=ExecutionTier.FAST,
        seed=seed,
        pre_binding={"binding_status": "FAST_NO_RAW_DATA_ACCESS"},
        model_hashes={name: "UNBOUND_FAST" for name in ("PRE", "M1", "M2", "M3", "M4")},
        registry_hashes={"registry_manifest": "UNBOUND_FAST"},
        config_hash=content_id({"experiment": experiment_id, "tier": "FAST", "dataset": dataset_id, "split": split}),
        scenario_hash=content_id({"experiment": experiment_id, "fixture": "NO_SCENARIOS"}),
        lineage=lineage,
        shared_gates={"M1_POSITIVE_TAIL": "BLOCKED_UNFROZEN", "M4_MONETARY_MAPPING": "BLOCKED_UNFROZEN"},
    )


def build_context_result(*, context: ExperimentContext, experiment_id: str, variant_id: str,
                         metrics: dict[str, MetricObservation], support_status: SupportStatus,
                         runtime: dict[str, Any] | None = None,
                         provenance: dict[str, Any] | None = None) -> ExperimentResult:
    """Create one provenance-complete result without upgrading support."""
    return ExperimentResult(
        experiment_id=experiment_id,
        variant_id=variant_id,
        dataset_id=context.dataset_id,
        split=context.split,
        tier=context.execution_tier.value,
        episode_count=context.episode_count,
        node_count=context.node_count,
        seed=context.seed,
        timestamp=datetime.now(timezone.utc),
        model_versions=context.model_hashes or {"CHAIN": "UNBOUND"},
        model_hashes=context.model_hashes or {"CHAIN": "UNBOUND"},
        registry_hashes=context.registry_hashes or {"REGISTRY": "UNBOUND"},
        artifact_versions={"PRE_BINDING": content_id(context.pre_binding), "M1_ARTIFACT": context.m1_artifact,
                           "M2_ARTIFACT": context.m2_artifact, "M3_BUNDLE": context.m3_bundle,
                           "M4_POLICY": context.m4_policy},
        scenario_hash=context.scenario_hash,
        config_hash=context.config_hash,
        metrics=metrics,
        support_status=support_status,
        lineage={**context.lineage, "context_hash": context.context_hash, "shared_gates": context.shared_gates},
        runtime=runtime or {},
        final_test_access_count=context.final_test_access_count,
        provenance={"paper_result": False, "FINAL_TEST_ACCESS_COUNT": context.final_test_access_count,
                    "PAPER_FULL_RUN": context.paper_full_run, **(provenance or {})},
    )


__all__ = ["ExecutionTier", "ExperimentContext", "build_context_result", "fast_context"]
