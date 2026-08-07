from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from ..m2.contracts import M2InputBundle, M2SampleLoss
from ..m3.artifact import M3Artifact
from .compatibility import validate_m2_inputs
from .contracts import (
    COST_CHANNELS,
    DecisionLane,
    M4ActionEvaluation,
    M4ContractError,
    M4EpisodeDecision,
    M4FormalArtifact,
    M4InputBundle,
    M4ResultStatus,
    M4RiskConfig,
    M4_CONTRACT_VERSION,
    M4_DRAW_PAIRING_VERSION,
    M4_RISK_VERSION,
)
from .explanation import summarize_reason_codes
from .input_adapter import adapt_m4_inputs
from .lane_assignment import assign_decision_lane
from .opportunity import evaluate_opportunity
from .output import episode_decisions_frame, write_formal_artifact
from .post_loss import PostLossSamples, calculate_post_loss
from .ranking import (
    M4_RANKING_TIE_BREAK,
    action_evaluations_frame,
    assign_lane_ranks,
    build_authoritative_ranking,
)
from .publication import M4_PUBLICATION_GATE_VERSION, evaluate_publication_gate
from .risk import risk_score, weighted_mean, weighted_positive_probability
from .stage_adapter import evaluate_stage
from .status import determine_result_status
from .evaluation import run_optional_evaluation
from ..ranking_contract import RANKING_CONTRACT_VERSION


def _risk_config(config: Mapping[str, object]) -> M4RiskConfig:
    m4 = dict(config.get("m4", config))
    risk = dict(m4.get("risk", {}))
    return M4RiskConfig(
        expected_weight=float(risk.get("expected_weight", 0.75)),
        cvar_weight=float(risk.get("cvar_weight", 0.25)),
        cvar_alpha=float(risk.get("cvar_alpha", 0.90)),
    )


def _pre_evidence_status(bundle: M4InputBundle) -> str:
    if bundle.evidence_context.is_formal_r3:
        return "PRE_R3_FORMAL"
    if bundle.evidence_context.is_r2:
        return "PRE_R2_COMPATIBILITY_ONLY"
    return "PRE_R3_NOT_AVAILABLE"


def _subitem_audit(
    bundle: M4InputBundle,
    post_by_action: Mapping[str, PostLossSamples],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for action_id, post in post_by_action.items():
        for sample_position, loss in enumerate(bundle.sample_losses):
            draw_id = int(post.draw_indices[sample_position])
            recovery = np.asarray(
                bundle.m3_artifact.subitem_recovery_rates[action_id][draw_id], dtype=float
            )
            for index, subitem in enumerate(post.pre_subitem_loss_rmb):
                rows.append({
                    "episode_id": loss.episode_id,
                    "snapshot_id": loss.snapshot_id,
                    "sample_id": loss.sample_id,
                    "action_id": action_id,
                    "response_draw_id": draw_id,
                    "subitem_id": subitem,
                    "pre_loss_rmb": post.pre_subitem_loss_rmb[subitem][sample_position],
                    "recovery_rate": recovery[index],
                    "post_loss_rmb": post.post_subitem_loss_rmb[subitem][sample_position],
                })
    return pd.DataFrame(rows)


def run_m4(
    bundle: M4InputBundle,
    config: Mapping[str, object],
) -> M4FormalArtifact:
    weights = validate_m2_inputs(bundle.m2_input_bundle, bundle.sample_losses)
    risk = _risk_config(config)
    post_by_action = {
        action_id: calculate_post_loss(
            action_id=action_id,
            losses=bundle.sample_losses,
            artifact=bundle.m3_artifact,
        )
        for action_id in bundle.m3_artifact.action_catalog
    }
    a00_post = post_by_action["A00"]
    a00_score, a00_expected, a00_cvar = risk_score(
        a00_post.post_total_loss_rmb, weights, risk
    )

    evaluations: list[M4ActionEvaluation] = []
    for action_id, action in bundle.m3_artifact.action_catalog.items():
        stage = evaluate_stage(
            action,
            source_stage=bundle.snapshot_stage,
            mapping=bundle.stage_mapping,
            mapping_version=bundle.stage_mapping_version,
            mapping_test_only=bundle.stage_mapping_test_only,
        )
        opportunity = evaluate_opportunity(
            action,
            overrides=bundle.opportunity_overrides,
        )
        lane, reasons = assign_decision_lane(
            action_id=action_id,
            bundle=bundle,
            stage=stage,
            opportunity=opportunity,
        )
        post = post_by_action[action_id]
        score, expected, cvar = risk_score(post.post_total_loss_rmb, weights, risk)
        expected_by_channel = {
            channel: weighted_mean(post.post_channel_loss_rmb[channel], weights)
            for channel in COST_CHANNELS
        }
        expected_implementation = sum(
            weighted_mean(post.implementation_costs_rmb[channel], weights)
            for channel in COST_CHANNELS
        )
        delta = a00_post.post_total_loss_rmb - post.post_total_loss_rmb
        evaluations.append(M4ActionEvaluation(
            episode_id=bundle.metadata.episode_id,
            snapshot_id=bundle.metadata.snapshot_id,
            action_id=action_id,
            action_family=action.action_family,
            decision_lane=lane,
            reason_codes=reasons,
            lane_rank=None,
            expected_post_loss_by_channel_rmb=expected_by_channel,
            expected_total_post_loss_rmb=expected,
            expected_implementation_cost_rmb=expected_implementation,
            cvar90_post_loss_rmb=cvar,
            risk_score=score,
            expected_improvement_vs_a00=a00_expected - expected,
            tail_improvement_vs_a00=a00_cvar - cvar,
            risk_score_improvement_vs_a00=a00_score - score,
            net_benefit_probability_vs_a00=weighted_positive_probability(delta, weights),
            m3_outcome_coverage=action.outcome_coverage,
            m3_parameter_status=action.parameter_status,
            m2_support_status=str(getattr(bundle.m2_input_bundle.input_status, "value", bundle.m2_input_bundle.input_status)),
            pre_evidence_status=_pre_evidence_status(bundle),
            test_only=bundle.test_only,
        ))
    ranked_evaluations = assign_lane_ranks(tuple(evaluations))
    full_ranking, ranking_prefixes, ranking_views = build_authoritative_ranking(
        ranked_evaluations
    )
    action_frame = action_evaluations_frame(ranked_evaluations)

    candidate_counts = {
        lane.value: sum(item.decision_lane is lane for item in ranked_evaluations)
        for lane in DecisionLane
    }
    status = determine_result_status(ranked_evaluations, test_only=bundle.test_only)
    publication = evaluate_publication_gate(bundle, ranked_evaluations, status)

    top1 = full_ranking.iloc[0] if not full_ranking.empty else None
    top2_gap = (
        float(full_ranking.iloc[1]["score"] - full_ranking.iloc[0]["score"])
        if len(full_ranking) > 1
        else None
    )
    a00_rows = full_ranking[full_ranking["action_id"].eq("A00")] if not full_ranking.empty else pd.DataFrame()
    a00_rank = int(a00_rows.iloc[0]["rank"]) if not a00_rows.empty else None
    a00_eval = next(item for item in ranked_evaluations if item.action_id == "A00")
    rankings: dict[int, tuple[str | None, ...]] = {}
    for depth, view in ranking_views.items():
        values: list[str | None] = []
        for value in view.sort_values("rank_position")["action_id"]:
            values.append(None if pd.isna(value) else str(value))
        rankings[depth] = tuple(values)
    decision = M4EpisodeDecision(
        episode_id=bundle.metadata.episode_id,
        snapshot_id=bundle.metadata.snapshot_id,
        decision_time=bundle.metadata.decision_time,
        information_cutoff=bundle.metadata.information_cutoff,
        result_status=status,
        status_reason_codes=tuple(summarize_reason_codes(ranked_evaluations)),
        test_only=bundle.test_only,
        publication_allowed=publication.allowed,
        publication_reason_codes=publication.reason_codes,
        candidate_counts=candidate_counts,
        top1_action_id=str(top1["action_id"]) if top1 is not None else None,
        top1_risk_score=float(top1["score"]) if top1 is not None else None,
        top1_expected_post_loss_rmb=float(top1["expected_residual"]) if top1 is not None else None,
        top1_cvar90_post_loss_rmb=float(top1["cvar_residual"]) if top1 is not None else None,
        a00_rank=a00_rank,
        a00_risk_score=a00_eval.risk_score,
        expected_improvement_vs_a00=(float(top1["expected_improvement_vs_a00"]) if top1 is not None else None),
        tail_improvement_vs_a00=(float(top1["tail_improvement_vs_a00"]) if top1 is not None else None),
        risk_score_improvement_vs_a00=(float(top1["risk_score_improvement_vs_a00"]) if top1 is not None else None),
        net_benefit_probability_vs_a00=(float(top1["net_benefit_probability_vs_a00"]) if top1 is not None else None),
        top1_top2_score_gap=top2_gap,
        rankings=rankings,
    )
    episode_frame = episode_decisions_frame((decision,))
    m4_config = dict(config.get("m4", config))
    emit_subitem = bool(dict(m4_config.get("output", {})).get("emit_subitem_audit", False))
    subitem_audit = _subitem_audit(bundle, post_by_action) if emit_subitem else pd.DataFrame()
    manifest = {
        "pre_contract_id": bundle.evidence_context.pre_contract_id,
        "pre_schema_version": bundle.evidence_context.pre_schema_version,
        "pre_research_revision": bundle.evidence_context.pre_research_revision,
        "pre_bundle_id": bundle.metadata.pre_bundle_id,
        "m1_model_version": bundle.metadata.m1_model_version,
        "m1_sampling_version": bundle.metadata.m1_sampling_version,
        "m2_contract_version": bundle.metadata.m2_contract_version,
        "m2_valuation_version": bundle.m2_input_bundle.valuation_context.valuation_version,
        "m3_contract_version": bundle.metadata.m3_contract_version,
        "m3_artifact_hash": bundle.metadata.m3_artifact_hash,
        "m3_sample_hash": bundle.metadata.m3_sample_hash,
        "m3_parameter_freeze_status": bundle.m3_artifact.parameter_freeze_status,
        "m3_formal_library_status": bundle.m3_artifact.formal_library_status,
        "m4_contract_version": M4_CONTRACT_VERSION,
        "draw_pairing_version": M4_DRAW_PAIRING_VERSION,
        "risk_version": M4_RISK_VERSION,
        "ranking_contract_version": RANKING_CONTRACT_VERSION,
        "publication_gate_version": M4_PUBLICATION_GATE_VERSION,
        "risk": {
            "expected_weight": risk.expected_weight,
            "cvar_weight": risk.cvar_weight,
            "cvar_alpha": risk.cvar_alpha,
        },
        "ranking_depths": [1, 2, 3, 5],
        "tie_break": list(M4_RANKING_TIE_BREAK),
        "test_only": bundle.test_only,
        "m4_formal_status": (
            "TEST_ONLY"
            if bundle.test_only
            else status.value
            if status in {
                M4ResultStatus.CONTRACT_ERROR,
                M4ResultStatus.BLOCKED_BY_UPSTREAM,
                M4ResultStatus.ABSTAIN,
            }
            else "PASS"
        ),
        "publication_allowed": publication.allowed,
        "publication_reason_codes": list(publication.reason_codes),
        "pre_evidence_lineage_hash": bundle.evidence_context.lineage_hash,
    }
    return M4FormalArtifact(
        metadata=bundle.metadata,
        episode_decisions=(decision,),
        action_evaluations=ranked_evaluations,
        episode_frame=episode_frame,
        action_frame=action_frame,
        full_ranking_frame=full_ranking,
        ranking_prefix_frame=ranking_prefixes,
        ranking_views=ranking_views,
        subitem_audit_frame=subitem_audit,
        manifest=manifest,
        test_only=bundle.test_only,
        publication_allowed=publication.allowed,
        formal_status=str(manifest["m4_formal_status"]),
        publication_reason_codes=publication.reason_codes,
        evaluation_enabled=False,
        evaluation_status="NOT_RUN",
        evaluation_result=None,
    )


def run_m4_synthetic_integration(
    m2_input_bundle: M2InputBundle,
    sample_losses: tuple[M2SampleLoss, ...],
    m3_artifact: M3Artifact,
    config: Mapping[str, object],
    *,
    stage_mapping: Mapping[str, str] | None = None,
    stage_mapping_version: str = "M4_TEST_STAGE_MAPPING_V1",
    opportunity_overrides: Mapping[str, float] | None = None,
) -> M4FormalArtifact:
    bundle = adapt_m4_inputs(
        m2_input_bundle,
        sample_losses,
        m3_artifact,
        formal_mode=False,
        stage_mapping=stage_mapping,
        stage_mapping_version=stage_mapping_version,
        stage_mapping_test_only=stage_mapping is not None,
        opportunity_overrides=opportunity_overrides,
    )
    artifact = run_m4(bundle, config)
    if not artifact.test_only or artifact.publication_allowed:
        raise RuntimeError("M4_SYNTHETIC_ISOLATION_FAILURE")
    return artifact


def run_m4_formal_stage(
    m2_input_bundle: M2InputBundle,
    sample_losses: tuple[M2SampleLoss, ...],
    m3_artifact: M3Artifact,
    config: Mapping[str, object],
    *,
    stage_mapping: Mapping[str, str],
    stage_mapping_version: str,
    output_dir: Path | None = None,
    project_root: Path | None = None,
) -> M4FormalArtifact:
    bundle = adapt_m4_inputs(
        m2_input_bundle,
        sample_losses,
        m3_artifact,
        formal_mode=True,
        stage_mapping=stage_mapping,
        stage_mapping_version=stage_mapping_version,
        stage_mapping_test_only=False,
    )
    artifact = run_m4(bundle, config)
    if output_dir is None:
        raise M4ContractError("M4_FORMAL_OUTPUT_DIRECTORY_REQUIRED")
    evaluation_cfg = dict(dict(config.get("evaluation", {})).get("m4", {}))
    evaluation_enabled = bool(evaluation_cfg.get("enabled", False))
    if evaluation_enabled and project_root is None:
        raise M4ContractError("M4_EVALUATION_PROJECT_ROOT_REQUIRED")
    write_formal_artifact(artifact, output_dir)
    evaluation_result = run_optional_evaluation(
        artifact,
        config,
        project_root=(project_root or output_dir.parent),
        formal_output_dir=output_dir,
    )
    return replace(
        artifact,
        evaluation_enabled=evaluation_enabled,
        evaluation_status=(evaluation_result.status if evaluation_result is not None else "NOT_RUN"),
        evaluation_result=evaluation_result,
    )
