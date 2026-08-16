import numpy as np
from .contracts import BootstrapResult

def episode_bootstrap(rows,metric,*,replicates=2000,seed=0):
    by_episode={row["episode_id"]:float(row[metric]) for row in rows};ids=sorted(by_episode)
    if not ids:raise ValueError("no episodes")
    values=np.array([by_episode[x] for x in ids]);rng=np.random.default_rng(seed)
    samples=np.array([rng.choice(values,size=len(values),replace=True).mean() for _ in range(replicates)])
    return BootstrapResult(metric=metric,estimate=float(values.mean()),ci_lower=float(np.quantile(samples,.025)),ci_upper=float(np.quantile(samples,.975)),replicates=replicates)
