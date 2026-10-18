"""Reporting-only helpers.  They consume summaries and never call model code."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping


def write_csv(path: Path, rows: Iterable[Mapping[str, object]], fieldnames: tuple[str, ...] | None = None) -> None:
    rows = list(rows)
    if fieldnames is None:
        fieldnames = tuple(rows[0]) if rows else ()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
