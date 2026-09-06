from __future__ import annotations

import pandas as pd
import pytest

from exp.shared.support import (
    COMMON_SUPPORT_050,
    COMMON_SUPPORT_090,
    FULL,
    apply_node_support_policy,
    policy,
)


def test_support_policy_ids_are_explicit():
    assert policy("FULL") == FULL
    assert policy("COMMON_SUPPORT_CONDITIONAL_090") == COMMON_SUPPORT_090
    assert policy("COMMON_SUPPORT_CONDITIONAL_050") == COMMON_SUPPORT_050


def test_apply_support_policy_does_not_mutate_source():
    source = pd.DataFrame({"node": ["a", "b"], "common_support_mass": [1.0, 0.5]})
    original = source.copy(deep=True)
    result = apply_node_support_policy(
        source, support_policy=COMMON_SUPPORT_090
    )
    pd.testing.assert_frame_equal(source, original)
    assert result["support_policy_id"].tolist() == [
        "COMMON_SUPPORT_CONDITIONAL_090",
        "COMMON_SUPPORT_CONDITIONAL_090",
    ]
    assert result["support_policy_eligible"].tolist() == [True, False]


def test_empty_support_view_is_typed_ineligible():
    result = apply_node_support_policy(
        pd.DataFrame({"common_support_mass": pd.Series(dtype=float)}),
        support_policy=FULL,
    )
    assert result.empty
    assert result["support_policy_eligible"].dtype == bool


def test_invalid_support_mass_is_rejected():
    with pytest.raises(ValueError, match="SHARED_SUPPORT_MASS_INVALID"):
        apply_node_support_policy(
            pd.DataFrame({"common_support_mass": [1.1]}),
            support_policy=FULL,
        )
