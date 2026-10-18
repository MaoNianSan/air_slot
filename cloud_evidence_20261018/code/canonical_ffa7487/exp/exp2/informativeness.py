"""Component- and domain-level delay informativeness."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import kendall_tau_b
from .protocol import COMPONENTS


def informativeness_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    quantities = [(component, f"{component}_native") for component in COMPONENTS]
    quantities.extend((name, name) for name in ("score_F", "score_P", "score_R"))
    for quantity_id, column in quantities:
        if column not in frame:
            raise ValueError(f"EXP2_INFORMATIVENESS_COLUMN_MISSING:{column}")
        # Exp2B has an estimand-specific population. A component must not
        # inherit Exp2A's seven-component complete-case gate.
        support_column = (
            f"{quantity_id}_status"
            if quantity_id in COMPONENTS and f"{quantity_id}_status" in frame
            else None
        )
        mask = np.isfinite(frame["delay_to_mean"].astype(float)) & np.isfinite(
            frame[column].astype(float)
        )
        if support_column is not None:
            mask &= frame[support_column].astype(str).str.startswith("SUPPORTED")
        if "support_primary" in frame:
            mask &= frame["support_primary"].eq(True)
        sample = frame.loc[mask].copy()
        estimate = kendall_tau_b(sample["delay_to_mean"], sample[column])
        rows.append(
            {
                "quantity_id": quantity_id,
                "estimate": estimate,
                "ci_low": None,
                "ci_high": None,
                "n_nodes": int(len(sample)),
                "n_episodes": int(sample["episode_id"].nunique()),
                "population_rule": "FINITE_SUPPORT_APPLICABLE_PER_COMPONENT_OR_DOMAIN",
                "support_population": (
                    "COMPONENT_SPECIFIC" if support_column is not None else "DOMAIN_COMPLETE"
                ),
                "support_status": (
                    "SUPPORTED" if estimate is not None else "ABSTAIN_NO_RANK_VARIATION"
                ),
            }
        )
    return pd.DataFrame(rows)


def informativeness_population(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the union of Exp2B estimand-specific eligible rows.

    The returned frame is intentionally not the Exp2A complete-case sample.
    Each quantity is filtered again inside ``informativeness_table``.
    """
    required = {"episode_id", "delay_to_mean"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"EXP2_INFORMATIVENESS_POPULATION_COLUMNS_MISSING:{missing}")
    return frame.loc[
        frame["support_primary"].eq(True)
        & np.isfinite(frame["delay_to_mean"].astype(float))
    ].copy()
