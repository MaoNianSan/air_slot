from __future__ import annotations

from datetime import timedelta
from enum import Enum

from model.M1.data import validate_history_sequence
from model.PRE.contracts.pre_state import PREState


class HistoryRepresentation(str, Enum):
    CURRENT = "CURRENT"
    FIXED_HISTORY = "FIXED_HISTORY"
    ADAPTIVE_HISTORY = "ADAPTIVE_HISTORY"


class HistoryEncoderMode(str, Enum):
    """Model-side history contract for principal and baseline paths."""

    FULL_ADAPTIVE_CAUSAL_PREFIX = "FULL_ADAPTIVE_CAUSAL_PREFIX"
    NO_HISTORY_CURRENT_OBSERVATION = "NO_HISTORY_CURRENT_OBSERVATION"


def adaptive_history(
    states: tuple[PREState, ...] | list[PREState],
) -> tuple[PREState, ...]:
    """Return the full causal prefix inside one predecessor-successor episode."""
    output = tuple(states)
    validate_history_sequence(output, require_episode_start=True)
    return output


def current_history(
    states: tuple[PREState, ...] | list[PREState],
) -> tuple[PREState, ...]:
    """Return only the current legal decision node."""
    full = adaptive_history(states)
    output = (full[-1],)
    validate_history_sequence(output, require_episode_start=False)
    return output


def fixed_history(
    states: tuple[PREState, ...] | list[PREState],
    window_minutes: int,
) -> tuple[PREState, ...]:
    """Return the closed causal interval [t-W, t] on the episode grid."""
    if window_minutes <= 0 or window_minutes % 5:
        raise ValueError("FIXED_HISTORY_WINDOW_MUST_ALIGN_TO_FIVE_MINUTE_GRID")
    full = adaptive_history(states)
    current_time = full[-1].decision_node.decision_time
    lower = current_time - timedelta(minutes=window_minutes)
    output = tuple(
        state
        for state in full
        if lower <= state.decision_node.decision_time <= current_time
    )
    validate_history_sequence(output, require_episode_start=False)
    return output


def represent_history(
    states: tuple[PREState, ...] | list[PREState],
    representation: HistoryRepresentation | str,
    *,
    window_minutes: int | None = None,
) -> tuple[PREState, ...]:
    variant = HistoryRepresentation(representation)
    if variant is HistoryRepresentation.CURRENT:
        if window_minutes is not None:
            raise ValueError("CURRENT_HISTORY_REJECTS_WINDOW")
        return current_history(states)
    if variant is HistoryRepresentation.ADAPTIVE_HISTORY:
        if window_minutes is not None:
            raise ValueError("ADAPTIVE_HISTORY_REJECTS_WINDOW")
        return adaptive_history(states)
    if window_minutes is None:
        raise ValueError("FIXED_HISTORY_WINDOW_REQUIRED")
    return fixed_history(states, window_minutes)
