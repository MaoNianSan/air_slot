from __future__ import annotations

from datetime import timedelta

from ..m1.contracts import M1ScenarioBundle
from .activation import activate_subitems
from .contracts import (
    AuditContext,
    FlightContext,
    M2InputBundle,
    M2InputStatus,
    M2Metadata,
    PassengerContext,
    ResourceContext,
    ValuationContext,
)


def _close(left, right, tolerance_seconds: float = 1e-3) -> bool:
    return abs((left - right).total_seconds()) <= tolerance_seconds


def _validate_scenario(scenario: M1ScenarioBundle) -> None:
    metadata = scenario.metadata
    expected_count = int(scenario.sampling_metadata.get("sample_count", -1))
    if expected_count != len(scenario.joint_samples):
        raise ValueError("M2_SAMPLE_COUNT_MISMATCH")
    for reference in (
        scenario.operational_references.successor_sobt,
        scenario.operational_references.turnaround_floor_minutes,
        scenario.operational_references.taxi_reference_minutes,
    ):
        if reference.active and (not reference.source_field or not reference.reference_version):
            raise ValueError("M2_REFERENCE_PROVENANCE_MISSING")
    query_time = metadata["query_time"]
    cutoff = metadata["information_cutoff"]
    for sample in scenario.joint_samples:
        if sample.information_cutoff != cutoff:
            raise ValueError("M2_INFORMATION_CUTOFF_ALIGNMENT_FAILED")
        if sample.r_ib_minutes is not None and sample.T_predecessor_inblock is not None:
            expected = query_time + timedelta(minutes=float(sample.r_ib_minutes))
            if not _close(sample.T_predecessor_inblock, expected):
                raise ValueError("M2_R_IB_IDENTITY_FAILED")
        if sample.r_ob_minutes is not None and sample.earliest_offblock_time is not None and sample.AOBT_successor is not None:
            expected = sample.earliest_offblock_time + timedelta(minutes=float(sample.r_ob_minutes))
            if not _close(sample.AOBT_successor, expected):
                raise ValueError("M2_R_OB_IDENTITY_FAILED")
        if sample.taxi_time is not None and sample.AOBT_successor is not None and sample.ATOT_successor is not None:
            expected = sample.AOBT_successor + timedelta(minutes=float(sample.taxi_time))
            if not _close(sample.ATOT_successor, expected):
                raise ValueError("M2_TAXI_IDENTITY_FAILED")


def build_m2_input(
    scenario: M1ScenarioBundle,
    *,
    passenger_context: PassengerContext | None = None,
    resource_context: ResourceContext | None = None,
    valuation_context: ValuationContext | None = None,
    disabled_subitems: tuple[str, ...] = (),
) -> M2InputBundle:
    _validate_scenario(scenario)
    metadata_raw = scenario.metadata
    metadata = M2Metadata(
        episode_id=str(metadata_raw["episode_id"]),
        snapshot_id=str(metadata_raw["snapshot_id"]),
        snapshot_version=int(metadata_raw["snapshot_version"]),
        query_time=metadata_raw["query_time"],
        information_cutoff=metadata_raw["information_cutoff"],
        pre_bundle_id=str(metadata_raw.get("pre_bundle_id", "")),
        m1_bundle_id=str(metadata_raw.get("m1_bundle_id", metadata_raw["snapshot_id"])),
        m1_model_version=str(metadata_raw.get("model_version", "")),
        m1_sampling_version=str(scenario.sampling_metadata.get("sampling_version", "M1_SAMPLING_V2")),
    )
    refs = scenario.operational_references
    flight_raw = scenario.pre_context.get("flight", {})
    flight_context = FlightContext(
        successor_sobt=refs.successor_sobt.value if refs.successor_sobt.active else None,
        turnaround_reference_minutes=float(refs.turnaround_floor_minutes.value) if refs.turnaround_floor_minutes.active else None,
        turnaround_reference_type=str(flight_raw.get("turnaround_reference_type", "OFFICIAL_FLOOR" if refs.turnaround_floor_minutes.active else "UNSUPPORTED")),
        continuity_exposure=float(flight_raw.get("continuity_exposure", 0.0)),
        downstream_leg_count=int(flight_raw.get("downstream_leg_count", 0)),
        execution_window_margin=float(flight_raw.get("execution_window_margin", 0.0)),
        aircraft_flexibility=float(flight_raw.get("aircraft_flexibility", 0.0)),
        evidence_status=str(flight_raw.get("evidence_status", refs.turnaround_floor_minutes.support_level)),
    )
    passenger = passenger_context or PassengerContext(**scenario.pre_context.get("passenger", {}))
    resource = resource_context or ResourceContext(**scenario.pre_context.get("resource", {}))
    valuation = valuation_context or ValuationContext(**scenario.pre_context.get("valuation", {}))
    activations = activate_subitems(
        flight_context, passenger, resource, valuation, disabled_subitems=disabled_subitems
    )
    audit = AuditContext(
        evidence_status=dict(scenario.pre_context.get("evidence_status", {})),
        proxy_status=dict(scenario.pre_context.get("proxy_status", {})),
        overflow_status="OVERFLOW_PRESENT" if any(any(sample.overflow_flags.values()) for sample in scenario.joint_samples) else "NONE",
        tail_resolution_status=str(scenario.sampling_metadata.get("tail_resolution_status", "TAIL_UNRESOLVED")),
        audit_status="VALIDATED",
    )
    has_r_ob = all(sample.r_ob_minutes is not None for sample in scenario.joint_samples)
    supported_refs = refs.successor_sobt.active and refs.turnaround_floor_minutes.active
    unresolved_overflow = (
        audit.tail_resolution_status == "TAIL_UNRESOLVED"
        and audit.overflow_status == "OVERFLOW_PRESENT"
    )
    if not has_r_ob or not supported_refs or unresolved_overflow:
        status = M2InputStatus.ABSTAIN
    elif any(item.status.value == "PROXY_ACTIVE" for item in activations.values()):
        status = M2InputStatus.PROXY_SUPPORTED
    elif any(item.status.value == "UNSUPPORTED" for item in activations.values()):
        status = M2InputStatus.PARTIAL
    else:
        status = M2InputStatus.VALID
    ordered_samples = tuple(sorted(scenario.joint_samples, key=lambda sample: sample.sample_id))
    return M2InputBundle(
        metadata=metadata, joint_scenarios=ordered_samples,
        flight_context=flight_context, passenger_context=passenger,
        resource_context=resource, subitem_activation=activations,
        valuation_context=valuation, audit_context=audit, input_status=status,
    )
