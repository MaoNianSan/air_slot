"""Freeze F3 contract tests (2026-08-25): Exp3B vintage exclusion.

LAG_5 / LAG_10 take only the frozen state identity of the past node at
t - delta; a node without a legal vintage is typed-excluded with
EXP3B_VINTAGE_NOT_AVAILABLE and never falls back to the current or most
recent state.  CONTRACT_FAST only; reads the shared Development context.
"""

import pytest

from exp.common.real_fast import state_vintage_bindings
from exp.common.context import real_fast_context
from exp.exp3.runner import Exp3Runner
from exp.exp3.protocol import EXP3B_STATE_LAG_5, EXP3B_STATE_LAG_10
from exp.common.result_schema import SupportStatus


def test_exp3b_lag_excludes_nodes_without_legal_vintage():
    context = real_fast_context()
    lagged = state_vintage_bindings(context, lag_minutes=5)
    assert lagged
    assert any(item["state_vintage_node_id"] is None for item in lagged)
    for item in lagged:
        assert item["current_state_read"] is False


def test_exp3b_runner_reports_typed_exclusion_without_fallback():
    context = real_fast_context()
    results = {item.variant_id: item for item in Exp3Runner().execute_real_fast(context=context)}
    for variant_id in (EXP3B_STATE_LAG_5, EXP3B_STATE_LAG_10):
        metric = results[variant_id].metrics["STATE_VINTAGE_COVERAGE"]
        assert metric.support_status is SupportStatus.SUPPORTED
        assert metric.metadata["vintage_identity_rule"] == "FROZEN_PRIOR_STATE_IDENTITY_NO_REEVALUATION_NO_INTERPOLATION"
        assert metric.metadata["vintage_match_rule"] == "EXACT_DECISION_TIME_T_MINUS_DELTA"
        assert metric.metadata["vintage_fallback_policy"] == "FORBIDDEN"
        assert metric.metadata["exclusion_code"] == "EXP3B_VINTAGE_NOT_AVAILABLE"
        assert metric.metadata["excluded_node_count"] >= 1
        assert metric.metadata["fallback_to_current_state"] is False
        assert metric.metadata["current_state_read"] is False
