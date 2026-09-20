"""Artifact-only reporting for JATM Section 5."""

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
    metric_aliases = information.get("metric_aliases", {})
    model_provenance = payload.get("model_definition_provenance", {})
    lines = [
        "# JATM Section 5 Development Report",
        "",
        "## A. Section 4 H-capacity status",
        f"- Status: {payload.get('section4_h_capacity_status')}",
        f"- H8: {payload.get('h_capacity_status', {}).get('H8')}",
        f"- H16: {payload.get('h_capacity_status', {}).get('H16')}",
        f"- H32: {payload.get('h_capacity_status', {}).get('H32')}",
        f"- Selected capacity: {payload.get('selected_history_capacity')}",
        f"- Section 5 primary model: {payload.get('section5_primary_model')}",
        "",
        "## B. Attention value",
        f"- Materialized rolling node count: {attention.get('materialized_rolling_node_count')}",
        f"- Materialized canonical counts: {attention.get('canonical_counts')}",
        f"- Stage-I canonical counts: {attention.get('stage1_canonical_counts')}",
        f"- Stage-I eligible counts: {attention.get('stage1_eligible_counts')}",
        f"- q grid: {attention.get('q_grid')}",
        f"- Overall L_att: {attention.get('overall', {}).get('L_att_overall')}",
        f"- Bootstrap status: {attention.get('bootstrap_status')}",
        "",
        "## C. Recovery value",
        f"- R* size: {recovery.get('R_star_size')}",
        f"- Stage-specific shortlist IDs: {recovery.get('shortlist_node_ids_by_stage')}",
        f"- Stage-specific R* IDs: {recovery.get('stage2_actionable_node_ids_by_stage')}",
        f"- Flattened R* compatibility IDs: {recovery.get('stage2_actionable_node_ids_flattened')}",
        f"- Flattened union semantics: {recovery.get('flattened_union_semantics')}",
        f"- Stage counts: {recovery.get('stage_counts')}",
        f"- Stage summary: {recovery.get('stage_summary')}",
        "",
        "## D. Information value",
        f"- Components: {information.get('components')}",
        f"- CROSS_STATE_DEPENDENCE_L_ATT: {metric_aliases.get('CROSS_STATE_DEPENDENCE_L_ATT')}",
        f"- CROSS_STATE_DEPENDENCE_L_REC: {metric_aliases.get('CROSS_STATE_DEPENDENCE_L_REC')}",
        f"- MARGINAL_UNCERTAINTY_INCREMENT_L_ATT: {metric_aliases.get('MARGINAL_UNCERTAINTY_INCREMENT_L_ATT')}",
        f"- MARGINAL_UNCERTAINTY_INCREMENT_L_REC: {metric_aliases.get('MARGINAL_UNCERTAINTY_INCREMENT_L_REC')}",
        f"- Paired increments: {information.get('paired_increments')}",
        "",
        "## E. Robustness",
        f"- Rows: {robustness.get('row_count')}",
        "",
        "## F. Definition and orchestration provenance",
        f"- SCIENTIFIC_DEFINITION_CHANGED: {payload.get('scientific_definition_changed')}",
        f"- M1_DEFINITION_CHANGED: {model_provenance.get('M1_DEFINITION_CHANGED')}",
        f"- M2_DEFINITION_CHANGED: {model_provenance.get('M2_DEFINITION_CHANGED')}",
        f"- M3_SELECTOR_DEFINITION_CHANGED: {model_provenance.get('M3_SELECTOR_DEFINITION_CHANGED')}",
        f"- M3_STAGE2_DEFINITION_CHANGED: {model_provenance.get('M3_STAGE2_DEFINITION_CHANGED')}",
        f"- M4_LOSS_DEFINITION_CHANGED: {model_provenance.get('M4_LOSS_DEFINITION_CHANGED')}",
        f"- SCIENTIFIC_ORCHESTRATION_CHANGED: {model_provenance.get('SCIENTIFIC_ORCHESTRATION_CHANGED')}",
        f"- SCIENTIFIC_ORCHESTRATION_PATCH: {model_provenance.get('SCIENTIFIC_ORCHESTRATION_PATCH')}",
        "",
        "## G. Final-Test readiness",
        f"- Development ready for freeze: {payload.get('development_ready_for_freeze')}",
        f"- Final-Test ready to open: {payload.get('final_test_ready_to_open')}",
        f"- Final-Test complete: {payload.get('final_test_complete')}",
        f"- Development readiness status: {payload.get('final_test_readiness', 'NOT_READY')}",
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
