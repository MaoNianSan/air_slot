from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

MODULES = ("pre", "overall_run", "overall_adv", "part_adv")


def _cleaner(module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = PROJECT / module_name / "clean.py"
    spec = importlib.util.spec_from_file_location(f"{module_name}_dev_clean_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / module_name / "project"
    module_root = project / module_name
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


@pytest.mark.parametrize("module_name", MODULES)
def test_clean_dev_output_dry_run_isolated(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaner = _cleaner(module_name, tmp_path, monkeypatch)
    dev = cleaner.OUTPUT_ROOT / "fast_three_change_dev" / "artifact.json"
    formal = cleaner.OUTPUT_ROOT / "fast" / "artifact.json"
    dev.parent.mkdir(parents=True)
    formal.parent.mkdir(parents=True)
    dev.write_text("dev", encoding="utf-8")
    formal.write_text("formal", encoding="utf-8")
    result = cleaner.clean_selection(
        mode=None,
        output_id="fast_three_change_dev",
        all_output=False,
        dry_run=True,
    )
    assert result["status"] == "DRY_RUN"
    assert result["resolved_output_path"] == str(dev.parent.resolve())
    assert result["selected_files"] == [str(dev.resolve())]
    assert dev.exists() and formal.exists()


@pytest.mark.parametrize("module_name", MODULES)
def test_clean_dev_output_never_targets_formal_fast(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaner = _cleaner(module_name, tmp_path, monkeypatch)
    dev = cleaner.OUTPUT_ROOT / "fast_three_change_dev" / "artifact.json"
    formal = cleaner.OUTPUT_ROOT / "fast" / "artifact.json"
    dev.parent.mkdir(parents=True)
    formal.parent.mkdir(parents=True)
    dev.write_text("dev", encoding="utf-8")
    formal.write_text("formal", encoding="utf-8")
    result = cleaner.clean_selection(
        mode=None,
        output_id="fast_three_change_dev",
        all_output=False,
        dry_run=False,
    )
    assert result["status"] == "CLEAN_PASS"
    assert not dev.exists()
    assert formal.read_text(encoding="utf-8") == "formal"


@pytest.mark.parametrize("module_name", MODULES)
def test_clean_rejects_unknown_output_id(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaner = _cleaner(module_name, tmp_path, monkeypatch)
    with pytest.raises(cleaner.CleanBoundaryError, match="UNKNOWN_OUTPUT_ID"):
        cleaner.clean_selection(
            mode=None,
            output_id="unregistered_dev",
            all_output=False,
            dry_run=True,
        )


@pytest.mark.parametrize("module_name", MODULES)
def test_clean_rejects_path_traversal(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaner = _cleaner(module_name, tmp_path, monkeypatch)
    with pytest.raises(cleaner.CleanBoundaryError, match="INVALID_OUTPUT_ID"):
        cleaner.clean_selection(
            mode=None,
            output_id="../fast",
            all_output=False,
            dry_run=True,
        )
