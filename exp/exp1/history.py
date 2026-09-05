"""History-effect aggregation and episode-cluster bootstrap."""

from __future__ import annotations

from collections import defaultdict
from random import Random
from typing import Callable, Iterable, Mapping, Sequence


def episode_balanced_estimate(
    records: Iterable[Mapping[str, object]],
    value_key: str = "delta_crps",
    *,
    episode_key: str = "episode_id",
) -> float:
    grouped: dict[object, list[float]] = defaultdict(list)
    for record in records:
        value = record.get(value_key)
        episode = record.get(episode_key)
        if value is None or episode is None:
            continue
        grouped[episode].append(float(value))
    if not grouped:
        raise ValueError("EXP1_NO_ELIGIBLE_EPISODES")
    return sum(sum(values) / len(values) for values in grouped.values()) / len(grouped)


def episode_cluster_bootstrap(
    records: Sequence[Mapping[str, object]],
    value_key: str = "delta_crps",
    *,
    episode_key: str = "episode_id",
    reps: int = 2000,
    seed: int = 0,
    statistic: Callable[[Iterable[Mapping[str, object]], str, str], float] = episode_balanced_estimate,
) -> tuple[float, float, float]:
    """Return estimate and percentile CI, preserving repeated sampled clusters."""
    if reps <= 0:
        raise ValueError("EXP1_BOOTSTRAP_REPS_INVALID")
    clusters: dict[object, list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        if record.get(value_key) is not None and record.get(episode_key) is not None:
            clusters[record[episode_key]].append(record)
    episode_ids = tuple(clusters)
    if not episode_ids:
        raise ValueError("EXP1_NO_ELIGIBLE_EPISODES")
    estimate = statistic(records, value_key, episode_key=episode_key)
    rng = Random(seed)
    samples: list[float] = []
    for _ in range(reps):
        selected = [episode_id for _ in episode_ids for episode_id in [rng.choice(episode_ids)]]
        sampled_records = [record for episode_id in selected for record in clusters[episode_id]]
        samples.append(statistic(sampled_records, value_key, episode_key=episode_key))
    samples.sort()
    low = samples[int(0.025 * (reps - 1))]
    high = samples[int(0.975 * (reps - 1))]
    return estimate, low, high
