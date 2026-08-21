from exp.exp3.protocol import EXP3_VARIANTS
from exp.exp3.runner import Exp3Runner


def test_exp3_owns_refresh_and_state_vintage_only():
    assert EXP3_VARIANTS == (
        "EXP3A_ONE_SHOT", "EXP3A_ROLLING", "EXP3B_SYNC",
        "EXP3B_STATE_LAG_5", "EXP3B_STATE_LAG_10",
    )
    assert "FormalCoverage" not in Exp3Runner.headline_metrics


def test_exp3_fast_preserves_no_rolling_novelty_claim():
    results = Exp3Runner().execute_fast()
    assert len(results) == 5
    assert all(item.provenance["rolling_novelty_claim"] is False for item in results)
    assert all(item.final_test_access_count == 0 for item in results)
