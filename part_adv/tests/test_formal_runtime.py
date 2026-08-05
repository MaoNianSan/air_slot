import json

import pytest
from downstream_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    SENSITIVITY_TARGET_COLUMN,
)

from src.pipeline import MODELS, _RunTelemetry, _formal_quantiles


def test_formal_quantiles_rejects_missing_upstream_column():
    scientific = {"m1": {"quantiles": [0.01, 0.5, 0.99]}}

    with pytest.raises(ValueError, match="FORMAL_QUANTILE_GRID_MISMATCH:q_0_99"):
        _formal_quantiles(scientific, ["q_0_01", "q_0_5"])


def test_model_checkpoint_reuse_requires_matching_hashes(tmp_path):
    cfg = {
        "output": tmp_path,
        "mode": "fast",
        "config_hash": "config-a",
    }
    telemetry = _RunTelemetry(cfg, "quiet", tmp_path / "logs" / "run.log", "input-a", "impl-a", "definition-a")
    calls = []

    first = telemetry.model_step(1, MODELS[0], 3, lambda: calls.append("fit") or {"value": 7})
    second = telemetry.model_step(1, MODELS[0], 3, lambda: calls.append("refit") or {"value": 8})

    assert first == second == {"value": 7}
    assert calls == ["fit"]
    assert telemetry.records[0]["resume_reused"] is True

    metadata_path = tmp_path / "checkpoints" / "m1" / "hist.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["formal_target_column"] == FORMAL_TARGET_COLUMN
    assert metadata["formal_target_contract_version"] == FORMAL_TARGET_CONTRACT_VERSION
    metadata["config_hash"] = "tampered"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH:HIST:config_hash"):
        telemetry.model_step(1, MODELS[0], 3, lambda: {"value": 9})

    metadata["config_hash"] = "config-a"
    metadata["formal_target_column"] = SENSITIVITY_TARGET_COLUMN
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="CHECKPOINT_HASH_MISMATCH:HIST:formal_target_column"):
        telemetry.model_step(1, MODELS[0], 3, lambda: {"value": 10})
