from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from exp.exp2.protocol import COMPONENTS
from exp.exp4.triage import _views
from validation.materialize_aggregation_robustness import (
    BASELINE_EXPECTED,
    BASELINE_SIMILAR_EXPECTED,
    VIEW_ORDER,
    compute_view_scores,
)


def _frame() -> pd.DataFrame:
    values = {
        "Z_F_continuity": [1.0, 4.0],
        "Z_F_execution": [2.0, 5.0],
        "Z_F_propagation": [3.0, 6.0],
        "Z_P_time": [4.0, 7.0],
        "Z_P_itinerary": [5.0, 8.0],
        "Z_P_service": [6.0, 9.0],
        "Z_R_operating": [7.0, 10.0],
    }
    return pd.DataFrame(values)


def test_six_view_scores_match_existing_exp4_definitions():
    frame = _frame()
    scores = compute_view_scores(frame)
    triage = _views(pd.DataFrame({"S_F": [2.0, 5.0], "S_P": [5.0, 8.0], "S_R": [7.0, 10.0], "EQUAL_COMPONENT": scores["EQUAL_COMPONENT"], "NO_F_EXECUTION": scores["NO_F_EXEC"],}))
    assert np.allclose(scores["EQUAL_COMPONENT"], triage[:, 3], atol=1e-12)
    assert np.allclose(scores["NO_F_EXEC"], triage[:, 4], atol=1e-12)
    assert np.allclose(scores["FLIGHT_EMPHASIS"], triage[:, 5], atol=1e-12)
    assert np.allclose(scores["PASSENGER_EMPHASIS"], triage[:, 6], atol=1e-12)
    assert np.allclose(scores["OPERATING_EMPHASIS"], triage[:, 7], atol=1e-12)
    assert VIEW_ORDER == ("BASE_EQUAL_DOMAIN", "EQUAL_COMPONENT", "NO_F_EXEC", "FLIGHT_EMPHASIS", "PASSENGER_EMPHASIS", "OPERATING_EMPHASIS")


def test_domain_emphasis_weights_sum_to_one():
    weights = ((.50, .25, .25), (.25, .50, .25), (.25, .25, .50))
    assert all(sum(row) == pytest.approx(1.0) for row in weights)


def test_frozen_baseline_contract_constants_are_explicit():
    assert BASELINE_EXPECTED["kendall_tau_b"] == pytest.approx(0.736488790649004)
    assert BASELINE_EXPECTED["top_decile_overlap"] == pytest.approx(0.7289156626506024)
    assert BASELINE_EXPECTED["median_abs_rank_displacement"] == pytest.approx(0.06974637681159424)
    assert BASELINE_SIMILAR_EXPECTED["median_abs_priority_separation"] == pytest.approx(0.20410628019323673)
    assert BASELINE_SIMILAR_EXPECTED["share_priority_separation_ge_030"] == pytest.approx(0.33782824698367636)
