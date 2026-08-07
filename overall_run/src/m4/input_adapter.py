from __future__ import annotations

from typing import Mapping

from ..m2.contracts import M2InputBundle, M2SampleLoss
from ..m3.artifact import M3Artifact
from .compatibility import formal_m2_blockers, validate_m2_inputs, validate_m3_artifact
from .contracts import M4InputBundle, M4Metadata, M4UpstreamBlocked
from .evidence import PRE_STAGE_KEY, build_evidence_context


def _snapshot_stage(bundle: M2InputBundle) -> str | None:
    stage = bundle.context_provenance.get(PRE_STAGE_KEY, {})
    for key in ("flight_chain_stage", "snapshot_stage", "stage"):
        if stage.get(key) is not None:
            return str(stage[key])
    return None


def adapt_m4_inputs(
    m2_input_bundle: M2InputBundle,
    sample_losses: tuple[M2SampleLoss, ...],
    m3_artifact: M3Artifact,
    *,
    formal_mode: bool = False,
    stage_mapping: Mapping[str, str] | None = None,
    stage_mapping_version: str | None = None,
    stage_mapping_test_only: bool = False,
    opportunity_overrides: Mapping[str, float] | None = None,
) -> M4InputBundle:
    validate_m2_inputs(m2_input_bundle, sample_losses)
    validate_m3_artifact(m3_artifact, formal_mode=formal_mode)
    evidence = build_evidence_context(m2_input_bundle)
    blockers = formal_m2_blockers(m2_input_bundle, sample_losses)
    if formal_mode and blockers:
        raise M4UpstreamBlocked("|".join(blockers))
    if formal_mode and not evidence.is_formal_r3:
        reason = (
            "PRE_R3_REGISTRY_MISSING"
            if evidence.pre_schema_version == "air-chain-core-2.1"
            else "PRE_R3_NOT_AVAILABLE"
        )
        raise M4UpstreamBlocked(reason)
    if formal_mode and stage_mapping_test_only:
        raise M4UpstreamBlocked("TEST_ONLY_ARTIFACT")
    overrides = dict(opportunity_overrides or {})
    test_only = bool(
        m3_artifact.test_only
        or m2_input_bundle.valuation_context.test_only
        or stage_mapping_test_only
        or overrides
    )
    metadata = M4Metadata(
        episode_id=m2_input_bundle.metadata.episode_id,
        snapshot_id=m2_input_bundle.metadata.snapshot_id,
        decision_time=m2_input_bundle.metadata.query_time,
        information_cutoff=m2_input_bundle.metadata.information_cutoff,
        pre_bundle_id=m2_input_bundle.metadata.pre_bundle_id,
        m1_bundle_id=m2_input_bundle.metadata.m1_bundle_id,
        m1_model_version=m2_input_bundle.metadata.m1_model_version,
        m1_sampling_version=m2_input_bundle.metadata.m1_sampling_version,
        m2_contract_version=m2_input_bundle.metadata.m2_contract_version,
        m3_contract_version=m3_artifact.contract_version,
        m3_artifact_hash=m3_artifact.artifact_hash,
        m3_sample_hash=m3_artifact.sample_hash,
    )
    return M4InputBundle(
        metadata=metadata,
        m2_input_bundle=m2_input_bundle,
        sample_losses=sample_losses,
        m3_artifact=m3_artifact,
        evidence_context=evidence,
        snapshot_stage=_snapshot_stage(m2_input_bundle),
        stage_mapping=dict(stage_mapping) if stage_mapping is not None else None,
        stage_mapping_version=stage_mapping_version,
        stage_mapping_test_only=stage_mapping_test_only,
        opportunity_overrides=overrides,
        formal_mode=formal_mode,
        test_only=test_only,
    )
