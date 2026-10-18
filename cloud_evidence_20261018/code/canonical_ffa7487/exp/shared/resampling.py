"""Explicit cluster draws and occurrence identities for Development inference."""

import numpy as np
import pandas as pd


def episode_ids(frame):
    key = "original_episode_id" if "original_episode_id" in frame else "episode_id"
    return tuple(sorted(frame[key].astype(str).unique()))


def bootstrap_plan(episodes, replicates=2000, seed=20260906):
    if not len(episodes):
        raise ValueError("BOOTSTRAP_EMPTY_COHORT")
    return np.random.default_rng(seed).choice(
        np.asarray(episodes), size=(replicates, len(episodes)), replace=True
    )


def expand_draw(frame, draw):
    key = "original_episode_id" if "original_episode_id" in frame else "episode_id"
    groups = {str(e): g for e, g in frame.groupby(key, sort=False)}
    chunks = []
    for occurrence, episode in enumerate(draw):
        if str(episode) not in groups:
            continue
        chunk = groups[str(episode)].copy()
        instance = f"{episode}#bootstrap-{occurrence:04d}"
        original_node = chunk.get("original_decision_node_id", chunk.decision_node_id)
        chunk["original_decision_node_id"] = original_node
        chunk["original_episode_id"] = str(episode)
        chunk["bootstrap_instance_id"] = instance
        chunk["episode_id"] = instance
        chunk["technical_node_id"] = original_node.astype(str) + f"#bootstrap-{occurrence:04d}"
        chunk["decision_node_id"] = chunk["technical_node_id"]
        chunks.append(chunk)
    return pd.concat(chunks, ignore_index=True) if chunks else frame.iloc[:0].copy()


def interval(values):
    values = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)
    values = values[np.isfinite(values)]
    return (None, None) if not len(values) else tuple(np.quantile(values, [.025, .975]))
