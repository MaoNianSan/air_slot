"""Contract tests for the Exp3 valuation-only materialization (F4/F5)."""

from exp.exp3.valuation_only import (
    MONETARY_BAND_RULE,
    RESPONSE_FREEZE_RULE,
    SAFETY,
    VALUATION_RECORD_SCHEMA,
    _weighted_mean,
)


def test_valuation_only_schema_columns():
    names = VALUATION_RECORD_SCHEMA.names
    assert names[0] == "episode_id"
    assert "valuation_band" in names
    assert "response_band" in names
    assert "response_freeze_rule" in names
    assert "claim_status" in names
    assert "authoritative" in names
    assert "conditional_residual_risk" in names


def test_valuation_only_freezes_response_at_base_and_monetary_only():
    assert RESPONSE_FREEZE_RULE == "F4_FROZEN_DECLARED_RESPONSE_PARAMETERS_BASE_FOR_ALL_BANDS"
    assert MONETARY_BAND_RULE == "F5_MONETARY_COEFFICIENTS_ONLY_0_5X_1_0X_2_0X"


def test_valuation_only_safety_all_zero():
    assert SAFETY["FINAL_TEST_ACCESS_COUNT"] == 0
    assert SAFETY["PAPER_FULL_RUN"] is False
    assert SAFETY["EXP3_RUNS"] == 0
    assert SAFETY["AUTHORITATIVE_RANKING"] is False


def test_weighted_mean():
    assert _weighted_mean([1.0, 3.0], [1.0, 3.0]) == 2.5
    assert _weighted_mean([], []) is None
