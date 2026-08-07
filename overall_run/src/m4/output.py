from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .contracts import M4ContractError, M4EpisodeDecision, M4FormalArtifact


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def episode_decisions_frame(decisions: tuple[M4EpisodeDecision, ...]) -> pd.DataFrame:
    rows = []
    for item in decisions:
        row: dict[str, Any] = {
            "episode_id": item.episode_id,
            "snapshot_id": item.snapshot_id,
            "decision_time": item.decision_time,
            "information_cutoff": item.information_cutoff,
            "result_status": item.result_status.value,
            "status_reason_codes": "|".join(item.status_reason_codes),
            "test_only": item.test_only,
            "publication_allowed": item.publication_allowed,
            "publication_reason_codes": "|".join(item.publication_reason_codes),
            "top1_action_id": item.top1_action_id,
            "top1_risk_score": item.top1_risk_score,
            "top1_expected_post_loss_rmb": item.top1_expected_post_loss_rmb,
            "top1_cvar90_post_loss_rmb": item.top1_cvar90_post_loss_rmb,
            "a00_rank": item.a00_rank,
            "a00_risk_score": item.a00_risk_score,
            "expected_improvement_vs_a00": item.expected_improvement_vs_a00,
            "tail_improvement_vs_a00": item.tail_improvement_vs_a00,
            "risk_score_improvement_vs_a00": item.risk_score_improvement_vs_a00,
            "net_benefit_probability_vs_a00": item.net_benefit_probability_vs_a00,
            "top1_top2_score_gap": item.top1_top2_score_gap,
        }
        for lane, count in item.candidate_counts.items():
            row[f"{lane.lower()}_candidate_count"] = count
        for depth, ranking in item.rankings.items():
            row[f"ranking_at_{depth}"] = list(ranking)
        rows.append(row)
    return pd.DataFrame(rows)


def build_manifest(
    artifact: M4FormalArtifact | None,
    *,
    base: Mapping[str, Any],
    formal_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    manifest = dict(base)
    manifest["formal_file_hashes"] = dict(formal_hashes or {})
    if artifact is not None:
        manifest["test_only"] = artifact.test_only
        manifest["publication_allowed"] = artifact.publication_allowed
    return manifest


def _validate_formal_frames(artifact: M4FormalArtifact) -> None:
    episode_required = {"episode_id", "snapshot_id", "result_status", "publication_allowed"}
    action_required = {"episode_id", "snapshot_id", "action_id", "decision_lane", "risk_score"}
    if artifact.episode_frame.empty or not episode_required.issubset(artifact.episode_frame):
        raise M4ContractError("M4_EPISODE_OUTPUT_SCHEMA_INVALID")
    if artifact.action_frame.empty or not action_required.issubset(artifact.action_frame):
        raise M4ContractError("M4_ACTION_OUTPUT_SCHEMA_INVALID")


def write_formal_artifact(artifact: M4FormalArtifact, output_dir: Path) -> dict[str, str]:
    if artifact.test_only:
        raise M4ContractError("M4_TEST_ONLY_FORMAL_OUTPUT_FORBIDDEN")
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    staging = output_dir.parent / f".{output_dir.name}.staging.{token}"
    backup = output_dir.parent / f".{output_dir.name}.backup.{token}"
    _validate_formal_frames(artifact)
    try:
        staging.mkdir(parents=False, exist_ok=False)
        episode_path = staging / "m4_episode_decision.parquet"
        action_path = staging / "m4_action_evaluation.parquet"
        manifest_path = staging / "m4_manifest.json"
        artifact.episode_frame.to_parquet(episode_path, index=False)
        artifact.action_frame.to_parquet(action_path, index=False)
        hashes = {
            episode_path.name: _sha256(episode_path),
            action_path.name: _sha256(action_path),
        }
        if not artifact.subitem_audit_frame.empty:
            audit_dir = staging / "audit"
            audit_dir.mkdir(parents=True, exist_ok=False)
            audit_path = audit_dir / "m4_subitem_effects.parquet"
            artifact.subitem_audit_frame.to_parquet(audit_path, index=False)
            hashes[str(audit_path.relative_to(staging))] = _sha256(audit_path)
        manifest = build_manifest(artifact, base=artifact.manifest, formal_hashes=hashes)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2, default=str),
            encoding="utf-8",
        )
        if output_dir.exists():
            os.replace(output_dir, backup)
        try:
            os.replace(staging, output_dir)
        except Exception:
            if backup.exists() and not output_dir.exists():
                os.replace(backup, output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        published_hashes = dict(hashes)
        published_hashes["m4_manifest.json"] = _sha256(output_dir / "m4_manifest.json")
        return published_hashes
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup.exists() and output_dir.exists():
            shutil.rmtree(backup)
