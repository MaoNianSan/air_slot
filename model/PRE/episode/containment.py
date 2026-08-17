from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math

from model.PRE.cohort import split_for_date


REASON_CROSS_V5_SPLIT_EXCLUDED = "CROSS_V5_SPLIT_EXCLUDED"
_SPLIT_LABELS = {
    "train": "TRAIN",
    "calibration": "CALIBRATION",
    "development": "DEVELOPMENT",
    "test": "FINAL_TEST",
}
_SPLIT_ORDER = ("train", "calibration", "development", "test")


@dataclass(frozen=True)
class SplitContainmentResult:
    allowed: bool
    split: str | None
    reason_code: str | None
    predecessor_split: str
    successor_split: str
    support_splits: tuple[str, ...]
    transitions: tuple[str, ...]


def decision_times(*, episode_start_time: datetime, episode_end_time: datetime):
    """Yield the frozen five-minute decision grid, inclusive of both endpoints."""
    current = episode_start_time
    while current <= episode_end_time:
        yield current
        current += timedelta(minutes=5)


def episode_node_count(*, episode_start_time: datetime, episode_end_time: datetime) -> int:
    seconds = (episode_end_time - episode_start_time).total_seconds()
    if seconds < 0:
        return 0
    return math.floor(seconds / 300) + 1


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def _transition_code(left: str, right: str) -> str:
    return f"{_SPLIT_LABELS[left]}_TO_{_SPLIT_LABELS[right]}"


def evaluate_episode_containment(
    episode,
    *,
    predecessor_service_date: date | datetime | str,
    successor_service_date: date | datetime | str,
    extra_decision_times: tuple[datetime, ...] = (),
) -> SplitContainmentResult:
    """Check all scientific episode support against the frozen V5 partition.

    The support includes both source service dates, the episode time interval,
    and every five-minute decision node. ``extra_decision_times`` lets callers
    validate materialized nodes when they have already been constructed.
    """
    predecessor_split = split_for_date(_as_date(predecessor_service_date))
    successor_split = split_for_date(_as_date(successor_service_date))
    # V5 partitions are contiguous date intervals. If both interval endpoints
    # map to one split, every monotone five-minute node between them does too.
    support_times = (
        episode.episode_start_time,
        episode.episode_end_time,
        *tuple(extra_decision_times),
    )
    support_splits = tuple(
        split_for_date(stamp.date())
        for stamp in support_times
    )
    sequence = (predecessor_split, *support_splits, successor_split)
    ordered_unique = tuple(name for name in _SPLIT_ORDER if name in set(sequence))
    transitions = tuple(
        _transition_code(left, right)
        for left, right in zip(ordered_unique, ordered_unique[1:])
    )
    unique = set(sequence)
    allowed = len(unique) == 1
    return SplitContainmentResult(
        allowed=allowed,
        split=next(iter(unique)) if allowed else None,
        reason_code=None if allowed else REASON_CROSS_V5_SPLIT_EXCLUDED,
        predecessor_split=predecessor_split,
        successor_split=successor_split,
        support_splits=tuple(dict.fromkeys(support_splits)),
        transitions=tuple(dict.fromkeys(transitions)),
    )


def episode_containment_from_rows(episode, rows_by_id: dict[str, dict]) -> SplitContainmentResult:
    predecessor = rows_by_id[episode.predecessor_flight_id]
    successor = rows_by_id[episode.successor_flight_id]
    return evaluate_episode_containment(
        episode,
        predecessor_service_date=predecessor["service_date"],
        successor_service_date=successor["service_date"],
    )
