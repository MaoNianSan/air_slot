"""Shared execution context and result construction for Exp1--Exp4.

The experiment packages own scientific transformations. This module only
carries frozen identities, execution tier, split discipline, and the common
result envelope used after a protocol has completed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from model.common.identity import content_id

from .result_schema import ExperimentResult, MetricObservation, SupportStatus


class ExecutionTier(str, Enum):
    CONTRACT_FAST = "CONTRACT_FAST"
    # Compatibility alias for callers that used the pre-real-fast enum name.
    FAST = "CONTRACT_FAST"
    REAL_DATA_FAST = "REAL_DATA_FAST"
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
        "execution_scope": "CONTRACT_FAST_FIXTURE_ONLY",
        "experiment_id": experiment_id,
        "realized_outcomes_entered_inference": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
    }
    return ExperimentContext(
        dataset_id=dataset_id,
        split=split,
        execution_tier=ExecutionTier.CONTRACT_FAST,
        seed=seed,
        pre_binding={"binding_status": "FAST_NO_RAW_DATA_ACCESS"},
        model_hashes={name: "UNBOUND_FAST" for name in ("PRE", "M1", "M2", "M3", "M4")},
        registry_hashes={"registry_manifest": "UNBOUND_FAST"},
        config_hash=content_id({"experiment": experiment_id, "tier": "CONTRACT_FAST", "dataset": dataset_id, "split": split}),
        scenario_hash=content_id({"experiment": experiment_id, "fixture": "NO_SCENARIOS"}),
        lineage=lineage,
        shared_gates={"M1_POSITIVE_TAIL": "BLOCKED_UNFROZEN", "M4_MONETARY_MAPPING": "BLOCKED_UNFROZEN"},
    )


def _load_real_fast_artifact(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"REAL_FAST_ARTIFACT_MISSING:{path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def real_fast_context(*, root: Path | None = None, seed: int = 0) -> ExperimentContext:
    """Bind the frozen Data2 Development pilot without manufacturing model output.

    This is deliberately the same ``ExperimentContext`` used for contract
    fixtures. Missing scientific artifacts are named as blocked gates rather
    than as ``UNBOUND_FAST`` placeholders.
    """
    repository_root = root or Path(__file__).resolve().parents[2]
    artifact_root = repository_root / "artifacts" / "experiment" / "exp2"
    diagnostics_root = repository_root / "artifacts" / "diagnostics"
    cohort = _load_real_fast_artifact(artifact_root / "DATA2_DEVELOPMENT_PILOT_COHORT_CURRENT_STAGE_V2.json")
    m3_bundle = _load_real_fast_artifact(artifact_root / "DATA2_DEV_PILOT_M3_SCENARIO_BUNDLE.json")
    m4_policy = _load_real_fast_artifact(artifact_root / "DATA2_DEV_PILOT_M4_RISK_POLICY.json")
    refreeze = _load_real_fast_artifact(
        diagnostics_root / "m1_v2_development_current_stage_refreeze" / "M1_V2_CURRENT_STAGE_COHORT_REFREEZE_MANIFEST.json"
    )
    positive_tail = _load_real_fast_artifact(
        diagnostics_root / "m1_v2_positive_tail_decision" / "M1_V2_CURRENT_STAGE_POSITIVE_TAIL_HUMAN_DECISION_PACKET.json"
    )
    # M2/M3/M4 statuses remain sourced from the historical pilot audit until
    # their current-stage artifacts are materialized; cohort identity and M1
    # binding below are current-stage only.
    readiness = _load_real_fast_artifact(artifact_root / "EXP2_PRE_M4_REAL_DATA_PILOT_AUDIT.json")
    if (
        cohort.get("dataset_id") != "DATA2"
        or cohort.get("split") != "DEVELOPMENT"
        or cohort.get("FINAL_TEST_ACCESS_COUNT") != 0
        or cohort.get("PAPER_FULL_RUN") is not False
    ):
        raise ValueError("REAL_FAST_COHORT_BOUNDARY_INVALID")
    if (
        refreeze.get("status") != "NEW_DEVELOPMENT_COHORT_REFROZEN"
        or refreeze.get("next_gate") != "M1_POSITIVE_TAIL_DECISION_REQUIRED"
        or refreeze.get("new_cohort", {}).get("cohort_hash") != cohort.get("cohort_hash")
        or positive_tail.get("status") != "M1_POSITIVE_TAIL_DECISION_REQUIRED"
        or positive_tail.get("cohort", {}).get("cohort_hash") != cohort.get("cohort_hash")
    ):
        raise ValueError("REAL_FAST_CURRENT_STAGE_BINDING_INVALID")

    nodes = tuple(dict(item) for item in cohort.get("decision_nodes", ()))
    if not nodes:
        raise ValueError("REAL_FAST_COHORT_NO_DECISION_NODES")
    m1_status = str(refreeze["m1_artifact_validity"]["status"])
    m2_status = str(readiness.get("M2", {}).get("status", "BLOCKED_M2_ARTIFACT_STATUS_MISSING"))
    policy = dict(m4_policy.get("policy", {}))
    mapping_status = str(m4_policy.get("monetary_mapping_status", "MONETARY_MAPPING_BLOCKED"))
    scenario_status = "BLOCKED_M1_POSITIVE_TAIL_DECISION_REQUIRED"
    scenario_hash = content_id({
        "cohort_hash": cohort["cohort_hash"],
        "scenario_status": scenario_status,
        "m1_status": m1_status,
    })
    return ExperimentContext(
        dataset_id="DATA2",
        split="DEVELOPMENT",
        execution_tier=ExecutionTier.REAL_DATA_FAST,
        cohort=nodes,
        seed=seed,
        pre_binding={
            "binding_status": "REAL_PRE_BOUND_FROM_CURRENT_STAGE_REFROZEN_DATA2_DEVELOPMENT_COHORT",
            "cohort_id": cohort["artifact_hash"],
            "cohort_hash": cohort["cohort_hash"],
            "source_manifest_hash": cohort["source_manifest_hash"],
            "selector_rule": cohort["selector_rule"],
            "roll_minutes": str(cohort["rolling_interval_minutes"]),
            "refreeze_manifest_hash": refreeze["artifact_hash"],
            "positive_tail_packet_hash": positive_tail["artifact_hash"],
            "historical_parent_cohort_hash": refreeze["historical_cohort"]["cohort_hash"],
            "current_stage_changed_node_count": str(refreeze["stage_audit"]["changed_node_count"]),
        },
        m1_artifact=m1_status,
        m2_artifact=m2_status,
        m3_bundle=str(m3_bundle["bundle_hash"]),
        m4_policy=str(policy.get("policy_hash", m4_policy.get("artifact_hash"))),
        model_hashes={
            "PRE": str(cohort["artifact_hash"]),
            "M1": m1_status,
            "M2": m2_status,
            "M3": str(m3_bundle["bundle_hash"]),
            "M4": str(m4_policy["artifact_hash"]),
        },
        registry_hashes={
            "PRE_REGISTRY": str(cohort["registry_hash"]),
            "M3_ACTION_REGISTRY": str(m3_bundle["action_registry_hash"]),
            "M3_RESPONSE_REGISTRY": str(m3_bundle["response_registry_hash"]),
            "M4_MAPPING_DESIGN": content_id(m4_policy.get("monetary_mapping_reference", {})),
        },
        config_hash=str(cohort["config_hash"]),
        scenario_hash=scenario_hash,
        lineage={
            "execution_scope": "REAL_DATA_FAST",
            "cohort_id": cohort["artifact_hash"],
            "cohort_hash": cohort["cohort_hash"],
            "refreeze_manifest_hash": refreeze["artifact_hash"],
            "positive_tail_packet_hash": positive_tail["artifact_hash"],
            "historical_parent_cohort_hash": refreeze["historical_cohort"]["cohort_hash"],
            "current_stage_changed_node_count": refreeze["stage_audit"]["changed_node_count"],
            "current_stage_distribution": refreeze["stage_audit"],
            "selection_rule": cohort["selector_rule"],
            "selection_pre_outcome": cohort["selector_pre_outcome"],
            "scenario_status": scenario_status,
            "M3_NON_A00_INTERPRETATION": "CONDITIONAL_NON_CAUSAL_NON_AUTHORITATIVE",
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        },
        shared_gates={
            "M1_CHECKPOINT": m1_status,
            "M1_POSITIVE_TAIL": str(positive_tail["status"]),
            "M2_SEVEN_COMPONENT": m2_status,
            "M3_A00": "READY_IDENTITY",
            "M3_NON_A00": "SCENARIO_ASSUMPTION_CONDITIONAL",
            "M4_FORMULA": "READY",
            "M4_RISK_POLICY": str(policy.get("policy_status", "NOT_FROZEN")),
            "M4_TAIL": str(policy.get("tail_support_state", "UNRESOLVED")),
            "M4_MAPPING": mapping_status,
            "M4_RANKING": "NOT_RUN_MAPPING_AND_TAIL_BLOCKED",
        },
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


__all__ = [
    "ExecutionTier", "ExperimentContext", "build_context_result", "fast_context",
    "real_fast_context",
]
