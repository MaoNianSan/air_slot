from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..ranking_contract import validate_ranking_prefixes
from .contracts import M4ContractError, M4EvaluationResult, M4FormalArtifact


def evaluate_frozen_artifact(
    artifact: M4FormalArtifact,
    *,
    evaluation_dir: Path | None = None,
    formal_output_dir: Path | None = None,
) -> M4EvaluationResult:
    if evaluation_dir is not None and formal_output_dir is not None:
        evaluation_root = evaluation_dir.resolve()
        formal_root = formal_output_dir.resolve()
        if evaluation_root == formal_root or evaluation_root.is_relative_to(formal_root):
            raise M4ContractError("M4_EVALUATION_FORMAL_DIRECTORY_FORBIDDEN")
    validate_ranking_prefixes(artifact.ranking_prefix_frame)
    checks = {
        "episode_schema": not artifact.episode_frame.empty,
        "action_schema": not artifact.action_frame.empty,
        "ranking_prefixes": True,
        "a00_unique": bool(
            artifact.action_frame[artifact.action_frame["action_id"].eq("A00")]
            .groupby(["episode_id", "snapshot_id"])
            .size()
            .le(1)
            .all()
        ),
        "padding_metrics_null": bool(
            artifact.ranking_prefix_frame.loc[
                artifact.ranking_prefix_frame["is_padding"],
                ["score", "expected_residual", "cvar_residual"],
            ].isna().all().all()
        ),
    }
    result = M4EvaluationResult(
        checks=checks,
        metrics={
            "episode_count": len(artifact.episode_frame),
            "action_count": len(artifact.action_frame),
            "ranking_row_count": len(artifact.ranking_prefix_frame),
        },
        passed=all(checks.values()),
        output_path=str(evaluation_dir) if evaluation_dir is not None else None,
    )
    if evaluation_dir is not None:
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        (evaluation_dir / "m4_evaluation.json").write_text(
            json.dumps(
                {"checks": checks, "metrics": result.metrics, "passed": result.passed},
                ensure_ascii=True,
                indent=2,
            ),
            encoding="utf-8",
        )
    return result


def run_optional_evaluation(
    artifact: M4FormalArtifact,
    config: Mapping[str, object],
    *,
    project_root: Path,
    formal_output_dir: Path | None = None,
) -> M4EvaluationResult | None:
    m4 = dict(config.get("m4", {}))
    if not bool(m4.get("enabled", False)):
        return None
    output_dir = project_root / str(m4.get("output_dir", "output/evaluation/m4"))
    try:
        return evaluate_frozen_artifact(
            artifact,
            evaluation_dir=output_dir,
            formal_output_dir=formal_output_dir,
        )
    except Exception:
        if bool(m4.get("fail_on_error", False)):
            raise
        return M4EvaluationResult(
            checks={"evaluation_completed": False},
            metrics={},
            passed=False,
            output_path=str(output_dir),
        )
