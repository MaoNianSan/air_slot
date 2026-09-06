"""Episode-cluster bootstrap with rank and pair reconstruction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .informativeness import informativeness_population, informativeness_table
from .priority import rank_base_sample, summarize_priority
from .robustness import no_f_execution
from .similar_delay import (
    aggregate_episode_pairs,
    build_similar_delay_pairs,
    summarize_episode_pairs,
)


def resample_episode_clusters(
    frame: pd.DataFrame, generator: np.random.Generator
) -> pd.DataFrame:
    episodes = tuple(sorted(frame["episode_id"].astype(str).unique()))
    if not episodes:
        raise ValueError("EXP2_BOOTSTRAP_NO_EPISODES")
    sampled = generator.choice(episodes, size=len(episodes), replace=True)
    clones: list[pd.DataFrame] = []
    for position, episode_id in enumerate(sampled):
        clone = frame.loc[frame["episode_id"].astype(str) == episode_id].copy()
        instance = f"{episode_id}#bootstrap-{position}"
        clone["original_episode_id"] = episode_id
        clone["bootstrap_instance_id"] = instance
        clone["episode_id"] = instance
        clone["decision_node_id"] = (
            clone["decision_node_id"].astype(str) + f"#bootstrap-{position}"
        )
        clones.append(clone)
    return pd.concat(clones, ignore_index=True)


def bootstrap_once(
    frame: pd.DataFrame,
    generator: np.random.Generator,
    *,
    caliper: float,
    informativeness_frame: pd.DataFrame | None = None,
) -> dict[str, object]:
    sample = rank_base_sample(resample_episode_clusters(frame, generator))
    priority = summarize_priority(sample)
    _, robustness = no_f_execution(sample)
    info_source = sample if informativeness_frame is None else resample_episode_clusters(
        informativeness_frame, generator
    )
    information = informativeness_table(info_source).set_index("quantity_id")["estimate"].to_dict()
    pairs = build_similar_delay_pairs(sample, caliper=caliper)
    pair_summary = summarize_episode_pairs(aggregate_episode_pairs(pairs))
    return {
        "priority": priority,
        "informativeness": information,
        "similar_delay": pair_summary,
        "robustness": robustness,
    }


def run_bootstrap(
    frame: pd.DataFrame,
    *,
    replicates: int,
    seed: int,
    caliper: float,
    informativeness_frame: pd.DataFrame | None = None,
) -> list[dict[str, object]]:
    generator = np.random.default_rng(seed)
    return [
        bootstrap_once(
            frame,
            generator,
            caliper=caliper,
            informativeness_frame=informativeness_frame,
        )
        for _ in range(replicates)
    ]


def percentile_interval(
    values: list[float | None],
) -> tuple[float | None, float | None]:
    finite = np.asarray([value for value in values if value is not None], dtype=float)
    if not len(finite):
        return None, None
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))
