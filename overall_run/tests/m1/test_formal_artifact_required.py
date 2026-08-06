from __future__ import annotations

import pytest

from overall_run.src.m1 import M1Pipeline, M1Settings


def test_formal_pipeline_rejects_missing_model_artifact(published_bundle, tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="M1_MODEL_ARTIFACT_MISSING"):
        M1Pipeline.from_artifacts(
            published_bundle,
            M1Settings(),
            tmp_path / "missing.pt",
            tmp_path / "missing-temperature.json",
        )


def test_formal_pipeline_rejects_missing_temperature_artifact(published_bundle, tmp_path) -> None:
    checkpoint = tmp_path / "placeholder.pt"
    checkpoint.write_bytes(b"not-loaded-because-temperature-is-checked-first")
    with pytest.raises(FileNotFoundError, match="M1_TEMPERATURE_ARTIFACT_MISSING"):
        M1Pipeline.from_artifacts(
            published_bundle,
            M1Settings(),
            checkpoint,
            tmp_path / "missing-temperature.json",
        )


def test_production_package_has_no_random_model_factory() -> None:
    import overall_run.src.m1 as m1

    assert not hasattr(m1, "build_untrained_test_model")
