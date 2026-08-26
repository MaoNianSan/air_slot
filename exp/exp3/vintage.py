"""Exp3B exact-vintage bindings (freeze F3, P2 refinement 2026-08-25).

LAG_5 / LAG_10 take only the frozen state identity of a decision node whose
decision_time is EXACTLY t - delta minutes.  There is no nearest-past
selection, no interpolation, and no fallback to the current or most recent
state; a current node without an exact vintage is typed-excluded as
EXP3B_VINTAGE_NOT_AVAILABLE.  E_t, the action set, consequences, response,
and J remain fixed (freeze F3).
"""

from __future__ import annotations

from datetime import timedelta

from exp.common.real_fast import select_replay


def exact_vintage_bindings(context, *, lag_minutes: int) -> tuple[dict, ...]:
    """Bind each decision node to the exact prior node at t - lag_minutes.

    Returns one record per decision node with ``state_vintage_node_id`` None
    (and ``exact_vintage_match`` False) when no node has decision_time equal
    to t - lag_minutes.
    """
    if lag_minutes <= 0:
        raise ValueError("EXP3B_EXACT_VINTAGE_REQUIRES_POSITIVE_LAG")
    registry, _ = select_replay(context)
    output = []
    for episode in registry.episodes:
        rows = episode.decision_records
        for current in rows:
            target_time = current.decision_time - timedelta(minutes=lag_minutes)
            exact = tuple(item for item in rows if item.decision_time == target_time)
            source = exact[0] if exact else None
            output.append({
                "episode_id": episode.episode_id,
                "decision_node_id": current.decision_node_id,
                "decision_time": current.decision_time.isoformat(),
                "lag_minutes": lag_minutes,
                "state_vintage_node_id": None if source is None else source.decision_node_id,
                "state_vintage_time": None if source is None else source.decision_time.isoformat(),
                "current_state_read": False,
                "exact_vintage_match": source is not None,
            })
    return tuple(output)


__all__ = ["exact_vintage_bindings"]
