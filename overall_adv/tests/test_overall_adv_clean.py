from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_NAME = "overall_adv"
MODULE_ROOT = Path(__file__).resolve().parents[1]
CLEAN_PATH = MODULE_ROOT / "clean.py"


def _load_cleaner():
    spec = importlib.util.spec_from_file_location(f"{MODULE_NAME}_clean_test", CLEAN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cleaner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_cleaner()
    project = tmp_path / "project"
    module_root = project / MODULE_NAME
    output_root = module_root / "output"
    data_root = project / "data"
    cache_root = project / "pre" / "cache"
    output_root.mkdir(parents=True)
    data_root.mkdir(parents=True)
    cache_root.mkdir(parents=True)
    monkeypatch.setattr(module, "MODULE_ROOT", module_root.resolve())
    monkeypatch.setattr(module, "PROJECT_ROOT", project.resolve())
    monkeypatch.setattr(module, "OUTPUT_ROOT", output_root.resolve())
    monkeypatch.setattr(module, "DATA_ROOT", data_root.resolve())
    monkeypatch.setattr(module, "PRE_CACHE_ROOT", cache_root.resolve())
    return module


def test_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, str(CLEAN_PATH), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout
    assert "--all-output" in result.stdout


def test_dry_run_does_not_delete(cleaner) -> None:
    artifact = cleaner.OUTPUT_ROOT / "fast" / "artifact_registry.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    result = cleaner.clean_selection(mode="fast", all_output=False, dry_run=True)
    assert result["status"] == "DRY_RUN"
    assert result["files_removed"] == 0
    assert artifact.exists()


def test_invalid_mode_is_rejected(cleaner) -> None:
    with pytest.raises(SystemExit):
        cleaner.build_parser().parse_args(["--mode", "invalid"])


def test_missing_mode_directory_is_safe(cleaner) -> None:
    result = cleaner.clean_selection(mode="diagnostic", all_output=False, dry_run=False)
    assert result["status"] == "NOTHING_TO_CLEAN"


def test_clean_is_output_local_and_removes_stale_state(cleaner) -> None:
    registry = cleaner.OUTPUT_ROOT / "fast" / "artifact_registry.json"
    checkpoint = cleaner.OUTPUT_ROOT / "fast" / "checkpoints" / "model.json"
    registry.parent.mkdir(parents=True)
    checkpoint.parent.mkdir(parents=True)
    registry.write_text("{}", encoding="utf-8")
    checkpoint.write_text("{}", encoding="utf-8")
    lock = cleaner.OUTPUT_ROOT / "fast" / "workers" / "task.lock"
    partial = cleaner.OUTPUT_ROOT / "fast" / "staging" / "task" / "part.parquet.partial"
    lock.parent.mkdir(parents=True)
    partial.parent.mkdir(parents=True)
    lock.write_text("owned", encoding="utf-8")
    partial.write_text("partial", encoding="utf-8")

    sibling = cleaner.PROJECT_ROOT / "other_module" / "output" / "fast" / "keep.json"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("{}", encoding="utf-8")
    data_file = cleaner.DATA_ROOT / "keep.bin"
    data_file.write_bytes(b"data")
    cache_file = cleaner.PRE_CACHE_ROOT / "keep.bin"
    cache_file.write_bytes(b"cache")

    result = cleaner.clean_selection(mode="fast", all_output=False, dry_run=False)
    assert result["status"] == "CLEAN_PASS"
    assert list((cleaner.OUTPUT_ROOT / "fast").iterdir()) == []
    assert sibling.exists()
    assert data_file.read_bytes() == b"data"
    assert cache_file.read_bytes() == b"cache"
    assert result["active_worker_count"] == 0
    assert result["lock_file_count"] == 0
    assert result["staging_file_count"] == 0
    assert result["partial_artifact_count"] == 0
    assert result["stale_checkpoint_count"] == 0


def test_protected_paths_are_rejected(cleaner) -> None:
    with pytest.raises(cleaner.CleanBoundaryError):
        cleaner._validate_target(cleaner.DATA_ROOT, allow_output_root=False)
    with pytest.raises(cleaner.CleanBoundaryError):
        cleaner._validate_target(cleaner.PRE_CACHE_ROOT, allow_output_root=False)
    with pytest.raises(cleaner.CleanBoundaryError):
        cleaner._validate_target(cleaner.PROJECT_ROOT, allow_output_root=False)


def test_all_output_is_supported(cleaner) -> None:
    for mode in ("fast", "full"):
        artifact = cleaner.OUTPUT_ROOT / mode / "run_summary.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("{}", encoding="utf-8")
    result = cleaner.clean_selection(mode=None, all_output=True, dry_run=False)
    assert result["status"] == "CLEAN_PASS"
    assert list(cleaner.OUTPUT_ROOT.iterdir()) == []


def test_main_does_not_import_or_call_clean() -> None:
    source = (MODULE_ROOT / "main.py").read_text(encoding="utf-8")
    assert "import clean" not in source
    assert "from clean" not in source
    assert "clean.py" not in source
