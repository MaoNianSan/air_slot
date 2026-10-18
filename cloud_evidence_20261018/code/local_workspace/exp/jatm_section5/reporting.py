 ""Artifact-only reporting for JATM Section 5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping


SECTION_MAPPING = {
    "attention_value": "Section 5.1",
    "recovery_value": "Section 5.2",
    "information_value": "Section 5.3",
    "robustness": "Section 5.4",
}


SCIENTIFIC_OBJECTS = (
    "attention_value",
    "recovery_value",
    "information_value",
    "robustness",
)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def render_report(payload: Mapping[str, object]) -> str:
    """Render from already-computed scientific objects; never recompute."""

    attention = payload["attention_value"]
    recovery = payload["recovery_value"]
    information = payload["information_value"]
    robustness = payload["robustness"]
    lines = [
        "# JATM Section 5 Development Report",
        "",
        "## A. Section 4 H-capacity status",
        f"- H8 complete: {payload.get('h_capacity_status', {}).get('H8')}",
        f"- H16 complete: {payload.get('h_capacity_status', {}).get('H16')}",
        f"- H32 complete: {payload.get('h_capacity_status', {}).get('H32')}",
        f"- Selected capacity: {payload.get('selected_history_capacity')}",
        "",
        "## B. Attention value",
        f"- Canonical counts: {attention.get('canonical_counts')}",
        f"- q grid: {attention.get('q_grid')}",
        f"- Overall L_att: {attention.get('overall', {}).get('L_att_overall')}",
        f"- Bootstrap status: {attention.get('bootstrap_status')}",
        "",
        "## C. Recovery value",
        f"- R* size: {recovery.get('R_star_size')}",
        f"- Stage counts: {recovery.get('stage_counts')}",
        f"- Stage summary: {recovery.get('stage_summary')}",
        "",
        "## D. Information value",
        f"- Components: {information.get('components')}",
        f"- Paired increments: {information.get('paired_increments')}",
        "",
        "## E. Robustness",
        f"- Rows: {robustness.get('row_count')}",
        "",
        "## F. Final-Test readiness",
        f"{payload.get('final_test_readiness', 'NOT_READY')}",
        f"- Blockers: {payload.get('blockers', [])}",
        "",
    ]
    return "\n".join(lines)


def write_report(root: Path, payload: Mapping[str, object]) -> dict[str, str]:
    report = root / "JATM_SECTION5_DEVELOPMENT_REPORT.md"
    manifest = root / "JATM_SECTION5_MANIFEST.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(payload), encoding="utf-8")
    write_json(manifest, payload)
    return {"report": str(report), "manifest": str(manifest)}


__all__ = [
    "SCIENTIFIC_OBJECTS",
    "SECTION_MAPPING",
    "render_report",
    "write_json",
    "write_report",
]
