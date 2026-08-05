from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_validation_report(root: Path, result: dict[str, Any]) -> None:
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "core_validation_recomputed.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
