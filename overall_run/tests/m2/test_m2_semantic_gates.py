from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from overall_run.src.m1.contracts import SupportedOperationalValue
from overall_run.src.m2 import (
    build_m2_context,
    build_m2_input,
    reconstruct_pre_action_loss,
    summarize_episode,
)
from overall_run.src.m2.activation import activate_subitems
from overall_run.src.m2.context_builder import risk_direction_value
from overall_run.src.m2.contracts import (
    ActivationStatus,
    AvailabilityStatus,
    CONTEXT_FIELD_REGISTRY,
    M2InputStatus,
    ValuationContext,
)
from overall_run.src.m2.dependencies import SUBITEM_DEPENDENCIES
from overall_run.src.m2.events import EVENT_NAMES, build_events

from .test_m2_rules_and_units import RULES, VALUES, valuation


def _base_dependency_inputs():
    events = {name: AvailabilityStatus.AVAILABLE for name in EVENT_NAMES}
    support = {
        name: AvailabilityStatus.AVAILABLE for name in CONTEXT_FIELD_REGISTRY
    }
    support.update(
        {
            "successor_sobt": AvailabilityStatus.AVAILABLE,
            "turnaround_reference_minutes": AvailabilityStatus.AVAILABLE,
        }
    )
    return events, support


@pytest.mark.parametrize("subitem", tuple(SUBITEM_DEPENDENCIES))
def test_each_subitem_rejects_missing_event(subitem: str) -> None:
    events, support = _base_dependency_inputs()
    spec = SUBITEM_DEPENDENCIES[subitem]
    for name in (*spec.required_events, *spec.any_required_events):
        events[name] = AvailabilityStatus.MISSING
    result = activate_subitems(events, support, valuation())
    assert result[subitem].status is ActivationStatus.UNSUPPORTED


@pytest.mark.parametrize("subitem", tuple(SUBITEM_DEPENDENCIES))
def test_each_subitem_rejects_missing_context(subitem: str) -> None:
    events, support = _base_dependency_inputs()
    spec = SUBITEM_DEPENDENCIES[subitem]
    field = (*spec.required_context_fields, *spec.required_reference_fields)[0]
    support[field] = AvailabilityStatus.UNSUPPORTED
    result = activate_subitems(events, support, valuation())
    assert result[subitem].status is ActivationStatus.UNSUPPORTED


@pytest.mark.parametrize("subitem", tuple(SUBITEM_DEPENDENCIES))
def test_each_subitem_requires_rule_and_value_parameters(subitem: str) -> None:
    events, support = _base_dependency_inputs()
    rules = {name: dict(parameters) for name, parameters in RULES.items()}
    rules.pop(subitem)
    result = activate_subitems(events, support, valuation(rules=rules))
    assert result[subitem].status is ActivationStatus.NOT_CONFIGURED
    values = dict(VALUES)
    values.pop(subitem)
    result = activate_subitems(events, support, valuation(values=values))
    assert result[subitem].status is ActivationStatus.NOT_CONFIGURED


@pytest.mark.parametrize("subitem", tuple(SUBITEM_DEPENDENCIES))
def test_each_subitem_distinguishes_proxy_disabled_and_tail(subitem: str) -> None:
    events, support = _base_dependency_inputs()
    spec = SUBITEM_DEPENDENCIES[subitem]
    proxy_field = (*spec.required_context_fields, *spec.required_reference_fields)[0]
    support[proxy_field] = AvailabilityStatus.PROXY_AVAILABLE
    result = activate_subitems(events, support, valuation())
    assert result[subitem].status is ActivationStatus.PROXY_ACTIVE

    events, support = _base_dependency_inputs()
    result = activate_subitems(
        events, support, valuation(), disabled_subitems=(subitem,)
    )
    assert result[subitem].status is ActivationStatus.DISABLED_BY_CONFIG

    events, support = _base_dependency_inputs()
    for name in (*spec.required_events, *spec.any_required_events):
        events[name] = AvailabilityStatus.TAIL_UNRESOLVED
    result = activate_subitems(events, support, valuation())
    assert result[subitem].status is ActivationStatus.UNSUPPORTED
    assert result[subitem].support_reason == "TAIL_UNRESOLVED"


def test_none_nan_unresolved_and_zero_event_semantics(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    sample = scenario.joint_samples[0]

    missing = build_events(replace(sample, r_ob_minutes=None), context.flight_context)
    assert missing.extra_offblock_wait_minutes is None
    assert missing.event_status["extra_offblock_wait"] is AvailabilityStatus.MISSING

    nan_event = build_events(replace(sample, r_ob_minutes=np.nan), context.flight_context)
    assert nan_event.extra_offblock_wait_minutes is None
    assert nan_event.event_status["extra_offblock_wait"] is AvailabilityStatus.MISSING

    overflow_flags = dict(sample.overflow_flags)
    overflow_flags["R_IB"] = True
    unresolved = build_events(
        replace(sample, T_predecessor_inblock=None, overflow_flags=overflow_flags),
        context.flight_context,
    )
    assert unresolved.event_status["turn_deficit"] is AvailabilityStatus.TAIL_UNRESOLVED

    predicted_zero = build_events(
        replace(sample, r_ob_minutes=0.0, observed_event_mask={}),
        context.flight_context,
    )
    assert predicted_zero.extra_offblock_wait_minutes == 0.0
    assert predicted_zero.event_semantics["extra_offblock_wait"] == "PREDICTED"

    observed_zero = build_events(
        replace(sample, r_ob_minutes=0.0, observed_event_mask={"AOBT_PLUS": True}),
        context.flight_context,
    )
    assert observed_zero.extra_offblock_wait_minutes == 0.0
    assert observed_zero.event_semantics["extra_offblock_wait"] == "OBSERVED"

    broken = replace(
        scenario,
        joint_samples=(replace(sample, r_ob_minutes=np.nan),)
        + scenario.joint_samples[1:],
    )
    with pytest.raises(ValueError, match="M2_SCENARIO_VALUE_NONFINITE:r_ob_minutes"):
        build_m2_input(broken, context, valuation_context=valuation())


def test_context_direction_conversions_are_monotone() -> None:
    assert risk_direction_value("resource_availability", 0.2) > risk_direction_value(
        "resource_availability", 0.8
    )
    assert risk_direction_value("execution_window_margin", 0.2) > risk_direction_value(
        "execution_window_margin", 0.8
    )
    assert risk_direction_value(
        "infrastructure_flexibility", 0.2
    ) > risk_direction_value("infrastructure_flexibility", 0.8)
    with pytest.raises(ValueError, match="M2_CONTEXT_UNIT_INTERVAL_REQUIRED"):
        risk_direction_value("resource_availability", 2.0)


def test_resource_scarcity_and_flow_pressure_drive_loss_in_risk_direction(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    rules = {name: dict(parameters) for name, parameters in RULES.items()}
    rules["R_SCARCITY"]["wait_threshold_minutes"] = 0.0
    rules["R_SCARCITY"]["taxi_threshold_minutes"] = 0.0
    configured = valuation(rules=rules)

    scarce = replace(
        context,
        resource_context=replace(
            context.resource_context,
            resource_availability=0.2,
            resource_scarcity=0.8,
            airport_flow_pressure=0.8,
        ),
    )
    ample = replace(
        context,
        resource_context=replace(
            context.resource_context,
            resource_availability=0.8,
            resource_scarcity=0.2,
            airport_flow_pressure=0.2,
        ),
    )
    scarce_loss = reconstruct_pre_action_loss(
        build_m2_input(scenario, scarce, valuation_context=configured)
    )[0]
    ample_loss = reconstruct_pre_action_loss(
        build_m2_input(scenario, ample, valuation_context=configured)
    )[0]
    assert scarce_loss.resource_scarcity_quantity > ample_loss.resource_scarcity_quantity
    assert scarce_loss.resource_taxi_quantity >= ample_loss.resource_taxi_quantity


def test_parameter_freeze_and_zero_total_summary_gates(
    m2_scenario_context_factory,
) -> None:
    scenario, context = m2_scenario_context_factory()
    frozen_pending = build_m2_input(
        scenario, context, valuation_context=ValuationContext()
    )
    assert frozen_pending.input_status is M2InputStatus.ABSTAIN
    assert "M2_PARAMETER_NOT_FROZEN" in frozen_pending.audit_context.abstain_reasons
    assert all(
        loss.total_pre_action_loss_rmb is None
        for loss in reconstruct_pre_action_loss(frozen_pending)
    )

    zero_losses = reconstruct_pre_action_loss(
        build_m2_input(
            scenario,
            context,
            valuation_context=valuation(values={name: 0.0 for name in VALUES}),
        )
    )
    summary = summarize_episode(zero_losses)
    assert summary.channel_loss_shares_status == "ZERO_TOTAL_LOSS"
    assert all(value is None for value in summary.channel_loss_shares.values())


def test_context_builder_preserves_unsupported_and_empirical_turn_proxy(
    m2_pre_bundle,
    m2_scenario_context_factory,
) -> None:
    scenario, _ = m2_scenario_context_factory()
    episodes = m2_pre_bundle.episodes.drop(columns=["rebooking_scarcity"])
    missing_bundle = replace(m2_pre_bundle, episodes=episodes)
    missing_context = build_m2_context(missing_bundle, scenario)
    assert missing_context.passenger_context.rebooking_scarcity is None
    assert missing_context.context_support["rebooking_scarcity"] is AvailabilityStatus.UNSUPPORTED

    empirical = pd.DataFrame(
        [
            {
                "reference_id": "turn-proxy",
                "reference_type": "minimum_turnaround",
                "group_key": '{"turnaround_airport": "EHAM"}',
                "statistic": "q10",
                "reference_value": 35.0,
                "cell_size": 50,
                "fallback_level": "EXACT_CELL",
                "fit_start_time": pd.Timestamp("2025-01-01", tz="UTC"),
                "fit_end_time": pd.Timestamp("2025-12-31", tz="UTC"),
                "fit_split": "train",
                "source_hash": "f" * 64,
            }
        ]
    )
    calibration = pd.concat([m2_pre_bundle.calibration, empirical], ignore_index=True)
    proxy_bundle = replace(m2_pre_bundle, calibration=calibration)
    inactive_floor = SupportedOperationalValue(
        value=None,
        active=False,
        support_level="UNSUPPORTED",
        source_field=None,
        source_event_id=None,
        availability_time=None,
        reference_version=None,
        inactive_reason="OFFICIAL_FLOOR_NOT_AVAILABLE",
    )
    scenario = replace(
        scenario,
        operational_references=replace(
            scenario.operational_references,
            turnaround_floor_minutes=inactive_floor,
        ),
    )
    proxy_context = build_m2_context(proxy_bundle, scenario)
    assert proxy_context.flight_context.turnaround_reference_type == "EMPIRICAL_REFERENCE"
    assert proxy_context.flight_context.turnaround_reference_minutes == 35.0
    bundle = build_m2_input(scenario, proxy_context, valuation_context=valuation())
    assert bundle.subitem_activation["F_TURN"].status is ActivationStatus.PROXY_ACTIVE
    assert scenario.operational_references.turnaround_floor_minutes.active is False
