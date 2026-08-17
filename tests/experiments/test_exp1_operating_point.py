import pytest
import torch

from exp.exp1.development.warning_evaluation import (
    _decision_window_gain,
    _paired_episode_diagnostics,
    _paired_node_diagnostics,
)
from exp.exp1.metrics import episode_operating_point, select_threshold


def _row(episode, lead, probability, *, positive=False, support="SUPPORTED"):
    return {
        "episode_id": episode,
        "lead_time_minutes": lead,
        "warning_probability": probability,
        "warning_support_state": support,
        "realized_event_positive": positive,
    }


def test_abstain_breaks_sustained_warning_continuity():
    rows = (
        _row("e", 15, 0.9),
        _row("e", 10, None, support="ABSTAIN"),
        _row("e", 5, 0.9),
    )
    result = episode_operating_point(rows, probability_key="warning_probability", threshold=0.5)
    assert not result["evaluable"]
    assert not result["sustained_warning"]


def test_threshold_selection_uses_episode_level_sustained_fpr():
    rows = (
        _row("n1", 10, 0.8), _row("n1", 5, 0.8),
        _row("n2", 10, 0.4), _row("n2", 5, 0.4),
        _row("n3", 10, 0.1), _row("n3", 5, 0.1),
        _row("p1", 10, 0.9, positive=True), _row("p1", 5, 0.9, positive=True),
    )
    selected = select_threshold(
        rows, probability_key="warning_probability", target_fpr=1 / 3, scenario_count=10)
    assert selected["threshold"] == 0.5
    assert selected["achieved_fpr"] == 1 / 3
    assert selected["negative_evaluable_n"] == 3


def test_threshold_selection_restores_float32_scenario_counts():
    scenarios = 250
    scores = [100 / scenarios] + [91 / scenarios] * 10 + [90 / scenarios] * 89
    rows = []
    for index, score in enumerate(scores):
        stored = torch.tensor(score, dtype=torch.float32).item()
        rows.extend(
            (
                _row(f"n{index}", 10, stored),
                _row(f"n{index}", 5, stored),
            )
        )

    selected = select_threshold(
        rows,
        probability_key="warning_probability",
        target_fpr=0.11,
        scenario_count=scenarios,
    )

    assert selected["threshold"] == 91 / scenarios
    assert selected["achieved_fpr"] == 0.11


def test_paired_sensitivity_reports_probability_classification_and_gain_changes():
    principal_nodes = {
        ("e1", "n1"): (0.3, "SUPPORTED"),
        ("e1", "n2"): (0.5, "SUPPORTED"),
    }
    sensitivity_nodes = {
        ("e1", "n1"): (0.4, "SUPPORTED"),
        ("e1", "n2"): (0.3, "SUPPORTED"),
    }
    nodes = _paired_node_diagnostics(
        principal_nodes,
        sensitivity_nodes,
        threshold=0.4,
    )
    assert nodes["supported_probability_pair_count"] == 2
    assert nodes["node_warning_classification_disagreement_count"] == 2
    assert nodes["mean_absolute_probability_change"] == pytest.approx(0.15)

    principal_status = {
        "e1": {"evaluable": True, "sustained_warning": False,
               "realized_event_positive": True}
    }
    sensitivity_status = {
        "e1": {"evaluable": True, "sustained_warning": True,
               "realized_event_positive": True}
    }
    episodes = _paired_episode_diagnostics(principal_status, sensitivity_status)
    assert episodes["sustained_warning_classification_disagreement_count"] == 1
    assert episodes["sustained_warning_classification_disagreement_rate"] == 1.0

    gain = _decision_window_gain({"e1": 30.0}, {"e1": 10.0})
    assert gain["DecisionWindowGain"] == 20.0
    assert gain["share_ge_15"] == 1.0
