"""Contract tests for the T-cal shared calibration artifact (2026-08-26).

Asserts the D7b-D7c contract without running the heavy fit: only the
calibration split is read; the artifact is ONE shared file listing both
models; quantile calibration stays NOT_APPLIED; checkpoints are never
written; safety counters stay zero.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from model.M1.calibration import fit_zero_mass_temperature
from model.M1.contracts import (
    M1_TEMPERATURE_D_OB_ZERO,
    M1_TEMPERATURE_D_TX_ZERO,
    M1_TEMPERATURE_HAZARD,
)
from model.common.errors import ContractError
from exp.reporting.calibration_artifact import (
    CALIBRATION_SPLIT,
    CURRENT_ONLY_MODEL_ID,
    EXPECTED_CALIBRATION_EPISODES,
    SAFETY,
    STATE_AWARE_MODEL_ID,
    apply_calibration_artifact,
    materialize,
)


class _FakePipeline:
    def __init__(self):
        self.temperatures = {
            M1_TEMPERATURE_HAZARD: 1.0,
            M1_TEMPERATURE_D_OB_ZERO: 1.0,
            M1_TEMPERATURE_D_TX_ZERO: 1.0,
        }


class _FakeExample:
    def __init__(self, index: int):
        self.episode_id = f"EP{index:04d}"
        self.episode_date = CALIBRATION_SPLIT[0]
        self.targets = {"D_OB": None, "D_TX": None}


class _FakeCache:
    def __init__(self):
        self.requested: list[tuple[str, str | None]] = []

    def partition(self, split, *, representation="ADAPTIVE_HISTORY", window_minutes=None):
        self.requested.append((split, representation))
        return tuple(_FakeExample(i) for i in range(64))


def _stub_cache_manifest(tmp_path: Path) -> Path:
    import exp.reporting.calibration_artifact as module

    path = tmp_path / module.CACHE_MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_key": "sha256:stub",
        "cache_hash": "sha256:stub-cache",
        "feature_schema_hash": "sha256:stub-feature",
        "final_test_included": False,
        "final_test_access_count": 0,
        "cache_build_scope": ["train", "calibration", "development"],
        "calibration_episode_count": 64,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _stub_record(model_id: str) -> dict:
    return {
        "model_id": model_id,
        "checkpoint_path": f"artifacts/{model_id}.pt",
        "checkpoint_sha256_before": "sha256:same",
        "checkpoint_sha256_after": "sha256:same",
        "n_episodes": 64,
        "n_nodes": 1122,
        "active_counts": {"hazard": 900, "d_ob_zero": 900, "d_tx_zero": 900},
        "temperatures": {"hazard": 1.05, "d_ob_zero": 1.1, "d_tx_zero": 1.2},
        "before_metrics": {"hazard_event_time_nll": 3.0, "zero_bce": {"D_OB": 0.5, "D_TX": 0.4}},
        "after_metrics": {"hazard_event_time_nll": 2.9, "zero_bce": {"D_OB": 0.49, "D_TX": 0.39}},
        "quantile_coverage_diagnostics": {"D_OB": {"0.1": 0.2}, "D_TX": {"0.1": 0.3}},
        "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
    }


def test_safety_all_zero() -> None:
    assert SAFETY["FINAL_TEST_ACCESS_COUNT"] == 0
    assert SAFETY["M1_TRAINING_RUNS"] == 0
    assert SAFETY["TUNING_RUNS"] == 0
    assert SAFETY["PAPER_FULL_RUN"] is False


def test_calibration_split_contract_values() -> None:
    assert CALIBRATION_SPLIT[0].isoformat() == "2019-07-01"
    assert CALIBRATION_SPLIT[1].isoformat() == "2019-07-31"
    assert EXPECTED_CALIBRATION_EPISODES == 64


def test_zero_mass_fit_forbids_non_calibration_split() -> None:
    import torch

    logits = torch.zeros(4)
    labels = torch.zeros(4)
    active = torch.ones(4, dtype=torch.bool)
    with pytest.raises(ContractError):
        fit_zero_mass_temperature(logits, labels, active, split="development")


def _run_stubbed_materialize(monkeypatch, tmp_path: Path):
    import exp.reporting.calibration_artifact as module

    fake_cache = _FakeCache()
    _stub_cache_manifest(tmp_path)
    _FakeLoader = type("FakeLoader", (), {
        "load": classmethod(lambda cls, *a, **k: fake_cache),
    })
    monkeypatch.setattr(module, "M1DevelopmentBaseCache", _FakeLoader)
    monkeypatch.setattr(
        module, "_fit_one_model",
        lambda *, checkpoint_path, examples, model_id: _stub_record(model_id),
    )
    output_root = tmp_path / "out"
    monkeypatch.setattr(module, "DEFAULT_OUTPUT", output_root)
    monkeypatch.setattr(module, "_sha256", lambda path: f"sha256:{path.name}")
    materialize(root=tmp_path, output_root=output_root)
    return output_root


def test_only_calibration_split_is_read(monkeypatch, tmp_path: Path) -> None:
    import exp.reporting.calibration_artifact as module

    fake_cache = _FakeCache()
    _stub_cache_manifest(tmp_path)
    _FakeLoader = type("FakeLoader", (), {
        "load": classmethod(lambda cls, *a, **k: fake_cache),
    })
    monkeypatch.setattr(module, "M1DevelopmentBaseCache", _FakeLoader)
    monkeypatch.setattr(
        module, "_fit_one_model",
        lambda *, checkpoint_path, examples, model_id: _stub_record(model_id),
    )
    output_root = tmp_path / "out"
    monkeypatch.setattr(module, "DEFAULT_OUTPUT", output_root)
    monkeypatch.setattr(module, "_sha256", lambda path: f"sha256:{path.name}")
    materialize(root=tmp_path, output_root=output_root)
    assert fake_cache.requested == [
        ("calibration", "ADAPTIVE_HISTORY"),
        ("calibration", "CURRENT"),
    ]


def test_shared_artifact_has_both_models_and_no_quantile_claim(monkeypatch, tmp_path: Path) -> None:
    output_root = _run_stubbed_materialize(monkeypatch, tmp_path)
    artifact = json.loads(
        (output_root / "M1_V2_CALIBRATION_ARTIFACT.json").read_text(encoding="utf-8")
    )
    assert set(artifact["shared_by"]) == {STATE_AWARE_MODEL_ID, CURRENT_ONLY_MODEL_ID}
    assert artifact["positive_quantile_calibration"] == "QUANTILE_CALIBRATION_NOT_APPLIED"
    assert artifact["fitting_procedure"]["selection_loop"] == "NONE"
    assert artifact["fitting_procedure"]["train_split_read"] is False
    assert artifact["fitting_procedure"]["development_split_read"] is False
    assert artifact["fitting_procedure"]["final_test_split_read"] is False
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["paper_result"] is False
    manifest = json.loads(
        (output_root / "M1_V2_CALIBRATION_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert manifest["checkpoint_hashes_unchanged"] == {
        STATE_AWARE_MODEL_ID: True,
        CURRENT_ONLY_MODEL_ID: True,
    }


def test_apply_artifact_memory_only(tmp_path: Path) -> None:
    artifact = {
        "models": {
            "STATE_AWARE_H32": _stub_record(STATE_AWARE_MODEL_ID),
            "CURRENT_ONLY": _stub_record(CURRENT_ONLY_MODEL_ID),
        }
    }
    pipeline = _FakePipeline()
    before_files = {p.name for p in tmp_path.iterdir()}
    applied = apply_calibration_artifact(pipeline, artifact, STATE_AWARE_MODEL_ID)
    assert applied[M1_TEMPERATURE_HAZARD] == pytest.approx(1.05)
    assert applied[M1_TEMPERATURE_D_OB_ZERO] == pytest.approx(1.1)
    assert applied[M1_TEMPERATURE_D_TX_ZERO] == pytest.approx(1.2)
    assert pipeline.temperatures[M1_TEMPERATURE_HAZARD] == pytest.approx(1.05)
    after_files = {p.name for p in tmp_path.iterdir()}
    assert before_files == after_files  # no file was written
    with pytest.raises(KeyError):
        apply_calibration_artifact(pipeline, artifact, "UNKNOWN_MODEL")
