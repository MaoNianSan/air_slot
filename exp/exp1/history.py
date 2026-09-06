"""History-effect aggregation and episode-cluster bootstrap."""

from __future__ import annotations

from collections import defaultdict
from random import Random
from typing import Callable, Iterable, Mapping, Sequence


def episode_means(
    records: Iterable[Mapping[str, object]],
    value_key: str = "delta_crps",
    *,
    episode_key: str = "episode_id",
) -> dict[object, float]:
    grouped: dict[object, list[float]] = defaultdict(list)
    for record in records:
        value = record.get(value_key)
        episode = record.get(episode_key)
        if value is None or episode is None:
            continue
        grouped[episode].append(float(value))
    if not grouped:
        raise ValueError("EXP1_NO_ELIGIBLE_EPISODES")
    return {
        episode: sum(values) / len(values)
        for episode, values in grouped.items()
    }


def episode_balanced_estimate(
    records: Iterable[Mapping[str, object]],
    value_key: str = "delta_crps",
    *,
    episode_key: str = "episode_id",
) -> float:
    means = episode_means(records, value_key, episode_key=episode_key)
    return sum(means.values()) / len(means)


def bootstrap_episode_mean(episode_values: Sequence[float]) -> float:
    """Average sampled episode means, preserving repeated entries."""
    if not episode_values:
        raise ValueError("EXP1_BOOTSTRAP_EMPTY_SAMPLE")
    return sum(float(value) for value in episode_values) / len(episode_values)


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
    means = episode_means(records, value_key, episode_key=episode_key)
    episode_ids = tuple(means)
    estimate = statistic(records, value_key, episode_key=episode_key)
    rng = Random(seed)
    samples: list[float] = []
    for _ in range(reps):
        selected = [means[rng.choice(episode_ids)] for _ in episode_ids]
        samples.append(bootstrap_episode_mean(selected))
    samples.sort()
    low = samples[int(0.025 * (reps - 1))]
    high = samples[int(0.975 * (reps - 1))]
    return estimate, low, high
