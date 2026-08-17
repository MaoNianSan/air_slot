import pytest

from validation.data2_v5_wstar_development import (
    SECONDARY_TRAINING_SEEDS,
    recommend_window,
)


def test_secondary_w_seeds_use_frozen_v5_sequence_prefix():
    assert SECONDARY_TRAINING_SEEDS == (20260813, 20260814, 20260815)


def test_w_recommendation_prefers_shorter_equivalent_history():
    raw_best, recommendation, relative, equivalent = recommend_window({
        30: 4.05,
        60: 4.018,
        120: 4.0,
        180: 4.03,
    })
    assert raw_best == 120
    assert recommendation == 60
    assert relative[60] == pytest.approx(0.0045)
    assert equivalent == {30: False, 60: True, 120: True, 180: False}


def test_w_recommendation_keeps_raw_best_when_shorter_is_not_equivalent():
    raw_best, recommendation, _, equivalent = recommend_window({
        30: 4.1,
        60: 4.04,
        120: 4.0,
        180: 4.02,
    })
    assert raw_best == 120
    assert recommendation == 120
    assert equivalent[60] is False
