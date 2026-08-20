"""Evaluation-only M2 helpers; never inputs to the baseline mapper."""

from model.M2.summary import summarize_formal_consequence


def summarize_formal(outputs, *, cvar_alpha=0.95, tail_threshold_cu=0.0):
    """Strict weighted summary that never drops unavailable scenarios."""
    return summarize_formal_consequence(
        tuple(outputs),
        cvar_alpha=cvar_alpha,
        tail_threshold_cu=tail_threshold_cu,
    )


def reconstruct_realized(realized: dict, context: dict):
    """Label a post-hoc evaluation view; it is prohibited from M2 inference."""
    return {
        "artifact_layer": "EVALUATION",
        "realized_inputs": tuple(sorted(realized)),
        "context_version": context.get("version"),
    }
