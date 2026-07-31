from __future__ import annotations

import json

import importlib.util

import pandas as pd
import pytest

PARQUET_AVAILABLE = importlib.util.find_spec("pyarrow") is not None or importlib.util.find_spec("fastparquet") is not None
requires_parquet = pytest.mark.skipif(not PARQUET_AVAILABLE, reason="Parquet engine not installed in lightweight test environment")

from src import pipeline


def _identity() -> dict[str, str]:
    return {
        "input_hash": "input",
        "config_hash": "config",
        "implementation_hash": "implementation",
        "mode": "fast",
        "formal_target_column": "y_movement_raw",
        "formal_target_contract_version": "Y_MOVEMENT_RAW_V1_20260725",
        "formal_target_definition_hash": "definition",
    }


@requires_parquet
def test_policy_checkpoint_round_trip_and_hash_rejection(tmp_path):
    score_path = tmp_path / "local_f_scores.parquet"
    pipeline._write_df(pd.DataFrame({"score": [1.0]}), score_path)
    decisions = pd.DataFrame({"policy_id": ["LOCAL_F"], "selected_action": ["A00"]})
    pipeline._write_policy_checkpoint(tmp_path, "LOCAL_F", decisions, _identity(), [score_path])

    restored = pipeline._load_policy_checkpoint(tmp_path, "LOCAL_F", _identity(), [score_path])
    pd.testing.assert_frame_equal(restored, decisions)

    changed = {**_identity(), "input_hash": "changed"}
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH:LOCAL_F:input_hash"):
        pipeline._load_policy_checkpoint(tmp_path, "LOCAL_F", changed, [score_path])

    wrong_target = {**_identity(), "formal_target_column": "y_movement_model"}
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH:LOCAL_F:formal_target_column"):
        pipeline._load_policy_checkpoint(tmp_path, "LOCAL_F", wrong_target, [score_path])


@requires_parquet
def test_uncheckpointed_policy_output_is_rejected(tmp_path):
    _, decisions_path = pipeline._policy_paths(tmp_path, "GLOBAL_FPR")
    pipeline._write_df(pd.DataFrame({"policy_id": ["GLOBAL_FPR"]}), decisions_path)
    with pytest.raises(ValueError, match="MIXED_OUTPUT_UNCHECKPOINTED"):
        pipeline._load_policy_checkpoint(tmp_path, "GLOBAL_FPR", _identity(), [])


def test_run_failure_marks_state_incomplete(tmp_path, monkeypatch):
    cfg = {
        "mode": "fast",
        "output": tmp_path,
        "config_hash": "config",
    }
    upstream = {
        "overall_run_registry_hash": "registry",
        "common_support_cohort_hash": "cohort",
        "formal_target_definition_hash": "definition",
    }
    monkeypatch.setattr(pipeline, "_load", lambda mode, override: cfg)
    monkeypatch.setattr(pipeline, "_upstream", lambda loaded: (pd.DataFrame(), upstream))
    monkeypatch.setattr(pipeline, "_run_active", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run("fast", "quiet")

    state = json.loads((tmp_path / "run_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "INCOMPLETE"
    assert state["error_type"] == "RuntimeError"
    assert not (tmp_path / "artifact_registry.json").exists()
