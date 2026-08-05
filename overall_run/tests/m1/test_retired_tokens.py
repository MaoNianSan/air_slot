from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_formal_source_config_and_readmes_have_no_retired_tokens() -> None:
    tokens = (
        "LGB_" + "Q_01",
        "y_" + "movement_raw",
        "y_" + "movement_model",
        "m1_" + "lineage_",
    )
    paths = [ROOT / "README.md"]
    for directory in (
        ROOT / "overall_run" / "src",
        ROOT / "overall_run" / "config",
        ROOT / "overall_run",
        ROOT / "overall_adv",
        ROOT / "part_adv",
        ROOT / "pre",
    ):
        if directory.is_file():
            paths.append(directory)
            continue
        paths.extend(directory.rglob("README.md"))
        if directory.name in {"src", "config"}:
            paths.extend(directory.rglob("*.py"))
            paths.extend(directory.rglob("*.yaml"))
    findings = []
    for path in sorted(set(paths)):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in tokens:
            if token in text:
                findings.append(f"{path.relative_to(ROOT)}:{token}")
    assert findings == []
