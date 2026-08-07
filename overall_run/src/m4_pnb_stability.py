from __future__ import annotations

LEGACY_M4_NOT_FORMAL = True

from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_contract import (
    AUDIT_SEED_NAMESPACE, CHANNELS, NEAR_Q_TOLERANCE, FrozenInputs,
)
from .m4_pnb_formula import generate_audit_m3_library, manual_pnb_reconstruction
from .utils import stable_hash


def build_mc_stability(
    frozen: FrozenInputs,
    frame: pd.DataFrame,
    snapshot: pd.DataFrame,
    n_samples: int = 4096,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    formal_samples = len(frozen.sample_ids)
    if n_samples % formal_samples:
        raise ValueError("PNB_MC_AUDIT_BUDGET_MUST_MULTIPLE_FORMAL_SAMPLES")
    repeats = n_samples // formal_samples
    base_seed = int(frozen.config["random_seed"])
    libraries = [
        generate_audit_m3_library(
            frozen.m3_parameters, n_samples, base_seed, replicate=replicate
        )
        for replicate in (0, 1)
    ]
    snapshot_index = {
        str(value): index
        for index, value in enumerate(frozen.summary["snapshot_id"].astype(str))
    }
    b0 = float(frozen.config["m4"]["decision_value"]["burden_ratio_max"])
    q0 = float(
        frozen.config["m4"]["decision_value"]["positive_net_benefit_probability_min"]
    )
    rows: list[dict[str, Any]] = []
    for record in frame.itertuples(index=False):
        index = snapshot_index[str(record.snapshot_id)]
        pre = {
            channel: np.tile(frozen.costs_rmb[channel][index], repeats)
            for channel in CHANNELS
        }
        audit_results = []
        for recovery, implementation, _ in libraries:
            audit_results.append(
                manual_pnb_reconstruction(
                    pre,
                    {
                        channel: recovery[record.action_id][:, channel_index]
                        for channel_index, channel in enumerate(CHANNELS)
                    },
                    {
                        channel: implementation[record.action_id][:, channel_index]
                        for channel_index, channel in enumerate(CHANNELS)
                    },
                )
            )
        first, second = audit_results
        q256 = float(record.positive_net_benefit_probability)
        q4096 = float(first["positive_net_benefit_probability"])
        q4096_second = float(second["positive_net_benefit_probability"])
        gate256 = q256 >= q0
        gate4096 = q4096 >= q0
        decision4096 = bool(
            first["burden_ratio"] <= b0
            and gate4096
        )
        candidate4096 = bool(record.physical_feasible and decision4096)
        rows.append(
            {
                "episode_id": record.episode_id,
                "snapshot_id": record.snapshot_id,
                "stage": record.stage,
                "action_id": record.action_id,
                "action_family": record.action_family,
                "cost_stratum": record.cost_stratum,
                "q_256": q256,
                "q_4096": q4096,
                "q_4096_second_seed": q4096_second,
                "absolute_difference": abs(q4096 - q256),
                "between_audit_seed_absolute_difference": abs(q4096_second - q4096),
                "gate_256": gate256,
                "gate_4096": gate4096,
                "gate_4096_second_seed": q4096_second >= q0,
                "gate_flip": gate256 != gate4096,
                "audit_seed_gate_flip": (q4096 >= q0) != (q4096_second >= q0),
                "near_threshold": abs(q256 - q0) <= NEAR_Q_TOLERANCE,
                "recovery_ratio_4096": first["recovery_ratio"],
                "burden_ratio_4096": first["burden_ratio"],
                "decision_value_pass_4096": decision4096,
                "final_candidate_256": bool(record.final_candidate),
                "final_candidate_4096": candidate4096,
                "candidate_flip": bool(record.final_candidate) != candidate4096,
                "audit_seed_namespace": AUDIT_SEED_NAMESPACE,
                "formal_samples": formal_samples,
                "audit_samples": n_samples,
            }
        )
    result = pd.DataFrame(rows)
    differences = result["absolute_difference"]
    near = result[result["near_threshold"]]
    action_flip = (
        result.groupby("action_id", observed=True)["gate_flip"].mean().to_dict()
    )
    snapshot_candidate_flip = result.groupby("snapshot_id", observed=True)[
        "candidate_flip"
    ].any()
    summary = {
        "formal_samples": formal_samples,
        "audit_samples": n_samples,
        "audit_seed_namespace": AUDIT_SEED_NAMESPACE,
        "audit_seed_hash": stable_hash(base_seed, AUDIT_SEED_NAMESPACE, 0, n_samples),
        "mean_absolute_difference": float(differences.mean()),
        "median_absolute_difference": float(differences.median()),
        "q90_absolute_difference": float(differences.quantile(0.90)),
        "q95_absolute_difference": float(differences.quantile(0.95)),
        "gate_flip_rate": float(result["gate_flip"].mean()),
        "gate_flip_count": int(result["gate_flip"].sum()),
        "action_level_gate_flip_rate": action_flip,
        "near_threshold_support": int(len(near)),
        "near_threshold_gate_flip_rate": float(near["gate_flip"].mean()) if len(near) else 0.0,
        "snapshot_candidate_set_potential_difference_count": int(
            snapshot_candidate_flip.sum()
        ),
        "snapshot_candidate_set_potential_difference_rate": float(
            snapshot_candidate_flip.mean()
        ),
        "second_seed_gate_flip_rate": float(result["audit_seed_gate_flip"].mean()),
        "second_seed_gate_flip_count": int(result["audit_seed_gate_flip"].sum()),
        "mean_between_audit_seed_absolute_difference": float(
            result["between_audit_seed_absolute_difference"].mean()
        ),
        "m2_expansion": "each frozen 256-draw M2 empirical cost vector repeated 16 times",
    }
    return result, summary


