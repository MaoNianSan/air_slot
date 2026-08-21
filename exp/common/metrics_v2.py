"""Small, standard metric helpers shared by the four experiment protocols."""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from statistics import mean
from typing import Iterable, Mapping


def paired_top1_disagreement(reference: Mapping[str, str], comparison: Mapping[str, str]) -> float | None:
    keys = tuple(sorted(set(reference) & set(comparison)))
    return None if not keys else sum(reference[key] != comparison[key] for key in keys) / len(keys)


def action_family_share(actions: Iterable[str], families: Mapping[str, str]) -> dict[str, float]:
    values = tuple(actions)
    if not values:
        return {}
    counts = defaultdict(int)
    for action in values:
        counts[families.get(action, "UNKNOWN")] += 1
    return {key: counts[key] / len(values) for key in sorted(counts)}


def recommendation_executability(rows: Iterable[Mapping]) -> float | None:
    values = tuple(rows)
    if not values:
        return None
    return sum(bool(row.get("executable", row.get("formally_comparable", False))) for row in values) / len(values)


def absolute_errors(predictions: Iterable[float], targets: Iterable[float]) -> float | None:
    pairs = tuple((float(left), float(right)) for left, right in zip(predictions, targets))
    return None if not pairs else mean(abs(left - right) for left, right in pairs)


def brier_score(probabilities: Iterable[float], outcomes: Iterable[bool | int]) -> float | None:
    pairs = tuple((float(probability), bool(outcome)) for probability, outcome in zip(probabilities, outcomes))
    return None if not pairs else mean((probability - float(outcome)) ** 2 for probability, outcome in pairs)


def crps_from_samples(samples: Iterable[float], observation: float) -> float | None:
    values = tuple(float(value) for value in samples)
    if not values:
        return None
    first = mean(abs(value - float(observation)) for value in values)
    second = mean(abs(left - right) for left in values for right in values)
    return first - 0.5 * second


def variogram_score(samples: Iterable[Mapping[str, float]], observation: Mapping[str, float], *, p: float = 0.5) -> float | None:
    rows = tuple(samples)
    fields = tuple(sorted(observation))
    if not rows or len(fields) < 2:
        return None
    score = 0.0
    for index, left in enumerate(fields):
        for right in fields[index + 1:]:
            observed = abs(float(observation[left]) - float(observation[right])) ** p
            expected = mean(abs(float(row[left]) - float(row[right])) ** p for row in rows)
            score += (expected - observed) ** 2
    return score


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * quantile))))
    return ordered[index]


def episode_cluster_mean(rows: Iterable[Mapping], value_key: str) -> float | None:
    groups: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("episode_id") is not None and row.get(value_key) is not None:
            groups[str(row["episode_id"])].append(float(row[value_key]))
    if not groups:
        return None
    return mean(mean(values) for values in groups.values())


__all__ = ["absolute_errors", "action_family_share", "brier_score", "crps_from_samples",
           "episode_cluster_mean", "paired_top1_disagreement", "percentile",
           "recommendation_executability", "variogram_score"]
