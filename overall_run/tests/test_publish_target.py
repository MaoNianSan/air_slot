from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from src.failures import FormalRunBlocked
from src.pipeline import prepare_empty_publish_target


def test_empty_clean_directory_is_consumed(tmp_path: Path) -> None:
    target = tmp_path / "output" / "fast"
    target.mkdir(parents=True)

    prepare_empty_publish_target(target)

    assert not target.exists()


def test_nonempty_publish_directory_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "output" / "fast"
    target.mkdir(parents=True)
    (target / "run_summary.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FormalRunBlocked, match="OUTPUT_MODE_EXISTS_BACKUP_REQUIRED"):
        prepare_empty_publish_target(target)


def test_cli_exposes_registered_modes_and_resume_alias() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "overall_run" / "main.py"), "--help"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "diagnostic" in result.stdout
    assert "precision" in result.stdout
    assert "--resume" in result.stdout
