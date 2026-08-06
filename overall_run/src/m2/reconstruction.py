from __future__ import annotations

from .constructed_units import channel_units, subitem_units
from .contracts import AvailabilityStatus, M2InputBundle, M2InputStatus, M2SampleLoss
from .currency import subitems_to_rmb, to_rmb
from .dependencies import CORE_SUBITEMS, SUBITEM_DEPENDENCIES
from .events import build_events
from .quantities import build_quantities


def reconstruct_sample(bundle: M2InputBundle, sample: object) -> M2SampleLoss:
    events = build_events(sample, bundle.flight_context)
    sample_tail_unresolved = any(
        status is AvailabilityStatus.TAIL_UNRESOLVED
        for status in events.event_status.values()
    )
    if sample_tail_unresolved:
        quantities = {name: None for name in SUBITEM_DEPENDENCIES}
    else:
        quantities = build_quantities(
            events,
            bundle.flight_context,
            bundle.passenger_context,
            bundle.resource_context,
            bundle.subitem_activation,
            bundle.valuation_context,
        )
    units = subitem_units(quantities, bundle.valuation_context)
    channels = channel_units(units)
    has_units = any(value is not None for value in channels.values())
    if has_units:
        losses = to_rmb(channels, bundle.valuation_context.channel_rates)
        subitem_losses = subitems_to_rmb(
            units, bundle.valuation_context.channel_rates
        )
    else:
        losses = {channel: None for channel in ("F", "P", "R")}
        subitem_losses = {name: None for name in units}
    supported_losses = [float(value) for value in losses.values() if value is not None]
    core_complete = all(units.get(name) is not None for name in CORE_SUBITEMS)
    abstain_reasons = set(bundle.audit_context.abstain_reasons)
    resolved_only_allowed = (
        core_complete
        and bool(supported_losses)
        and not sample_tail_unresolved
        and abstain_reasons.issubset({"M2_TAIL_UNRESOLVED"})
    )
    resolved_only_total = (
        sum(supported_losses) if resolved_only_allowed else None
    )
    total = (
        sum(supported_losses)
        if bundle.input_status is not M2InputStatus.ABSTAIN
        and core_complete
        and not sample_tail_unresolved
        and supported_losses
        else None
    )
    proxy = {
        name: item.status.value
        for name, item in bundle.subitem_activation.items()
        if item.status.value == "PROXY_ACTIVE"
    }
    evidence = {
        name: item.input_evidence_level
        for name, item in bundle.subitem_activation.items()
    }
    sample_tail_status = (
        "TAIL_UNRESOLVED"
        if sample_tail_unresolved
        else (
            "RESOLVED_SAMPLE"
            if bundle.audit_context.tail_resolution_status == "TAIL_UNRESOLVED"
            else bundle.audit_context.tail_resolution_status
        )
    )
    return M2SampleLoss(
        episode_id=bundle.metadata.episode_id,
        snapshot_id=bundle.metadata.snapshot_id,
        sample_id=int(sample.sample_id),
        sample_weight=1.0 / len(bundle.joint_scenarios),
        turn_deficit_minutes=events.turn_deficit_minutes,
        turn_deficit_semantics=events.turn_deficit_semantics,
        extra_offblock_wait_minutes=events.extra_offblock_wait_minutes,
        extra_taxi_minutes=events.extra_taxi_minutes,
        takeoff_delay_minutes=events.takeoff_delay_minutes,
        event_status={name: status.value for name, status in events.event_status.items()},
        event_semantics=events.event_semantics,
        event_source=events.event_source,
        quantities=quantities,
        constructed_units=units,
        channel_constructed_units=channels,
        subitem_loss_rmb=subitem_losses,
        channel_loss_rmb=losses,
        total_pre_action_loss_rmb=total,
        resolved_only_total_pre_action_loss_rmb=resolved_only_total,
        m2_input_status=bundle.input_status,
        tail_resolution_status=sample_tail_status,
        evidence_status=evidence,
        proxy_status=proxy,
        audit_status="VALIDATED",
        overflow_present=any(getattr(sample, "overflow_flags", {}).values()),
    )


def reconstruct_pre_action_loss(bundle: M2InputBundle) -> tuple[M2SampleLoss, ...]:
    return tuple(
        reconstruct_sample(bundle, sample) for sample in bundle.joint_scenarios
    )
