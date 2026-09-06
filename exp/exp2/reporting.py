"""Artifact writers and Development support audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from .protocol import COMPONENTS


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def support_audit(
    base_all: pd.DataFrame,
    base_sample: pd.DataFrame,
    pair_counts: Mapping[str, int],
    tie_counts: Mapping[str, int],
) -> dict[str, object]:
    components = {}
    for component in COMPONENTS:
        status = base_all[f"{component}_status"].eq("SUPPORTED")
        supported = base_all.loc[status]
        native = supported[f"{component}_native"]
        components[component] = {
            "supported_nodes": int(status.sum()),
            "supported_episodes": int(supported["episode_id"].nunique()),
            "valid_zero_fraction": float((native == 0).mean()) if len(native) else None,
            "rank_variation_status": (
                "SUPPORTED"
                if native.nunique(dropna=True) >= 2
                else "ABSTAIN_NO_RANK_VARIATION"
            ),
        }
    return {
        "total_episode_count": int(base_all["episode_id"].nunique()),
        "total_decision_node_count": int(len(base_all)),
        "active_decision_node_count": int(
            base_all["operational_stage"].ne("COMPLETED").sum()
        ),
        "primary_inherited_support_node_count": int(
            base_all["inherited_support_primary"].eq(True).sum()
        ),
        "sensitivity_inherited_support_node_count": int(
            base_all["inherited_support_sensitivity"].eq(True).sum()
        ),
        "aggregate_complete_node_count": int(
            base_all["aggregate_complete"].eq(True).sum()
        ),
        "base_sample_node_count": int(len(base_sample)),
        "components": components,
        "similar_delay": dict(pair_counts),
        "top10": dict(tie_counts),
    }
