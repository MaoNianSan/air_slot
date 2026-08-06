from __future__ import annotations

import inspect
from pathlib import Path

import overall_run.src.m3 as m3_package
from overall_run.src.legacy import m3_v3_audit
from src.m3 import generate_m3_library
from src.m3.artifact import M3Artifact


def test_m3_generator_has_no_episode_or_downstream_inputs() -> None:
    parameters = inspect.signature(generate_m3_library).parameters
    forbidden = {"episode_id", "m1_prediction", "m2_loss_value", "m4_ranking", "sample_id"}
    assert forbidden.isdisjoint(parameters)


def test_m3_artifact_uses_response_draw_identity() -> None:
    fields = set(M3Artifact.__dataclass_fields__)
    assert "response_draw_ids" in fields
    assert "sample_ids" not in fields


def test_active_import_resolves_to_package_and_legacy_is_isolated() -> None:
    active_path = Path(m3_package.__file__).resolve()
    assert active_path.as_posix().endswith("overall_run/src/m3/__init__.py")
    assert not (active_path.parent.parent / "m3.py").exists()
    assert m3_v3_audit.LEGACY_AUDIT_ONLY is True

    src_root = active_path.parents[1]
    active_sources = [
        path
        for path in src_root.rglob("*.py")
        if "legacy" not in path.relative_to(src_root).parts
    ]
    references = [
        path
        for path in active_sources
        if "legacy.m3_v3_audit" in path.read_text(encoding="utf-8")
    ]
    assert references == []
