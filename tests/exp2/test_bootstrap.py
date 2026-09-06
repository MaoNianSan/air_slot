import numpy as np
import pandas as pd

from exp.exp2.bootstrap import bootstrap_once, resample_episode_clusters
from exp.exp2.protocol import COMPONENTS
from exp.exp2.similar_delay import build_similar_delay_pairs


def _base():
    rows = []
    for episode, offset in (("A", 0), ("B", 3), ("C", 6)):
        for node in range(2):
            value = float(offset + node)
            rows.append(
                {
                    "episode_id": episode,
                    "decision_node_id": f"{episode}{node}",
                    "operational_stage": "PRE_IB",
                    "delay_to_mean": value,
                    "score_C": value,
                    "score_F": value,
                    "score_P": value,
                    "score_R": value,
                    **{f"Z_{component}": value for component in COMPONENTS},
                    **{f"{component}_native": value for component in COMPONENTS},
                }
            )
    return pd.DataFrame(rows)


class FixedGenerator:
    def choice(self, episodes, size, replace):
        return np.asarray(["A", "A", "B"])


def test_episode_cluster_resampling_retains_all_nodes_and_clone_identity():
    sample = resample_episode_clusters(_base(), FixedGenerator())
    assert len(sample) == 6
    assert sample["original_episode_id"].tolist().count("A") == 4
    assert (
        sample.loc[
            sample["original_episode_id"].eq("A"), "bootstrap_instance_id"
        ].nunique()
        == 2
    )


def test_clone_pairs_exclude_same_original_episode():
    sample = resample_episode_clusters(_base(), FixedGenerator())
    sample["consequence_rank_pct"] = np.linspace(0.1, 0.9, len(sample))
    pairs = build_similar_delay_pairs(sample, caliper=10)
    assert (pairs["original_episode_a"] != pairs["original_episode_b"]).all()


def test_bootstrap_rebuilds_ranks_and_pairs():
    result = bootstrap_once(_base(), np.random.default_rng(4), caliper=5)
    assert result["priority"]["n_nodes"] == 6
    assert "F_continuity" in result["informativeness"]
    assert "unique_episode_pairs" in result["similar_delay"]
