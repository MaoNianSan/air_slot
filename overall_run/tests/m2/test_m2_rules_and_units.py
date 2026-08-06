from __future__ import annotations

from dataclasses import replace

import pytest

from overall_run.src.m2 import build_m2_input, reconstruct_pre_action_loss
from overall_run.src.m2.contracts import PassengerContext, ResourceContext, ValuationContext
from overall_run.src.m2.evaluation import audit_sample_losses
from overall_run.src.m2.rules import continuous, excess, piecewise, threshold
from overall_run.src.m2.subitem_values import value_for


VALUES = {name: 1.0 for name in (
    "F_TURN", "F_WAIT", "F_PROPAGATION", "P_DELAY", "P_CONNECTION",
    "P_CARE", "R_GROUND", "R_TAXI", "R_SCARCITY",
)}
RULES = {
    "P_CARE": {"threshold_minutes": 60.0},
    "R_GROUND": {"context_gamma": 0.5},
    "R_TAXI": {"context_gamma": 0.5},
    "R_SCARCITY": {"wait_threshold_minutes": 30.0},
}


def _valuation(rates=None):
    return ValuationContext(
        subitem_value_parameters=VALUES,
        rule_parameters=RULES,
        valuation_version="TEST_VALUES_V1",
        channel_rates=rates or {"F": 1.0, "P": 1.0, "R": 1.0},
    )


def _passenger():
    return PassengerContext(100.0, 0.5, 20.0, 0.2, "OFFICIAL_OPERATIONAL")


def _resource():
    return ResourceContext(0.5, 0.5, 0.5, 0.5, "OFFICIAL_OPERATIONAL")


def test_rule_library_is_nonnegative_monotone_and_complexity_bounded() -> None:
    grid = (0.0, 10.0, 20.0, 40.0)
    for function in (
        lambda value: continuous(value, 2.0),
        lambda value: excess(value, 5.0, 2.0),
        lambda value: piecewise(value, (1.0, 0.5, 0.25), (10.0, 30.0)),
        lambda value: threshold(value, 15.0, 2.0),
    ):
        values = tuple(function(value) for value in grid)
        assert all(value >= 0.0 for value in values)
        assert values == tuple(sorted(values))
    with pytest.raises(ValueError, match="M2_RULE_COMPLEXITY_LIMIT"):
        piecewise(20.0, (1.0, 1.0, 1.0, 1.0), (5.0, 10.0, 15.0))


def test_missing_subitem_value_is_not_silently_zero() -> None:
    with pytest.raises(ValueError, match="M2_VALUE_PARAMETER_NOT_CONFIGURED"):
        value_for("F_TURN", ValuationContext())


def test_currency_mapping_changes_only_currency_layer(m1_scenario_factory) -> None:
    scenario = m1_scenario_factory()
    base = reconstruct_pre_action_loss(build_m2_input(
        scenario, passenger_context=_passenger(), resource_context=_resource(),
        valuation_context=_valuation(),
    ))[0]
    changed = reconstruct_pre_action_loss(build_m2_input(
        scenario, passenger_context=_passenger(), resource_context=_resource(),
        valuation_context=_valuation({"F": 2.0, "P": 1.0, "R": 1.0}),
    ))[0]
    assert base.quantities == changed.quantities
    assert base.constructed_units == changed.constructed_units
    assert changed.flight_loss_rmb == 2.0 * base.flight_loss_rmb
    assert audit_sample_losses((base,)) == {
        "nonnegative": True, "currency_identity": True, "total_additivity": True,
    }


def test_input_row_order_does_not_change_results(m1_scenario_factory) -> None:
    scenario = m1_scenario_factory()
    reversed_scenario = replace(scenario, joint_samples=tuple(reversed(scenario.joint_samples)))
    first = reconstruct_pre_action_loss(build_m2_input(
        scenario, passenger_context=_passenger(), resource_context=_resource(),
        valuation_context=_valuation(),
    ))
    second = reconstruct_pre_action_loss(build_m2_input(
        reversed_scenario, passenger_context=_passenger(), resource_context=_resource(),
        valuation_context=_valuation(),
    ))
    assert first == second
