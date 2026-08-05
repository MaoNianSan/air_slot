from __future__ import annotations

import pandas as pd

from src.core.observation_builder import _align


def test_source_global_observation_has_no_split_or_chain_fields() -> None:
    frame = pd.DataFrame({"observation_id": ["o1"], "source": ["flow"]})
    aligned = _align(frame)
    assert not {"split", "chain_episode_id", "request_start", "request_end"} & set(aligned.columns)

