"""Contract tests of the post-hoc consequence-domain emphasis views.

The three ``DOMAIN_EMPHASIS_*`` views exist only for the read-only
``CONSEQUENCE_DOMAIN_EMPHASIS_ROBUSTNESS`` stress test. These tests pin the
properties the robustness analysis relies on:

* the primary ``PRIMARY_AGGREGATION_VIEW`` arithmetic is unchanged and stays the
  default, so the sealed Balanced numbers are a regression check rather than a
  validation of refactored primary code;
* each emphasis view reuses the primary view's domain construction exactly and
  differs *only* in the three domain weights;
* the three emphasis vectors are symmetric rotations of one another, are
  non-negative and sum to one, so no single domain is privileged by construction;
* an unknown view is still rejected, and every view keeps the primary
  incomplete-vector contract.
"""

from __future__ import annotations

import pytest

from model.M2.comparison_support import (
    DOMAIN_EMPHASIS_FLIGHT_VIEW,
    DOMAIN_EMPHASIS_PASSENGER_VIEW,
    DOMAIN_EMPHASIS_RESOURCE_VIEW,
    DOMAIN_EMPHASIS_VIEW_WEIGHTS,
    EQUAL_COMPONENT_VIEW,
    PRIMARY_AGGREGATION_VIEW,
    phi_c,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import ContractError


EMPHASIS_VIEWS = (
    DOMAIN_EMPHASIS_FLIGHT_VIEW,
    DOMAIN_EMPHASIS_PASSENGER_VIEW,
    DOMAIN_EMPHASIS_RESOURCE_VIEW,
)

#: A CU vector with seven distinct values; the flight, passenger and operating
#: domain values are then 0.1, 0.6 and 0.7 respectively.
SAMPLE_CU = {
    "F_continuity": 0.0,
    "F_execution": 0.1,
    "F_propagation": 0.2,
    "P_time": 0.5,
    "P_itinerary": 0.6,
    "P_service": 0.7,
    "R_operating": 0.7,
}


def _one_hot(component: str, value: float = 1.0) -> dict[str, float]:
    return {
        name: (value if name == component else 0.0)
        for name in CONSEQUENCE_COMPONENTS
    }


def _domains(cu: dict[str, float]) -> tuple[float, float, float]:
    flight = (
        cu["F_continuity"] + cu["F_execution"] + cu["F_propagation"]
    ) / 3.0
    passenger = (cu["P_time"] + cu["P_itinerary"] + cu["P_service"]) / 3.0
    return flight, passenger, cu["R_operating"]


def test_primary_view_is_the_default_and_keeps_its_arithmetic() -> None:
    signal = phi_c(SAMPLE_CU)
    assert signal == pytest.approx(phi_c(SAMPLE_CU, view=PRIMARY_AGGREGATION_VIEW))
    assert signal == pytest.approx((0.1 + 0.6 + 0.7) / 3.0)

    one_hot_flight = phi_c(_one_hot("F_continuity"))
    one_hot_operating = phi_c(_one_hot("R_operating"))
    assert one_hot_flight == pytest.approx(1 / 9)
    assert one_hot_operating == pytest.approx(1 / 3)


def test_emphasis_weights_are_non_negative_and_balanced() -> None:
    assert set(DOMAIN_EMPHASIS_VIEW_WEIGHTS) == set(EMPHASIS_VIEWS)
    for view, weights in DOMAIN_EMPHASIS_VIEW_WEIGHTS.items():
        assert len(weights) == 3, view
        assert all(weight >= 0.0 for weight in weights), view
        assert sum(weights) == pytest.approx(1.0, abs=1e-12), view
        assert max(weights) == 0.50, view


def test_emphasis_views_are_symmetric_rotations() -> None:
    flight = DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_FLIGHT_VIEW]
    passenger = DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_PASSENGER_VIEW]
    resource = DOMAIN_EMPHASIS_VIEW_WEIGHTS[DOMAIN_EMPHASIS_RESOURCE_VIEW]
    assert flight == (0.50, 0.25, 0.25)
    assert passenger == (0.25, 0.50, 0.25)
    assert resource == (0.25, 0.25, 0.50)
    assert passenger == (flight[2], flight[0], flight[1])
    assert resource == (flight[1], flight[2], flight[0])


@pytest.mark.parametrize("view", EMPHASIS_VIEWS)
def test_emphasis_views_apply_only_the_domain_weights(view: str) -> None:
    """The emphasis value is the weighted sum of the primary domain values."""

    flight, passenger, operating = _domains(SAMPLE_CU)
    weight_flight, weight_passenger, weight_operating = (
        DOMAIN_EMPHASIS_VIEW_WEIGHTS[view]
    )
    expected = (
        weight_flight * flight
        + weight_passenger * passenger
        + weight_operating * operating
    )
    assert phi_c(SAMPLE_CU, view=view) == pytest.approx(expected, abs=1e-15)


def test_equal_weight_limit_agrees_with_the_primary_view() -> None:
    """A weighted expression at (1/3, 1/3, 1/3) agrees with the frozen branch.

    The primary branch is *not* computed through this expression; the check only
    documents that the emphasis generalization is numerically the same mapping at
    equal domain weights (float associativity aside).
    """

    flight, passenger, operating = _domains(SAMPLE_CU)
    combined = (flight + passenger + operating) / 3.0
    assert phi_c(SAMPLE_CU) == pytest.approx(combined, abs=1e-15)


def test_emphasis_one_hot_values() -> None:
    assert phi_c(_one_hot("F_continuity"), view=DOMAIN_EMPHASIS_FLIGHT_VIEW) == (
        pytest.approx(0.50 / 3.0)
    )
    assert phi_c(_one_hot("F_continuity"), view=DOMAIN_EMPHASIS_RESOURCE_VIEW) == (
        pytest.approx(0.25 / 3.0)
    )
    assert phi_c(_one_hot("P_service"), view=DOMAIN_EMPHASIS_PASSENGER_VIEW) == (
        pytest.approx(0.50 / 3.0)
    )
    assert phi_c(_one_hot("R_operating"), view=DOMAIN_EMPHASIS_RESOURCE_VIEW) == (
        pytest.approx(0.50)
    )


def test_emphasis_views_never_change_the_component_contract() -> None:
    for view in (*EMPHASIS_VIEWS, PRIMARY_AGGREGATION_VIEW, EQUAL_COMPONENT_VIEW):
        with pytest.raises(ContractError):
            phi_c({"F_continuity": 1.0}, view=view)
    with pytest.raises(ContractError):
        phi_c(_one_hot("R_operating"), view="NOT_A_VIEW")


def test_emphasis_views_are_not_reachable_by_default() -> None:
    assert phi_c({**SAMPLE_CU}, view=PRIMARY_AGGREGATION_VIEW) == pytest.approx(
        (0.1 + 0.6 + 0.7) / 3.0
    )
    assert phi_c(SAMPLE_CU) == phi_c(SAMPLE_CU, view=PRIMARY_AGGREGATION_VIEW)
