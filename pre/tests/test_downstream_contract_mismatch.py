from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "entry",
    ["overall_run/main.py", "overall_adv/main.py", "part_adv/main.py"],
)
def test_downstream_entry_stops_before_adapter_migration(entry: str) -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, entry, "fast", "--progress", "quiet"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "M2_CONTRACT_MISMATCH" in result.stderr
    assert "M2-M4 have not migrated" in result.stderr
