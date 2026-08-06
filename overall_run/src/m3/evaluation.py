from __future__ import annotations

from itertools import combinations
from typing import Any, Mapping

import numpy as np
import pandas as pd

from .artifact import M3Artifact
from .contracts import SUBITEMS_M2_V2, M3ContractBundle
from .footprint import footprint_counts
from .sampling import generate_test_fixture_library


def evaluate_m3_structure(
    contract: M3ContractBundle,
    artifact: M3Artifact,
) -> dict[str, Any]:
    duplicate_pairs = []
    for left, right in combinations(contract.catalog, 2):
        left_roles = tuple(contract.footprints[left].roles[name] for name in SUBITEMS_M2_V2)
        right_roles = tuple(contract.footprints[right].roles[name] for name in SUBITEMS_M2_V2)
        if left_roles == right_roles:
            duplicate_pairs.append(f"{left}:{right}")
    return {
        "M3_EVALUATION_SCIENTIFIC_STATUS": "STRUCTURE_ONLY",
        "A00_identity": bool(
            np.all(artifact.subitem_recovery_rates["A00"] == 0.0)
            and np.all(artifact.implementation_costs_rmb["A00"] == 0.0)
        ),
        "structural_none_exactness": bool(artifact.response_audit["structural_none_exact"].all()),
        "recovery_bounds": bool(
            all(
                np.all((values >= 0.0) & (values <= 1.0))
                for values in artifact.subitem_recovery_rates.values()
            )
        ),
        "cost_nonnegativity": bool(
            all(np.all(values >= 0.0) for values in artifact.implementation_costs_rmb.values())
        ),
        "action_coverage": len(artifact.action_catalog) == len(contract.catalog),
        "subitem_coverage": tuple(artifact.footprint_table["subitem_id"].drop_duplicates()) == SUBITEMS_M2_V2,
        "footprint_sparsity": bool(footprint_counts(contract)["nonzero_count"].le(4).all()),
        "near_duplicate_actions": duplicate_pairs,
        "M2_compatibility": artifact.m2_compatibility.get("status") == "PASS",
        "parameter_readiness": "NOT_READY",
        "M4_status": "BLOCKED",
    }


def sample_count_stability(
    contract: M3ContractBundle,
    m2_contract: Mapping[str, Any] | Any,
    *,
    draw_counts: tuple[int, ...] = (100, 500, 1000, 2000),
    base_seed: int | None = None,
) -> pd.DataFrame:
    seed = contract.base_seed if base_seed is None else int(base_seed)
    rows = []
    for draw_count in draw_counts:
        artifact = generate_test_fixture_library(
            contract,
            n_draws=draw_count,
            base_seed=seed,
            m2_contract=m2_contract,
        )
        nonnull = [
            values.mean()
            for action_id, values in artifact.response_intensities.items()
            if action_id != "A00"
        ]
        rows.append({
            "response_draw_count": draw_count,
            "mean_response_intensity": float(np.mean(nonnull)),
            "mean_failure_rate": float(
                artifact.response_audit.loc[
                    artifact.response_audit["action_id"].ne("A00"), "empirical_failure_rate"
                ].mean()
            ),
            "sample_hash": artifact.sample_hash,
        })
    return pd.DataFrame(rows)
