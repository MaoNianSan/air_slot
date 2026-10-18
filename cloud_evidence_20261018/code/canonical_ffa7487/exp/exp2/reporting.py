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
        status = base_all[f"{component}_status"].isin(
            ("SUPPORTED", "SUPPORTED_CONDITIONAL")
        )
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
    active = base_all.loc[base_all["operational_stage"].ne("COMPLETED")].copy()
    mass = active["common_support_mass"].astype(float)
    support_groups = {}
    for name, column in (
        ("primary_90", "support_primary"),
        ("sensitivity_50", "support_sensitivity"),
        ("full_support_100", "support_full"),
    ):
        subset = active.loc[active[column].eq(True)]
        support_groups[name] = {
            "n_nodes": int(len(subset)),
            "n_episodes": int(subset["episode_id"].nunique()),
        }
    unsupported = {}
    for reason in ("D_TO", *COMPONENTS):
        column = f"unsupported_scenario_count_{reason}"
        unsupported[reason] = (
            int(active[column].sum()) if column in active else None
        )
    return {
        "total_episode_count": int(base_all["episode_id"].nunique()),
        "total_decision_node_count": int(len(base_all)),
        "active_decision_node_count": int(
            base_all["operational_stage"].ne("COMPLETED").sum()
        ),
        "common_support_mass": {
            "min": float(mass.min()) if len(mass) else None,
            "p10": float(mass.quantile(0.10)) if len(mass) else None,
            "median": float(mass.median()) if len(mass) else None,
            "p90": float(mass.quantile(0.90)) if len(mass) else None,
            "max": float(mass.max()) if len(mass) else None,
        },
        **support_groups,
        "support_bands": {
            "lt_0_50": int((mass < 0.50).sum()),
            "ge_0_50_lt_0_90": int(((mass >= 0.50) & (mass < 0.90)).sum()),
            "ge_0_90_lt_1_00": int(((mass >= 0.90) & (mass < 1.0)).sum()),
            "eq_1_00": int(mass.eq(1.0).sum()),
        },
        "conditional_aggregate_complete_node_count": int(
            active["conditional_aggregate_complete"].eq(True).sum()
        ),
        "formal_full_support_node_count": int(
            active["formal_full_support"].eq(True).sum()
        ),
        "base_sample_node_count": int(len(base_sample)),
        "scenario_level_unsupported_reason_counts": unsupported,
        "components": components,
        "similar_delay": dict(pair_counts),
        "top10": dict(tie_counts),
    }
