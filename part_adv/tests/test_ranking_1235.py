from __future__ import annotations

import pandas as pd

from ranking_contract import build_ranking_prefixes, full_ranking_from_scores
from src.pipeline_common import MODELS
from src.pipeline_propagation import _model_ranking_agreement


def test_part_adv_agreement_1235_and_padding_exclusion() -> None:
    base = pd.DataFrame([
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A00", "action_family": "null", "value": 2.0, "expected_residual": 2.0, "priority": 0},
        {"episode_id": "e1", "snapshot_id": "s1", "action_id": "A11", "action_family": "hold", "value": 1.0, "expected_residual": 1.0, "priority": 1},
    ])
    universe = base[["episode_id", "snapshot_id"]].drop_duplicates()
    parts = []
    for model in MODELS:
        values = base.copy()
        if model == "HIST":
            values["value"] = [1.0, 2.0]
        prefixes, _ = build_ranking_prefixes(
            universe,
            full_ranking_from_scores(values, "value")
        )
        parts.append(prefixes.assign(model_id=model))
    rankings = pd.concat(parts, ignore_index=True)
    agreement = _model_ranking_agreement(rankings)
    assert set(agreement["ranking_k"]) == {1, 2, 3, 5}
    assert set(agreement["model_id"]) == set(MODELS)
    assert agreement.loc[agreement["model_id"].eq("PROP"), "agreement"].all()
    assert rankings.loc[rankings["is_padding"], "action_id"].isna().all()
