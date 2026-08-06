from __future__ import annotations

from .contracts import M2InputBundle, M2InputStatus, M2SampleLoss
from .events import build_events
from .quantities import build_quantities
from .constructed_units import channel_units, subitem_units
from .currency import to_rmb


def reconstruct_sample(bundle: M2InputBundle, sample: object) -> M2SampleLoss:
    events = build_events(sample, bundle.flight_context)
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
    losses = to_rmb(channels, bundle.valuation_context.channel_rates)
    supported_losses = [float(value) for value in losses.values() if value is not None]
    total = None if bundle.input_status is M2InputStatus.ABSTAIN or not supported_losses else sum(supported_losses)
    proxy = {name: item.status.value for name, item in bundle.subitem_activation.items() if item.status.value == "PROXY_ACTIVE"}
    evidence = {name: item.input_evidence_level for name, item in bundle.subitem_activation.items()}
    return M2SampleLoss(
        episode_id=bundle.metadata.episode_id,
        snapshot_id=bundle.metadata.snapshot_id,
        sample_id=int(sample.sample_id), sample_weight=1.0 / len(bundle.joint_scenarios),
        turn_deficit_minutes=events.turn_deficit_minutes, turn_deficit_semantics=events.turn_deficit_semantics,
        extra_offblock_wait_minutes=events.extra_offblock_wait_minutes, extra_taxi_minutes=events.extra_taxi_minutes,
        takeoff_delay_minutes=events.takeoff_delay_minutes, quantities=quantities, constructed_units=units,
        channel_constructed_units=channels, channel_loss_rmb=losses, total_pre_action_loss_rmb=total,
        m2_input_status=bundle.input_status, tail_resolution_status=bundle.audit_context.tail_resolution_status,
        evidence_status=evidence, proxy_status=proxy, audit_status="VALIDATED",
        overflow_present=any(getattr(sample, "overflow_flags", {}).values()),
    )


def reconstruct_pre_action_loss(bundle: M2InputBundle) -> tuple[M2SampleLoss, ...]:
    if bundle.input_status is M2InputStatus.ABSTAIN:
        return tuple(reconstruct_sample(bundle, sample) for sample in bundle.joint_scenarios)
    return tuple(reconstruct_sample(bundle, sample) for sample in bundle.joint_scenarios)
