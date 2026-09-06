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
        sample = frame.loc[
            np.isfinite(frame["delay_to_mean"].astype(float))
            & np.isfinite(frame[column].astype(float))
        ]
        estimate = kendall_tau_b(sample["delay_to_mean"], sample[column])
        rows.append(
            {
                "quantity_id": quantity_id,
                "estimate": estimate,
                "ci_low": None,
                "ci_high": None,
                "n_nodes": int(len(sample)),
                "n_episodes": int(sample["episode_id"].nunique()),
                "support_status": (
                    "SUPPORTED" if estimate is not None else "ABSTAIN_NO_RANK_VARIATION"
                ),
            }
        )
    return pd.DataFrame(rows)
