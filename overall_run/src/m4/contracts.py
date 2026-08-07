from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ..m2.contracts import M2InputBundle, M2SampleLoss
from ..m3.artifact import M3Artifact
from ..m3.contracts import COST_CHANNELS, SUBITEMS_M2_V2, OutcomeCoverage, ParameterStatus


M4_CONTRACT_VERSION = "M4_CONTEXTUAL_RESIDUAL_RISK_V2"
M4_INPUT_CONTRACT_VERSION = "M4_M2_V2_M3_V4_INPUT_V1"
M4_OUTPUT_CONTRACT_VERSION = "M4_RESIDUAL_RISK_OUTPUT_V1"
M4_DRAW_PAIRING_VERSION = "M4_STABLE_SHARED_DRAW_INDEX_V1"
M4_RISK_VERSION = "M4_WEIGHTED_MEAN_CVAR_V1"


class M4ContractError(ValueError):
    pass


class M4UpstreamBlocked(RuntimeError):
    pass


class DecisionLane(str, Enum):
    FORMAL = "FORMAL"
    CONDITIONAL = "CONDITIONAL"
    SCENARIO = "SCENARIO"
    EXCLUDED = "EXCLUDED"


class M4ResultStatus(str, Enum):
    VALID = "VALID"
    TEST_ONLY_VALID = "TEST_ONLY_VALID"
    A00_ONLY = "A00_ONLY"
    CONDITIONAL_ONLY = "CONDITIONAL_ONLY"
    SCENARIO_ONLY = "SCENARIO_ONLY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    ABSTAIN = "ABSTAIN"
    CONTRACT_ERROR = "CONTRACT_ERROR"
    BLOCKED_BY_UPSTREAM = "BLOCKED_BY_UPSTREAM"


REASON_CODES = frozenset({
    "FORMAL_SUPPORTED",
    "M2_INPUT_PARTIAL",
    "M2_INPUT_ABSTAIN",
    "M2_SUBITEM_UNSUPPORTED",
    "M2_TAIL_UNRESOLVED",
    "M2_VALUATION_NOT_FROZEN",
    "M2_PROXY_DEPENDENT",
    "PRE_R2_COMPATIBILITY_ONLY",
    "PRE_R3_NOT_AVAILABLE",
    "PRE_R3_REGISTRY_MISSING",
    "PRE_EVIDENCE_UNSUPPORTED",
    "PRE_SCENARIO_PARAMETER_REQUIRED",
    "PRE_ASSUMPTION_MISMATCH",
    "M3_PARAMETER_NOT_CONFIGURED",
    "M3_PARAMETER_NOT_FROZEN",
    "M3_FORMAL_LIBRARY_NOT_READY",
    "M3_PARTIAL_SUPPORTED",
    "M3_SCENARIO_ONLY",
    "RESOURCE_NETWORK_NOT_AVAILABLE",
    "PASSENGER_CONNECTION_NOT_FORMAL",
    "TAXI_REFERENCE_UNSUPPORTED",
    "STAGE_CONTRACT_NOT_FROZEN",
    "STAGE_NOT_APPLICABLE",
    "OPPORTUNITY_CONTRACT_NOT_CONFIGURED",
    "TEST_ONLY_ARTIFACT",
    "CONTRACT_MISMATCH",
    "ACTION_DISABLED",
})


@dataclass(frozen=True)
class M4RiskConfig:
    expected_weight: float = 0.75
    cvar_weight: float = 0.25
    cvar_alpha: float = 0.90


@dataclass(frozen=True)
class M4Metadata:
    episode_id: str
    snapshot_id: str
    decision_time: datetime
    information_cutoff: datetime
    pre_bundle_id: str
    m1_bundle_id: str
    m1_model_version: str
    m1_sampling_version: str
    m2_contract_version: str
    m3_contract_version: str
    m3_artifact_hash: str
    m3_sample_hash: str
    m4_contract_version: str = M4_CONTRACT_VERSION
    m4_input_contract_version: str = M4_INPUT_CONTRACT_VERSION


@dataclass(frozen=True)
class M4EvidenceContext:
    pre_contract_id: str
    pre_schema_version: str
    pre_research_revision: str
    pre_bundle_id: str
    information_cutoff: datetime
    availability_policy_status: str
    input_rule_registry_hash: str | None
    formula_registry_hash: str | None
    evidence_types: Mapping[str, str]
    proxy_statuses: Mapping[str, str]
    assumption_match_statuses: Mapping[str, str]
    unsupported_fields: tuple[str, ...]
    scenario_parameter_fields: tuple[str, ...]
    lineage_hash: str
    reason_codes: tuple[str, ...] = ()

    @property
    def is_r2(self) -> bool:
        return (
            self.pre_contract_id == "AIR_CHAIN_CORE_V2"
            and self.pre_schema_version == "air-chain-core-2.0"
            and self.pre_research_revision == "AIR_CHAIN_CORE_V2_R2"
        )

    @property
    def is_formal_r3(self) -> bool:
        return (
            self.pre_contract_id == "AIR_CHAIN_CORE_V2"
            and self.pre_schema_version == "air-chain-core-2.1"
            and self.pre_research_revision == "AIR_CHAIN_CORE_V2_R3"
            and bool(self.input_rule_registry_hash)
            and bool(self.formula_registry_hash)
        )


@dataclass(frozen=True)
class M4InputBundle:
    metadata: M4Metadata
    m2_input_bundle: M2InputBundle
    sample_losses: tuple[M2SampleLoss, ...]
    m3_artifact: M3Artifact
    evidence_context: M4EvidenceContext
    snapshot_stage: str | None
    stage_mapping: Mapping[str, str] | None
    stage_mapping_version: str | None
    stage_mapping_test_only: bool
    opportunity_overrides: Mapping[str, float] = field(default_factory=dict)
    formal_mode: bool = False
    test_only: bool = False


@dataclass(frozen=True)
class M4ActionEvaluation:
    episode_id: str
    snapshot_id: str
    action_id: str
    action_family: str
    decision_lane: DecisionLane
    reason_codes: tuple[str, ...]
    lane_rank: int | None
    expected_post_loss_by_channel_rmb: Mapping[str, float]
    expected_total_post_loss_rmb: float
    expected_implementation_cost_rmb: float
    cvar90_post_loss_rmb: float
    risk_score: float
    expected_improvement_vs_a00: float
    tail_improvement_vs_a00: float
    risk_score_improvement_vs_a00: float
    net_benefit_probability_vs_a00: float
    m3_outcome_coverage: OutcomeCoverage | str
    m3_parameter_status: ParameterStatus | str
    m2_support_status: str
    pre_evidence_status: str
    test_only: bool


@dataclass(frozen=True)
class M4EpisodeDecision:
    episode_id: str
    snapshot_id: str
    decision_time: datetime
    information_cutoff: datetime
    result_status: M4ResultStatus
    status_reason_codes: tuple[str, ...]
    test_only: bool
    publication_allowed: bool
    publication_reason_codes: tuple[str, ...]
    candidate_counts: Mapping[str, int]
    top1_action_id: str | None
    top1_risk_score: float | None
    top1_expected_post_loss_rmb: float | None
    top1_cvar90_post_loss_rmb: float | None
    a00_rank: int | None
    a00_risk_score: float | None
    expected_improvement_vs_a00: float | None
    tail_improvement_vs_a00: float | None
    risk_score_improvement_vs_a00: float | None
    net_benefit_probability_vs_a00: float | None
    top1_top2_score_gap: float | None
    rankings: Mapping[int, tuple[str | None, ...]]


@dataclass(frozen=True)
class M4FormalArtifact:
    metadata: M4Metadata
    episode_decisions: tuple[M4EpisodeDecision, ...]
    action_evaluations: tuple[M4ActionEvaluation, ...]
    episode_frame: Any
    action_frame: Any
    full_ranking_frame: Any
    ranking_prefix_frame: Any
    ranking_views: Mapping[int, Any]
    subitem_audit_frame: Any
    manifest: Mapping[str, Any]
    test_only: bool
    publication_allowed: bool
    formal_status: str
    publication_reason_codes: tuple[str, ...]
    evaluation_enabled: bool
    evaluation_status: str
    evaluation_result: M4EvaluationResult | None
    output_contract_version: str = M4_OUTPUT_CONTRACT_VERSION


@dataclass(frozen=True)
class M4UnavailableArtifact:
    status: M4ResultStatus
    reason_codes: tuple[str, ...]
    detail: str
    test_only: bool = False
    publication_allowed: bool = False
    contract_version: str = M4_CONTRACT_VERSION


@dataclass(frozen=True)
class M4EvaluationResult:
    checks: Mapping[str, bool]
    metrics: Mapping[str, float | int | str | bool | None]
    passed: bool
    status: str
    output_path: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PublicationGateResult:
    allowed: bool
    reason_codes: tuple[str, ...]


__all__ = [
    "COST_CHANNELS",
    "SUBITEMS_M2_V2",
    "DecisionLane",
    "M4ActionEvaluation",
    "M4_CONTRACT_VERSION",
    "M4ContractError",
    "M4_DRAW_PAIRING_VERSION",
    "M4EpisodeDecision",
    "M4EvaluationResult",
    "M4EvidenceContext",
    "M4FormalArtifact",
    "M4_INPUT_CONTRACT_VERSION",
    "M4InputBundle",
    "M4Metadata",
    "M4_OUTPUT_CONTRACT_VERSION",
    "M4ResultStatus",
    "M4_RISK_VERSION",
    "M4RiskConfig",
    "M4UnavailableArtifact",
    "M4UpstreamBlocked",
    "OutcomeCoverage",
    "ParameterStatus",
    "PublicationGateResult",
    "REASON_CODES",
]
