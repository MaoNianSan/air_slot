from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from src.m4 import evaluate_frozen_artifact, run_m4_synthetic_integration, run_optional_evaluation
from src.m4.contracts import M4ContractError


def _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides):
    bundle, losses = m4_input_factory()
    return run_m4_synthetic_integration(
        bundle,
        losses,
        m3_artifact,
        cfg.scientific,
        stage_mapping={"TURNAROUND": "t1"},
        opportunity_overrides=opportunity_overrides,
    )


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = frame.to_json(orient="split", date_format="iso", default_handler=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_evaluation_disabled_not_run(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    result = run_optional_evaluation(
        artifact,
        {"evaluation": {"m4": {"enabled": False, "fail_on_error": False, "output_dir": "eval"}}},
        project_root=tmp_path,
    )
    assert result is None
    assert not (tmp_path / "eval").exists()


def test_evaluation_runs_after_formal_freeze(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    result = evaluate_frozen_artifact(artifact, evaluation_dir=tmp_path / "evaluation")
    assert result.passed
    assert (tmp_path / "evaluation" / "m4_v2_evaluation.json").is_file()


def test_formal_hash_same_with_evaluation_on_off(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    before = (_frame_hash(artifact.episode_frame), _frame_hash(artifact.action_frame))
    evaluate_frozen_artifact(artifact, evaluation_dir=tmp_path / "evaluation")
    after = (_frame_hash(artifact.episode_frame), _frame_hash(artifact.action_frame))
    assert before == after


def test_evaluation_failure_preserves_formal_output(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    formal = tmp_path / "formal"
    formal.mkdir()
    sentinel = formal / "sentinel.txt"
    sentinel.write_text("frozen", encoding="ascii")
    before = sentinel.read_bytes()
    with pytest.raises(M4ContractError, match="FORMAL_DIRECTORY_FORBIDDEN"):
        evaluate_frozen_artifact(
            artifact,
            evaluation_dir=formal / "evaluation",
            formal_output_dir=formal,
        )
    assert sentinel.read_bytes() == before


def test_evaluation_cannot_write_formal_directory(
    tmp_path, cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    formal = tmp_path / "formal"
    with pytest.raises(M4ContractError, match="FORMAL_DIRECTORY_FORBIDDEN"):
        evaluate_frozen_artifact(
            artifact,
            evaluation_dir=formal,
            formal_output_dir=formal,
        )


def test_evaluation_metrics_absent_from_formal_schema(
    cfg, m4_input_factory, m3_artifact, opportunity_overrides
) -> None:
    artifact = _artifact(cfg, m4_input_factory, m3_artifact, opportunity_overrides)
    assert not any(column.startswith("evaluation_") for column in artifact.episode_frame)
    assert not any(column.startswith("evaluation_") for column in artifact.action_frame)
