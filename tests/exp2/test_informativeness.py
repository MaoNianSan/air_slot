import pandas as pd
import pytest

from exp.exp2.informativeness import informativeness_table
from exp.exp2.protocol import COMPONENTS


def _frame():
    rows = []
    for index in range(4):
        row = {
            "episode_id": f"e{index // 2}",
            "delay_to_mean": float(index),
            "score_F": float(index),
            "score_P": float(index),
            "score_R": float(index),
        }
        for component in COMPONENTS:
            row[f"{component}_native"] = float(index)
        rows.append(row)
    return pd.DataFrame(rows)


def test_component_kendall_uses_native_and_positive_scale_does_not_change_rank():
    frame = _frame()
    base = informativeness_table(frame).set_index("quantity_id")
    frame["F_continuity_native"] *= 1000
    changed = informativeness_table(frame).set_index("quantity_id")
    assert (
        base.loc["F_continuity", "estimate"]
        == changed.loc["F_continuity", "estimate"]
        == pytest.approx(1)
    )


def test_constant_component_abstains_and_na_is_not_zero():
    frame = _frame()
    frame["P_service_native"] = 0.0
    frame.loc[0, "P_itinerary_native"] = None
    result = informativeness_table(frame).set_index("quantity_id")
    assert result.loc["P_service", "support_status"] == "ABSTAIN_NO_RANK_VARIATION"
    assert result.loc["P_service", "estimate"] is None or pd.isna(
        result.loc["P_service", "estimate"]
    )
    assert result.loc["P_itinerary", "n_nodes"] == 3
    assert result.loc["P_itinerary", "n_episodes"] == 2
