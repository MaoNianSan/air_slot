from __future__ import annotations

from membership_test_data import state_observations, state_request
from src.core.membership import interval_join_partition


def test_state_membership_roles_are_vectorized_with_frozen_precedence() -> None:
    observations = state_observations(
        [
            "2022-05-02 09:30",
            "2022-05-02 10:05",
            "2022-05-02 10:15",
            "2022-05-02 10:25",
        ]
    )
    result = interval_join_partition(
        observations,
        state_request(),
        source="state",
        observation_date="2022-05-02",
    )
    assert result.sort_values("observation_id")["membership_role"].tolist() == [
        "PREDECESSOR_HISTORY",
        "PREDECESSOR_ACTIVE",
        "TURNAROUND_CONTEXT",
        "SUCCESSOR_CONTEXT",
    ]
