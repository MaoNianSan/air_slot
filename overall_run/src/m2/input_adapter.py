from __future__ import annotations

import math
from datetime import timedelta
from typing import TYPE_CHECKING

from ..m1.contracts import M1ScenarioBundle, M1_CONTRACT_ID
from .activation import activate_subitems
from .context_builder import build_m2_context
from .contracts import (
    ActivationStatus,
    AuditContext,
    AvailabilityStatus,
    M2ContextBundle,
    M2ContractError,
    M2InputBundle,
    M2InputStatus,
    M2Metadata,
    ParameterStatus,
    ValuationContext,
)
from .currency import validate_currency_mapping
from .dependencies import CORE_SUBITEMS
from .events import aggregate_event_status, build_events

if TYPE_CHECKING:
    from ..m1.adapter.bundle_loader import PublishedPreBundle


def _close(left, right, tolerance_seconds: float = 1e-3) -> bool:
    return abs((left - right).total_seconds()) <= tolerance_seconds


def _validate_scenario(scenario: M1ScenarioBundle) -> None:
    metadata = scenario.metadata
    if str(metadata.get("m1_contract_id", M1_CONTRACT_ID)) != M1_CONTRACT_ID:
        raise M2ContractError("M2_M1_CONTRACT_VERSION_MISMATCH")
    expected_count = int(scenario.sampling_metadata.get("sample_count", -1))
    if expected_count != len(scenario.joint_samples):
        raise M2ContractError("M2_SAMPLE_COUNT_MISMATCH")
    for reference in (
        scenario.operational_references.successor_sobt,
        scenario.operational_references.turnaround_floor_minutes,
        scenario.operational_references.taxi_reference_minutes,
    ):
        if reference.active and (not reference.source_field or not reference.reference_version):
            raise M2ContractError("M2_REFERENCE_PROVENANCE_MISSING")
    query_time = metadata["query_time"]
    cutoff = metadata["information_cutoff"]
    for sample in scenario.joint_samples:
        for field in (
            "r_ib_minutes",
            "r_ob_minutes",
            "taxi_time",
            "offblock_delay",
            "extra_taxi_delay",
            "total_takeoff_delay",
        ):
            value = getattr(sample, field, None)
            if value is not None and not math.isfinite(float(value)):
                raise M2ContractError(f"M2_SCENARIO_VALUE_NONFINITE:{field}")
        if sample.information_cutoff != cutoff:
            raise M2ContractError("M2_INFORMATION_CUTOFF_ALIGNMENT_FAILED")
        if sample.r_ib_minutes is not None and sample.T_predecessor_inblock is not None:
            expected = query_time + timedelta(minutes=float(sample.r_ib_minutes))
            if not _close(sample.T_predecessor_inblock, expected):
                raise M2ContractError("M2_R_IB_IDENTITY_FAILED")
        if (
            sample.r_ob_minutes is not None
            and sample.earliest_offblock_time is not None
            and sample.AOBT_successor is not None
        ):
            expected = sample.earliest_offblock_time + timedelta(
                minutes=float(sample.r_ob_minutes)
            )
            if not _close(sample.AOBT_successor, expected):
                raise M2ContractError("M2_R_OB_IDENTITY_FAILED")
        if (
            sample.taxi_time is not None
            and sample.AOBT_successor is not None
            and sample.ATOT_successor is not None
        ):
            expected = sample.AOBT_successor + timedelta(minutes=float(sample.taxi_time))
            if not _close(sample.ATOT_successor, expected):
                raise M2ContractError("M2_TAXI_IDENTITY_FAILED")


def _validate_context_alignment(
    scenario: M1ScenarioBundle,
    context: M2ContextBundle,
) -> None:
    metadata = scenario.metadata
    if context.metadata.episode_id != str(metadata["episode_id"]):
        raise M2ContractError("M2_CONTEXT_EPISODE_ALIGNMENT_FAILED")
    if context.metadata.query_time != metadata["query_time"]:
        raise M2ContractError("M2_CONTEXT_QUERY_TIME_ALIGNMENT_FAILED")
    if context.metadata.information_cutoff != metadata["information_cutoff"]:
        raise M2ContractError("M2_CONTEXT_CUTOFF_ALIGNMENT_FAILED")
    if context.metadata.pre_bundle_id != str(metadata.get("pre_bundle_id", "")):
        raise M2ContractError("M2_PRE_M1_VERSION_MISMATCH")
    if context.metadata.pre_contract_id != "AIR_CHAIN_CORE_V2":
        raise M2ContractError("M2_PRE_CONTRACT_VERSION_MISMATCH")


def build_m2_input(
    scenario: M1ScenarioBundle,
    context_bundle: M2ContextBundle,
    *,
    valuation_context: ValuationContext | None = None,
    disabled_subitems: tuple[str, ...] = (),
) -> M2InputBundle:
    _validate_scenario(scenario)
    _validate_context_alignment(scenario, context_bundle)
    valuation = valuation_context or ValuationContext()
    metadata_raw = scenario.metadata
    metadata = M2Metadata(
        episode_id=str(metadata_raw["episode_id"]),
        snapshot_id=str(metadata_raw["snapshot_id"]),
        snapshot_version=int(metadata_raw["snapshot_version"]),
        query_time=metadata_raw["query_time"],
        information_cutoff=metadata_raw["information_cutoff"],
        pre_bundle_id=str(metadata_raw.get("pre_bundle_id", "")),
        m1_bundle_id=str(
            metadata_raw.get("m1_bundle_id", metadata_raw["snapshot_id"])
        ),
        m1_model_version=str(metadata_raw.get("model_version", "")),
        m1_sampling_version=str(
            scenario.sampling_metadata.get("sampling_version", "M1_SAMPLING_V2")
        ),
    )
    ordered_samples = tuple(
        sorted(scenario.joint_samples, key=lambda sample: sample.sample_id)
    )
    runtime_events = tuple(
        build_events(sample, context_bundle.flight_context)
        for sample in ordered_samples
    )
    event_status = aggregate_event_status(runtime_events)
    activations = activate_subitems(
        event_status,
        context_bundle.context_support,
        valuation,
        disabled_subitems=disabled_subitems,
    )

    unresolved_sample_ids = tuple(
        int(sample.sample_id)
        for sample, event_sample in zip(ordered_samples, runtime_events)
        if any(
            status is AvailabilityStatus.TAIL_UNRESOLVED
            for status in event_sample.event_status.values()
        )
    )
    overflow_present = any(
        any(sample.overflow_flags.values()) for sample in ordered_samples
    )
    abstain_reasons: list[str] = []
    core_states = {name: activations[name].status for name in CORE_SUBITEMS}
    if any(status is ActivationStatus.NOT_CONFIGURED for status in core_states.values()):
        abstain_reasons.append("M2_PARAMETER_NOT_FROZEN")
    if any(
        status in {ActivationStatus.UNSUPPORTED, ActivationStatus.DISABLED_BY_CONFIG}
        for status in core_states.values()
    ):
        abstain_reasons.append("M2_CORE_SUBITEM_DEPENDENCY_UNAVAILABLE")
    if unresolved_sample_ids:
        abstain_reasons.append("M2_TAIL_UNRESOLVED")

    configured_active = any(
        item.status in {ActivationStatus.ACTIVE, ActivationStatus.PROXY_ACTIVE}
        for item in activations.values()
    )
    currency_status = "NOT_CONFIGURED"
    if configured_active:
        validate_currency_mapping(valuation.channel_rates)
        currency_status = "CONFIGURED"
        if valuation.currency != "RMB" or valuation.currency_mapping_mode != "IDENTITY":
            currency_status = "CONFIGURED_NON_IDENTITY"

    if abstain_reasons:
        status = M2InputStatus.ABSTAIN
    elif any(
        item.status is ActivationStatus.PROXY_ACTIVE for item in activations.values()
    ):
        status = M2InputStatus.PROXY_SUPPORTED
    elif any(
        item.status in {ActivationStatus.UNSUPPORTED, ActivationStatus.NOT_CONFIGURED}
        for name, item in activations.items()
        if name not in CORE_SUBITEMS
    ):
        status = M2InputStatus.PARTIAL
    else:
        status = M2InputStatus.VALID

    context_evidence = {
        name: (
            value.value if isinstance(value, AvailabilityStatus) else str(value)
        )
        for name, value in context_bundle.context_support.items()
    }
    proxy_status = {
        name: item.status.value
        for name, item in activations.items()
        if item.status is ActivationStatus.PROXY_ACTIVE
    }
    tail_status = str(
        scenario.sampling_metadata.get("tail_resolution_status", "TAIL_UNRESOLVED")
    )
    if unresolved_sample_ids:
        tail_status = "TAIL_UNRESOLVED"
    audit = AuditContext(
        evidence_status=context_evidence,
        proxy_status=proxy_status,
        overflow_status="OVERFLOW_PRESENT" if overflow_present else "NONE",
        tail_resolution_status=tail_status,
        parameter_status=ParameterStatus(valuation.parameter_status).value,
        currency_mapping_status=currency_status,
        formal_reconstruction_gate=(
            abstain_reasons[0] if abstain_reasons else "PASS"
        ),
        abstain_reasons=tuple(dict.fromkeys(abstain_reasons)),
        unresolved_sample_ids=unresolved_sample_ids,
        audit_status="VALIDATED",
    )
    return M2InputBundle(
        metadata=metadata,
        joint_scenarios=ordered_samples,
        flight_context=context_bundle.flight_context,
        passenger_context=context_bundle.passenger_context,
        resource_context=context_bundle.resource_context,
        context_support=context_bundle.context_support,
        context_provenance=context_bundle.provenance,
        normalization_version=context_bundle.normalization_version,
        subitem_activation=activations,
        valuation_context=valuation,
        audit_context=audit,
        input_status=status,
    )


def build_m2_input_from_pre(
    pre_bundle: "PublishedPreBundle",
    scenario: M1ScenarioBundle,
    *,
    valuation_context: ValuationContext | None = None,
    disabled_subitems: tuple[str, ...] = (),
) -> M2InputBundle:
    context = build_m2_context(pre_bundle, scenario)
    return build_m2_input(
        scenario,
        context,
        valuation_context=valuation_context,
        disabled_subitems=disabled_subitems,
    )
