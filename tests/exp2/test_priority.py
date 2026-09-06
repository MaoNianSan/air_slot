import numpy as np
import pandas as pd
import pytest

from exp.exp2.metrics import (
    kendall_tau_b,
    midrank_percentiles,
    priority_metrics,
    top_k_ids,
)
from exp.exp2.priority import add_domain_scores
from exp.exp2.protocol import COMPONENTS


def test_perfect_agreement_and_reversal():
    assert kendall_tau_b([1, 2, 3], [1, 2, 3]) == pytest.approx(1)
    assert kendall_tau_b([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)


def test_ties_use_tau_b_and_midrank():
    assert kendall_tau_b([1, 1, 2], [1, 2, 3]) == pytest.approx(0.816496580927726)
    ranks = midrank_percentiles([1, 1, 3, 4])
    assert ranks[0] == ranks[1] == pytest.approx(0.25)


def test_displacement_is_symmetric_and_bounded():
    forward = priority_metrics([1, 2, 3, 4], [4, 2, 3, 1], list("abcd"))
    reverse = priority_metrics([4, 2, 3, 1], [1, 2, 3, 4], list("abcd"))
    assert forward["median_rank_displacement"] == reverse["median_rank_displacement"]
    assert 0 <= forward["p90_rank_displacement"] <= 1


def test_equal_domain_aggregation_is_exact_and_not_seven_component_sum():
    row = {f"Z_{component}": 0.0 for component in COMPONENTS}
    row.update(
        Z_F_continuity=3.0,
        Z_F_execution=6.0,
        Z_F_propagation=9.0,
        Z_P_time=2.0,
        Z_P_itinerary=4.0,
        Z_P_service=6.0,
        Z_R_operating=12.0,
    )
    result = add_domain_scores(pd.DataFrame([row])).iloc[0]
    assert result["score_F"] == 6
    assert result["score_P"] == 4
    assert result["score_R"] == 12
    assert result["score_C"] == pytest.approx(22 / 3)
    assert result["score_C"] != sum(row.values())


def test_top10_boundary_tie_is_deterministic_by_technical_id_only():
    selected, tie_count = top_k_ids([10, 10, 10, 1], ["c", "a", "b", "d"], 0.25)
    assert selected == ("a",)
    assert tie_count == 3
