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
