"""Contract tests for the Exp4 per-node records materialization."""

from exp.exp4.per_node_records import (
    LEAD_TIME_BINS,
    METHODS,
    _episode_bootstrap,
    _finite_discrete_crps,
    _lead_time_bin,
    _lead_time_for,
)


def test_lead_bin_floor_semantics():
    assert _lead_time_bin(None) is None
    assert _lead_time_bin(0.0) == 0
    assert _lead_time_bin(30.0) == 30
    assert _lead_time_bin(45.0) == 30
    assert _lead_time_bin(420.0) == 420
    assert _lead_time_bin(480.0) == 480
    assert _lead_time_bin(600.0) == 480


def test_lead_time_rules_per_target():
    assert _lead_time_for("T_IB_A00", 7.0, None, None) == (
        7.0, "REALIZED_REMAINING_MINUTES",
    )
    assert _lead_time_for("T_IB_A00", None, None, None) == (
        None, "NA_NO_OBSERVED_REMAINING_MINUTES",
    )
    assert _lead_time_for("D_TX", 0.0, None, None) == (
        None, "NA_NO_PLANNED_WHEELS_OFF",
    )
    pre = {
        "successor_state": {
            "schedule_reference": {
                "support_state": "SUPPORTED",
                "value": {"scheduled_departure_utc": "2019-08-16T21:00:00Z"},
            }
        }
    }
    lead, source = _lead_time_for("D_OB", None, pre, "2019-08-16T20:15:00Z")
    assert source == "PLANNED_SCHEDULE_HORIZON"
    assert lead == 45.0


def test_finite_discrete_crps_degenerate():
    assert _finite_discrete_crps([5.0], [1.0], 5.0) == 0.0
    assert _finite_discrete_crps([5.0], [1.0], 8.0) == 3.0


def test_episode_bootstrap_deterministic_and_episode_level():
    first = _episode_bootstrap({"a": 1.0, "b": 3.0, "c": 5.0}, replicates=200, seed=7)
    second = _episode_bootstrap({"a": 1.0, "b": 3.0, "c": 5.0}, replicates=200, seed=7)
    assert first == second
    assert first["estimate"] == 3.0
    assert first["n_episodes"] == 3
    assert _episode_bootstrap({}) is None


def test_methods_and_bins_contract():
    assert METHODS == ("HISTORICAL", "LIGHTGBM", "RANDOM_FOREST", "STATE_AWARE_H32")
    assert LEAD_TIME_BINS == (0, 30, 60, 120, 180, 240, 300, 360, 420, 480)
