from __future__ import annotations

import subprocess
from pathlib import Path


TEXT_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".md", ".toml", ".txt"}
FORBIDDEN = (
    "AIR_CHAIN_CORE_" + "V1",
    "air-chain-core-" + "1.0",
    "LEGACY_MOVEMENT_" + "V1",
    "y_movement_" + "raw",
    "primary_stage_" + "map",
    "snapshot_" + "ratio",
    "41 " + "passed",
)


def _candidate_paths(root: Path) -> set[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    paths = {root / value for value in listed}
    paths.update((root / "reports").glob("PRE_*.md"))
    paths.update((root / "pre" / "reports" / "published" / "core_v2").glob("*"))
    return {path for path in paths if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES}


def test_repository_has_no_retired_contract_identifiers() -> None:
    root = Path(__file__).resolve().parents[2]
    hits: list[str] = []
    for path in sorted(_candidate_paths(root)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN:
            if token in text:
                hits.append(f"{path.relative_to(root)}:{token}")
    assert hits == []
