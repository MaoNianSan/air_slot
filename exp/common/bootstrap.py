import numpy as np
from .contracts import BootstrapResult
from .rng import stream_generator

def episode_bootstrap(rows, metric, *, replicates=2000, seed=0):
    by_episode = {row["episode_id"]: float(row[metric]) for row in rows}
    ids = sorted(by_episode)
    if not ids:
        raise ValueError("no episodes")
    values = np.array([by_episode[x] for x in ids])
    rng = stream_generator("bootstrap", seed, metric)
    samples = np.array([rng.choice(values, size=len(values), replace=True).mean()
                        for _ in range(replicates)])
    return BootstrapResult(metric=metric, estimate=float(values.mean()),
                           ci_lower=float(np.quantile(samples, .025)),
                           ci_upper=float(np.quantile(samples, .975)),
                           replicates=replicates)


def paired_episode_cluster_bootstrap(rows, metric_fn, *, replicates=2000, seed=0):
    """Bootstrap paired variants while retaining every node and seed per episode."""
    by_episode = {}
    for row in rows:
        by_episode.setdefault(row["episode_id"], []).append(row)
    ids = sorted(by_episode)
    if not ids:
        raise ValueError("no episodes")
    episode_values = np.array([
        float(metric_fn(tuple(by_episode[episode_id]))) for episode_id in ids
    ])
    rng = stream_generator("bootstrap", seed, "paired", getattr(metric_fn, "__name__", "metric"))
    samples = np.array([
        episode_values[rng.integers(0, len(ids), size=len(ids))].mean()
        for _ in range(replicates)
    ])
    return BootstrapResult(metric=getattr(metric_fn, "__name__", "metric"),
                           estimate=float(episode_values.mean()),
                           ci_lower=float(np.quantile(samples, .025)),
                           ci_upper=float(np.quantile(samples, .975)),
                           replicates=replicates)
