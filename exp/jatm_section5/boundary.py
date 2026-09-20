"""Decision-boundary diagnostics for the consequence shortlist."""

from __future__ import annotations

from model.PRE.decision_environment import action_stage_class

from .contracts import AttentionStageResult


def boundary_rows(result: AttentionStageResult) -> list[dict[str, object]]:
    evaluation = result.evaluation
    reference = {item.node_id: item for item in result.reference_decision.entries}
    comparator = {item.node_id: item for item in result.comparator_decision.entries}
    selected = tuple(
        item.node_id for item in result.reference_decision.entries if item.selected
    )
    if not selected:
        cutoff = 0.0
    else:
        cutoff = min(float(reference[node_id].score) for node_id in selected)
    rows = []
    for candidate in result.candidates:
        ref = reference[candidate.node_id]
        cmp = comparator[candidate.node_id]
        margin = float(candidate.p_c) - cutoff
        rows.append(
            {
                "node_id": candidate.node_id,
                "episode_id": candidate.episode_id,
                "stage": action_stage_class(candidate.stage),
                "q": float(result.q),
                "P_C": float(candidate.p_c),
                "P_D": float(candidate.delay_score),
                "margin_to_consequence_cutoff": margin,
                "selected_C": bool(ref.selected),
                "selected_D": bool(cmp.selected),
                "selection_changed": bool(ref.selected != cmp.selected),
                "abs_margin_bin": _margin_bin(abs(margin)),
            }
        )
    return rows


def _margin_bin(value: float) -> str:
    if value <= 1e-12:
        return "0"
    if value <= 0.05:
        return "(0,0.05]"
    if value <= 0.10:
        return "(0.05,0.10]"
    if value <= 0.25:
        return "(0.10,0.25]"
    return ">0.25"


__all__ = ["boundary_rows"]
