from __future__ import annotations

import hashlib
import json
import os
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


def _atomic_parquet(frame: pd.DataFrame, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    os.replace(temporary, target)


def write_formal_artifact(artifact: M4FormalArtifact, output_dir: Path) -> dict[str, str]:
    if artifact.test_only or not artifact.publication_allowed:
        raise M4ContractError("M4_TEST_ONLY_FORMAL_OUTPUT_FORBIDDEN")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_path = output_dir / "m4_episode_decision.parquet"
    action_path = output_dir / "m4_action_evaluation.parquet"
    manifest_path = output_dir / "m4_manifest.json"
    _atomic_parquet(artifact.episode_frame, episode_path)
    _atomic_parquet(artifact.action_frame, action_path)
    hashes = {
        episode_path.name: _sha256(episode_path),
        action_path.name: _sha256(action_path),
    }
    if not artifact.subitem_audit_frame.empty:
        audit_dir = output_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / "m4_subitem_effects.parquet"
        _atomic_parquet(artifact.subitem_audit_frame, audit_path)
        hashes[str(audit_path.relative_to(output_dir))] = _sha256(audit_path)
    manifest = build_manifest(artifact, base=artifact.manifest, formal_hashes=hashes)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, manifest_path)
    hashes[manifest_path.name] = _sha256(manifest_path)
    return hashes
