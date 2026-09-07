"""Episode-cluster bootstrap with rank and pair reconstruction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd
from exp.shared.resampling import episode_ids, expand_draw, bootstrap_plan

from .informativeness import informativeness_table
from .metrics import kendall_tau_b, midrank_percentiles, priority_metrics
from .priority import rank_base_sample, summarize_priority
from .protocol import COMPONENTS
from .robustness import no_f_execution, no_f_execution_scores
from .similar_delay import (
    aggregate_episode_pairs,
    build_similar_delay_pairs,
    summarize_episode_pairs,
)


@dataclass(frozen=True)
class _PairGroup:
    left: np.ndarray
    right: np.ndarray
    component_medians: dict[str, float]


@dataclass(frozen=True)
class _BootstrapCache:
    frame: pd.DataFrame
    information: pd.DataFrame
    episodes: tuple[str, ...]
    frame_groups: dict[str, np.ndarray]
    information_groups: dict[str, np.ndarray]
    pair_groups: dict[tuple[str, str], _PairGroup]
    information_masks: dict[str, np.ndarray]


def _groups(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    key = "original_episode_id" if "original_episode_id" in frame else "episode_id"
    return {
        str(episode): group.index.to_numpy(dtype=int)
        for episode, group in frame.groupby(key, sort=False)
    }


def _expanded_indices(
    groups: dict[str, np.ndarray], draw
) -> tuple[np.ndarray, np.ndarray]:
    indices: list[np.ndarray] = []
    occurrences: list[np.ndarray] = []
    for occurrence, episode in enumerate(draw):
        group = groups.get(str(episode))
        if group is None:
            continue
        indices.append(group)
        occurrences.append(np.full(len(group), occurrence, dtype=int))
    if not indices:
        return np.empty(0, dtype=int), np.empty(0, dtype=int)
    return np.concatenate(indices), np.concatenate(occurrences)


def _pair_groups(frame: pd.DataFrame, caliper: float) -> dict[tuple[str, str], _PairGroup]:
    episode_key = "original_episode_id" if "original_episode_id" in frame else "episode_id"
    episodes = frame[episode_key].astype(str).to_numpy()
    delays = frame["delay_to_mean"].to_numpy(dtype=float)
    stages = frame["operational_stage"].astype(str).to_numpy()
    pairs: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for stage in sorted(set(stages)):
        ordered = np.flatnonzero(stages == stage)
        node_ids = frame["decision_node_id"].astype(str).to_numpy()
        ordered = ordered[np.lexsort((node_ids[ordered], delays[ordered]))]
        for left_position, left in enumerate(ordered):
            right_position = left_position + 1
            while (
                right_position < len(ordered)
                and delays[ordered[right_position]] - delays[left] <= caliper
            ):
                right = ordered[right_position]
                if episodes[left] != episodes[right]:
                    key = tuple(sorted((episodes[left], episodes[right])))
                    if episodes[left] == key[0]:
                        pairs[key].append((int(left), int(right)))
                    else:
                        pairs[key].append((int(right), int(left)))
                right_position += 1
    output: dict[tuple[str, str], _PairGroup] = {}
    for key, values in pairs.items():
        index = np.asarray(values, dtype=int)
        component_medians = {
            component: float(np.median(np.abs(
                frame[f"Z_{component}"].to_numpy(dtype=float)[index[:, 0]]
                - frame[f"Z_{component}"].to_numpy(dtype=float)[index[:, 1]]
            )))
            for component in COMPONENTS
        }
        output[key] = _PairGroup(index[:, 0], index[:, 1], component_medians)
    return output


def _information_masks(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    delay = frame["delay_to_mean"].to_numpy(dtype=float)
    primary = frame["support_primary"].eq(True).to_numpy() if "support_primary" in frame else np.ones(len(frame), dtype=bool)
    masks = {}
    for quantity, column in [
        *[(component, f"{component}_native") for component in COMPONENTS],
        *((name, name) for name in ("score_F", "score_P", "score_R")),
    ]:
        mask = np.isfinite(delay) & np.isfinite(frame[column].to_numpy(dtype=float)) & primary
        support = f"{quantity}_status"
        if support in frame:
            mask &= frame[support].astype(str).str.startswith("SUPPORTED").to_numpy()
        masks[quantity] = mask
    return masks


def _compile_cache(
    frame: pd.DataFrame, information: pd.DataFrame | None, caliper: float
) -> _BootstrapCache:
    primary = frame.reset_index(drop=True).copy()
    primary["score_C_no_execution"] = no_f_execution_scores(primary)
    info = (frame if information is None else information).reset_index(drop=True).copy()
    episodes = tuple(sorted(set(episode_ids(primary)) | set(episode_ids(info))))
    return _BootstrapCache(
        frame=primary,
        information=info,
        episodes=episodes,
        frame_groups=_groups(primary),
        information_groups=_groups(info),
        pair_groups=_pair_groups(primary, caliper),
        information_masks=_information_masks(info),
    )


def _weighted_values(values: list[float], weights: list[int]) -> np.ndarray:
    if not values:
        return np.empty(0, dtype=float)
    return np.repeat(np.asarray(values, dtype=float), np.asarray(weights, dtype=int))


def _similar_delay_summary(
    cache: _BootstrapCache,
    occurrences_by_episode: dict[str, list[int]],
    consequence_rank: np.ndarray,
) -> dict[str, object]:
    priority_values: list[float] = []
    weights: list[int] = []
    component_values = {component: [] for component in COMPONENTS}
    for (episode_a, episode_b), group in cache.pair_groups.items():
        for occurrence_a in occurrences_by_episode.get(episode_a, []):
            for occurrence_b in occurrences_by_episode.get(episode_b, []):
                priority_values.append(float(np.median(np.abs(
                    consequence_rank[occurrence_a, group.left]
                    - consequence_rank[occurrence_b, group.right]
                ))))
                weights.append(1)
                for component in COMPONENTS:
                    component_values[component].append(group.component_medians[component])
    priority = _weighted_values(priority_values, weights)
    if not len(priority):
        return summarize_episode_pairs(pd.DataFrame())
    result: dict[str, object] = {
        "support_status": "SUPPORTED",
        "unique_episode_pairs": int(np.sum(weights)),
        "median_priority_separation": float(np.median(priority)),
        "share_priority_separation_ge_030": float(np.mean(priority >= .30)),
    }
    for component in COMPONENTS:
        result[f"median_component_gap_{component}"] = float(np.median(
            _weighted_values(component_values[component], weights)
        ))
    return result


def _bootstrap_once_fast(cache: _BootstrapCache, draw) -> dict[str, object]:
    row_index, occurrence = _expanded_indices(cache.frame_groups, draw)
    if not len(row_index):
        raise ValueError("EXP2_BOOTSTRAP_EMPTY_RESAMPLED_FRAME")
    primary = cache.frame
    delay = primary["delay_to_mean"].to_numpy(dtype=float)[row_index]
    consequence = primary["score_C"].to_numpy(dtype=float)[row_index]
    node_column = (
        "original_decision_node_id"
        if "original_decision_node_id" in primary
        else "decision_node_id"
    )
    node = primary[node_column].astype(str).to_numpy()[row_index]
    technical_ids = [f"{value}#bootstrap-{position:04d}" for value, position in zip(node, occurrence)]
    priority = priority_metrics(delay.tolist(), consequence.tolist(), technical_ids)
    no_execution = primary["score_C_no_execution"].to_numpy(dtype=float)[row_index]
    robustness = priority_metrics(delay.tolist(), no_execution.tolist(), technical_ids)
    ranks = midrank_percentiles(consequence)
    consequence_rank = np.full(len(primary), np.nan, dtype=float)
    consequence_rank[row_index] = ranks
    occurrences_by_episode: dict[str, list[int]] = defaultdict(list)
    for occurrence, episode in enumerate(draw):
        occurrences_by_episode[str(episode)].append(occurrence)
    rank_matrix = np.full((len(draw), len(primary)), np.nan, dtype=float)
    offset = 0
    for occurrence, episode in enumerate(draw):
        group = cache.frame_groups.get(str(episode))
        if group is None:
            continue
        rank_matrix[occurrence, group] = ranks[offset:offset + len(group)]
        offset += len(group)
    pair_summary = _similar_delay_summary(cache, occurrences_by_episode, rank_matrix)

    info_index, _ = _expanded_indices(cache.information_groups, draw)
    information = {}
    information_n_nodes = {}
    info = cache.information
    info_delay = info["delay_to_mean"].to_numpy(dtype=float)
    for quantity, mask in cache.information_masks.items():
        selected = info_index[mask[info_index]]
        column = f"{quantity}_native" if quantity in COMPONENTS else quantity
        information[quantity] = kendall_tau_b(
            info_delay[selected], info[column].to_numpy(dtype=float)[selected]
        )
        information_n_nodes[quantity] = int(len(selected))
    return {
        "priority": priority,
        "informativeness": information,
        "informativeness_n_nodes": information_n_nodes,
        "similar_delay": pair_summary,
        "robustness": robustness,
    }


def resample_episode_clusters(
    frame: pd.DataFrame,
    generator: np.random.Generator,
    *,
    sampled_episodes: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    episodes = episode_ids(frame)
    if not episodes:
        raise ValueError("EXP2_BOOTSTRAP_NO_EPISODES")
    sampled = (
        sampled_episodes
        if sampled_episodes is not None
        else tuple(generator.choice(episodes, size=len(episodes), replace=True))
    )
    output = expand_draw(frame, sampled)
    if output.empty:
        raise ValueError("EXP2_BOOTSTRAP_EMPTY_RESAMPLED_FRAME")
    return output


def bootstrap_once(
    frame: pd.DataFrame,
    generator: np.random.Generator,
    *,
    caliper: float,
    informativeness_frame: pd.DataFrame | None = None,
    sampled_episodes: tuple[str, ...] | None = None,
) -> dict[str, object]:
    if sampled_episodes is None:
        episodes = tuple(sorted(set(episode_ids(frame)) | (
            set() if informativeness_frame is None else set(episode_ids(informativeness_frame))
        )))
        sampled_episodes = tuple(generator.choice(episodes, size=len(episodes), replace=True))
    if len(sampled_episodes) == 0:
        raise ValueError("EXP2_BOOTSTRAP_EMPTY_DRAW")
    expanded = expand_draw(frame, sampled_episodes)
    sample = rank_base_sample(expanded) if not expanded.empty else expanded
    if informativeness_frame is None:
        info_source = sample
    else:
        info_source = expand_draw(informativeness_frame, sampled_episodes)
    information_table = informativeness_table(info_source)
    information = information_table.set_index("quantity_id")["estimate"].to_dict()
    information_n_nodes = information_table.set_index("quantity_id")["n_nodes"].to_dict()
    if sample.empty:
        priority = {
            "status": "ABSTAIN_EMPTY_BOOTSTRAP_SAMPLE",
            "kendall_tau_b": None,
            "median_rank_displacement": None,
            "p90_rank_displacement": None,
            "share_rank_displacement_ge_030": None,
            "top_overlap": None,
        }
        robustness = dict(priority)
        pair_summary = summarize_episode_pairs(pd.DataFrame())
    else:
        priority = summarize_priority(sample)
        _, robustness = no_f_execution(sample)
        pairs = build_similar_delay_pairs(sample, caliper=caliper)
        pair_summary = summarize_episode_pairs(aggregate_episode_pairs(pairs))
    return {
        "priority": priority,
        "informativeness": information,
        "informativeness_n_nodes": information_n_nodes,
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
    plan=None,
    reference: bool = False,
) -> list[dict[str, object]]:
    generator = np.random.default_rng(seed)
    cache = _compile_cache(frame, informativeness_frame, caliper)
    episodes = cache.episodes
    if not episodes:
        raise ValueError("EXP2_BOOTSTRAP_NO_EPISODES")
    if plan is None:
        plan = bootstrap_plan(episodes, replicates, seed)
    if len(plan) != replicates or any(len(draw) != len(episodes) for draw in plan):
        raise ValueError("EXP2_BOOTSTRAP_PLAN_LENGTH_MISMATCH")
    results = []
    for replicate, sampled in enumerate(plan):
        if reference:
            results.append(
                bootstrap_once(
                    frame,
                    generator,
                    caliper=caliper,
                    informativeness_frame=informativeness_frame,
                    sampled_episodes=sampled,
                )
            )
        else:
            results.append(_bootstrap_once_fast(cache, sampled))
        if (replicate + 1) % 100 == 0:
            print(f"EXP2 bootstrap {replicate+1}/{replicates}", flush=True)
    return results


def percentile_interval(
    values: list[float | None],
) -> tuple[float | None, float | None]:
    finite = np.asarray([value for value in values if value is not None], dtype=float)
    if not len(finite):
        return None, None
    return float(np.quantile(finite, 0.025)), float(np.quantile(finite, 0.975))
