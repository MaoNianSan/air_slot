from __future__ import annotations

import pytest

from overall_run.src.m1.calibration import (
    TemperatureArtifact,
    load_temperature_artifact,
    save_temperature_artifact,
)


def test_temperature_artifact_checks_checkpoint_identity(tmp_path) -> None:
    artifact = TemperatureArtifact.build(
        values={"R_IB": 1.1, "R_OB": 1.2, "T_TX": 0.9},
        checkpoint_hash="checkpoint-a",
        pre_manifest_hash="pre-a",
        feature_schema_hash="schema-a",
        calibration_episode_ids=("ep-1", "ep-2"),
        objective_value=0.5,
        artifact_version="temperature-v1",
    )
    path = tmp_path / "temperature.json"
    save_temperature_artifact(path, artifact)
    with pytest.raises(ValueError, match="M1_CALIBRATION_CHECKPOINT_MISMATCH"):
        load_temperature_artifact(
            path,
            checkpoint_hash="checkpoint-b",
            pre_manifest_hash="pre-a",
            feature_schema_hash="schema-a",
        )
