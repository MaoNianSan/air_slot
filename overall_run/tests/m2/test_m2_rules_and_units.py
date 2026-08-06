from __future__ import annotations

from dataclasses import replace

import pytest

from overall_run.src.m2 import build_m2_input, reconstruct_pre_action_loss
from overall_run.src.m2.contracts import ParameterStatus, ValuationContext
from overall_run.src.m2.corrections import apply_constructed_unit_correction
from overall_run.src.m2.currency import to_rmb
from overall_run.src.m2.evaluation import audit_sample_losses
from overall_run.src.m2.rules import bounded_multiplier, continuous, excess, piecewise, threshold
from overall_run.src.m2.subitem_values import value_for


VALUES = {
    name: 1.0
    for name in (
        "F_TURN",
        "F_WAIT",
        "F_PROPAGATION",
        "P_DELAY",
        "P_CONNECTION",
        "P_CARE",
        "R_GROUND",
        "R_TAXI",
        "R_SCARCITY",
    )
}


def _multiplier_rule(rule_type: str) -> dict[str, object]:
    return {
        "rule_type": rule_type,
        "context_gamma": 0.5,
        "context_multiplier_min": 1.0,
        "context_multiplier_max": 1.5,
        "rule_version": "SYNTHETIC_RULE_V1",
    }


RULES = {
    "F_TURN": _multiplier_rule("EXCESS_ACCUMULATION"),
    "F_WAIT": _multiplier_rule("CONTINUOUS_ACCUMULATION"),
    "F_PROPAGATION": {"rule_type": "CONTINUOUS_ACCUMULATION"},
    "P_DELAY": {"rule_type": "CONTINUOUS_ACCUMULATION"},
    "P_CONNECTION": _multiplier_rule("EXCESS_ACCUMULATION"),
    "P_CARE": {"rule_type": "THRESHOLD_EVENT", "threshold_minutes": 60.0},
    "R_GROUND": _multiplier_rule("CONTINUOUS_ACCUMULATION"),
    "R_TAXI": _multiplier_rule("CONTINUOUS_ACCUMULATION"),
    "R_SCARCITY": {
        "rule_type": "THRESHOLD_EVENT",
        "wait_threshold_minutes": 30.0,
        "taxi_threshold_minutes": 10.0,
    },
}


def valuation(rates=None, rules=None, values=None):
    return ValuationContext(
        subitem_value_parameters=VALUES if values is None else values,
        rule_parameters=RULES if rules is None else rules,
        valuation_version="TEST_VALUES_V1",
        parameter_status=ParameterStatus.CONFIGURED,
        currency_mapping_version="IDENTITY_TEST_V1",
        currency_mapping_mode="IDENTITY",
        channel_rates=rates or {"F": 1.0, "P": 1.0, "R": 1.0},
        test_only=True,
        source="SYNTHETIC_FIXTURE",
    )


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


def test_bounded_multiplier_uses_configured_bounds_and_is_not_constant() -> None:
    values = [bounded_multiplier(value, 0.5, 1.0, 1.4) for value in (0.0, 0.5, 1.0)]
    assert values == sorted(values)
    assert values[0] == 1.0
    assert values[-1] == 1.4
    assert len(set(values)) > 1


def test_missing_subitem_value_is_not_silently_zero() -> None:
    with pytest.raises(ValueError, match="M2_VALUE_PARAMETER_NOT_CONFIGURED"):
        value_for("F_TURN", ValuationContext())


def test_currency_mapping_changes_only_currency_layer(m2_scenario_context_factory) -> None:
    scenario, context = m2_scenario_context_factory()
    base = reconstruct_pre_action_loss(
        build_m2_input(scenario, context, valuation_context=valuation())
    )[0]
    changed = reconstruct_pre_action_loss(
        build_m2_input(
            scenario,
            context,
            valuation_context=valuation({"F": 2.0, "P": 1.0, "R": 1.0}),
        )
    )[0]
    assert base.quantities == changed.quantities
    assert base.constructed_units == changed.constructed_units
    assert changed.flight_loss_rmb == 2.0 * base.flight_loss_rmb
    assert audit_sample_losses((base,)) == {
        "nonnegative": True,
        "currency_identity": True,
        "total_additivity": True,
    }


def test_currency_mapping_requires_all_channels() -> None:
    with pytest.raises(ValueError, match="M2_CURRENCY_MAPPING_INCOMPLETE"):
        to_rmb({"F": 1.0, "P": 1.0, "R": 1.0}, {"F": 1.0, "P": 1.0})


def test_input_row_order_does_not_change_results(m2_scenario_context_factory) -> None:
    scenario, context = m2_scenario_context_factory()
    reversed_scenario = replace(
        scenario, joint_samples=tuple(reversed(scenario.joint_samples))
    )
    first = reconstruct_pre_action_loss(
        build_m2_input(scenario, context, valuation_context=valuation())
    )
    second = reconstruct_pre_action_loss(
        build_m2_input(reversed_scenario, context, valuation_context=valuation())
    )
    assert first == second


def test_learned_correction_bound_is_hard() -> None:
    result = apply_constructed_unit_correction(
        10.0,
        enabled=True,
        correction_units=1.0,
        channel_labels_available=True,
        rho_g=0.1,
        epsilon=0.01,
    )
    assert result.corrected_units == 11.0
    assert result.correction_bound_status == "PASS"
    with pytest.raises(ValueError, match="M2_LEARNED_CORRECTION_BOUND_EXCEEDED"):
        apply_constructed_unit_correction(
            10.0,
            enabled=True,
            correction_units=1.1,
            channel_labels_available=True,
            rho_g=0.1,
            epsilon=0.01,
        )
