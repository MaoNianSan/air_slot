"""PRE static/reference publication for M1 (Tranche 3).

Resolves ``M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`` per field by
publishing typed context objects into the PRE state:

- route_context             origin/destination airport ids (+ route key)
- carrier_context           BTS Reporting_Airline carrier id (+ provenance)
- aircraft_identity         retained registration identity (never ordinal)
- schedule_reference         typed schedule reference (countdown stays DYNAMIC
                            r_fast; never duplicated into static)
- turnaround_reference      train-frozen reference artifact (MODEL_FEATURE)
- taxi_reference            train-frozen reference artifact (MODEL_FEATURE)

RETAINED_IDENTITY fields never become numeric predictors without a frozen
deterministic encoding contract (MODEL_FEATURE_PENDING); numeric turnaround /
taxi references (train-frozen empirical medians) enter ``c_static`` directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from model.common.enums import EvidenceClass, SupportState
from model.common.value_objects import SupportedValue
from model.PRE.contracts.pre_state import PREState


def _schedule_value(pre_state: PREState) -> dict | None:
    schedule = pre_state.successor_state.get("schedule_reference")
    if schedule is None or schedule.support_state is SupportState.ABSTAIN:
        return None
    if not isinstance(schedule.value, dict):
        return None
    return schedule.value


def _reference_dict(reference) -> dict | None:
    """Extract frozen-reference publication metadata from a reference object."""
    if reference is None:
        return None
    return {
        "reference_id": getattr(reference, "reference_id", None),
        "freeze_id": getattr(reference, "manifest_freeze_id", None),
        "rule_id": getattr(reference, "rule_id", None),
        "rule_version": getattr(reference, "rule_version", None),
        "dataset_instance_id": getattr(reference, "dataset_instance_id", None),
    }


def _reference_value(reference, airport_id: str) -> SupportedValue | None:
    """Frozen-reference lookup; returns the numeric cell or None."""
    if reference is None or airport_id is None:
        return None
    try:
        lookup = reference.lookup(airport_id)
    except Exception:
        return None
    if lookup.support_state is SupportState.ABSTAIN or lookup.value is None:
        return None
    return lookup


def _supported_value(
    value: Any, *, unit: str, support_state: str, quality_flags=()
) -> SupportedValue:
    return SupportedValue(
        value=value,
        unit=unit,
        evidence_class=EvidenceClass.DIRECT,
        support_ceiling=EvidenceClass.DIRECT,
        support_state=SupportState(support_state),
        quality_flags=tuple(quality_flags),
    )


def _abstain_value(reason: str) -> SupportedValue:
    """Unsupported/missing-data publication: ABSTAIN, never fabricated."""
    return SupportedValue(
        value=None,
        unit="canonical",
        evidence_class=EvidenceClass.UNSUPPORTED,
        support_ceiling=EvidenceClass.UNSUPPORTED,
        support_state=SupportState.ABSTAIN,
        reason_code=reason,
    )


def publish_static_reference(
    pre_state: PREState,
    *,
    taxi_reference=None,
    turnaround_reference=None,
    connection_airport_id: str | None = None,
) -> tuple[dict[str, SupportedValue], dict[str, dict]]:
    """Publish the six static/reference fields into a successor-state dict.

    Returns ``(published, publication_meta)``: ``published`` maps each field
    to a SupportedValue (to be merged into the successor state);
    ``publication_meta`` is a plain per-field dict of
    ``{model_feature_status, provenance_reference_id, freeze_id,
    publication_status}`` (no M1 import — PRE never imports downstream).
    M1 rebuilds its typed ``M1StaticReferenceContext`` from this metadata.
    """
    schedule = _schedule_value(pre_state)
    published: dict[str, SupportedValue] = {}
    publication_meta: dict[str, dict] = {}

    # Schedule-derived context fields: when no legal schedule reference exists
    # (e.g. data1, registry UNSUPPORTED/NO_SCHEDULE) they are published as
    # ABSTAIN — never fabricated as SUPPORTED-with-None values.
    if schedule is None:
        for field, meta in (
            ("route_context", "MODEL_FEATURE_PENDING"),
            ("carrier_context", "MODEL_FEATURE_PENDING"),
            ("aircraft_identity", "RETAINED_IDENTITY"),
        ):
            published[field] = _abstain_value("NO_SCHEDULE")
            publication_meta[field] = {
                "publication_status": meta,
                "model_feature_status": meta,
                "provenance_reference_id": "schedule_reference",
                "freeze_id": None,
            }
        publication_meta["schedule_reference"] = {
            "publication_status": "RETAINED_IDENTITY",
            "model_feature_status": "RETAINED_IDENTITY",
            "provenance_reference_id": "schedule_reference",
            "reference_id": "schedule_reference",
            "freeze_id": None,
            "value": None,
            "unit": "UTC",
            "support_state": "ABSTAIN",
            "fallback_level": None,
            "provenance": {"reference_id": "schedule_reference"},
        }
    else:
        route = {
            "origin_airport_id": schedule.get("origin_airport_id"),
            "destination_airport_id": schedule.get("destination_airport_id"),
            "route_key": (
                f"{schedule.get('origin_airport_id')}-{schedule.get('destination_airport_id')}"
            ),
        }
        published["route_context"] = _supported_value(
            route,
            unit="canonical",
            support_state="SUPPORTED",
            quality_flags=("ROUTE_CONTEXT_FROM_SCHEDULE",),
        )
        publication_meta["route_context"] = {
            "publication_status": "MODEL_FEATURE_PENDING",
            "model_feature_status": "MODEL_FEATURE_PENDING",
            "provenance_reference_id": "schedule_reference",
            "freeze_id": None,
        }

        carrier = {"carrier_id": schedule.get("carrier_id")}
        published["carrier_context"] = _supported_value(
            carrier,
            unit="canonical",
            support_state="SUPPORTED",
            quality_flags=("CARRIER_FROM_BTS_REPORTING_AIRLINE",),
        )
        publication_meta["carrier_context"] = {
            "publication_status": "MODEL_FEATURE_PENDING",
            "model_feature_status": "MODEL_FEATURE_PENDING",
            "provenance_reference_id": "schedule_reference",
            "freeze_id": None,
        }

        aircraft = {
            "aircraft_id": schedule.get("aircraft_id"),
            "aircraft_id_namespace": schedule.get("aircraft_id_namespace"),
        }
        published["aircraft_identity"] = _supported_value(
            aircraft,
            unit="canonical",
            support_state="SUPPORTED",
            quality_flags=("AIRCRAFT_IDENTITY_RETAINED_REGISTRATION",),
        )
        publication_meta["aircraft_identity"] = {
            "publication_status": "RETAINED_IDENTITY",
            "model_feature_status": "RETAINED_IDENTITY",
            "provenance_reference_id": "schedule_reference",
            "freeze_id": None,
        }

        publication_meta["schedule_reference"] = {
            "publication_status": "RETAINED_IDENTITY",
            "model_feature_status": "RETAINED_IDENTITY",
            "provenance_reference_id": "schedule_reference",
            "reference_id": "schedule_reference",
            "freeze_id": None,
            "value": schedule,
            "unit": "UTC",
            "support_state": "SUPPORTED",
            "fallback_level": None,
            "provenance": {
                "reference_id": "schedule_reference",
                "availability_basis": "SCHEDULE_REFERENCE_ASSUMPTION",
            },
        }

    origin_airport = None if schedule is None else schedule.get("origin_airport_id")
    # The connection/turn station is the successor origin (the predecessor
    # destination), never the successor destination.
    connection = connection_airport_id or (
        None if schedule is None else schedule.get("origin_airport_id")
    )

    # Turnaround reference: train-frozen numeric MODEL_FEATURE.
    turnaround = _reference_dict(turnaround_reference)
    turnaround_lookup = _reference_value(turnaround_reference, connection)
    turnaround_value = {
        "value": None if turnaround_lookup is None else turnaround_lookup.value,
        "unit": "minutes",
        "reference_id": None if turnaround is None else turnaround["reference_id"],
        "freeze_id": None if turnaround is None else turnaround["freeze_id"],
        "fallback_level": next(
            (
                flag.removeprefix("REFERENCE_LEVEL_")
                for flag in (
                    turnaround_lookup.quality_flags
                    if turnaround_lookup is not None
                    else ()
                )
                if flag.startswith("REFERENCE_LEVEL_")
            ),
            None,
        ),
        "support_state": (
            turnaround_lookup.support_state.value
            if turnaround_lookup is not None
            else "ABSTAIN"
        ),
        "provenance": turnaround,
    }
    if turnaround_lookup is None:
        published["turnaround_reference"] = _abstain_value(
            "NO_TURNAROUND_REFERENCE_CELL"
        )
    else:
        published["turnaround_reference"] = _supported_value(
            turnaround_value,
            unit="minutes",
            support_state="SUPPORTED",
            quality_flags=("TURNAROUND_REFERENCE_PUBLISHED",),
        )
    turnaround_status = (
        "MODEL_FEATURE" if turnaround_lookup is not None else "MODEL_FEATURE_PENDING"
    )
    publication_meta["turnaround_reference"] = {
        "publication_status": turnaround_status,
        "model_feature_status": turnaround_status,
        "provenance_reference_id": (
            None if turnaround is None else turnaround["reference_id"]
        ),
        "freeze_id": None if turnaround is None else turnaround["freeze_id"],
    }

    # Taxi reference: train-frozen numeric MODEL_FEATURE.
    taxi = _reference_dict(taxi_reference)
    taxi_lookup = _reference_value(taxi_reference, origin_airport)
    taxi_value = {
        "value": None if taxi_lookup is None else taxi_lookup.value,
        "unit": "minutes",
        "reference_id": None if taxi is None else taxi["reference_id"],
        "freeze_id": None if taxi is None else taxi["freeze_id"],
        "fallback_level": next(
            (
                flag.removeprefix("REFERENCE_LEVEL_")
                for flag in (
                    taxi_lookup.quality_flags if taxi_lookup is not None else ()
                )
                if flag.startswith("REFERENCE_LEVEL_")
            ),
            None,
        ),
        "support_state": (
            taxi_lookup.support_state.value if taxi_lookup is not None else "ABSTAIN"
        ),
        "provenance": taxi,
    }
    if taxi_lookup is None:
        published["taxi_reference"] = _abstain_value("NO_TAXI_REFERENCE_CELL")
    else:
        published["taxi_reference"] = _supported_value(
            taxi_value,
            unit="minutes",
            support_state="SUPPORTED",
            quality_flags=("TAXI_REFERENCE_PUBLISHED",),
        )
    taxi_status = (
        "MODEL_FEATURE" if taxi_lookup is not None else "MODEL_FEATURE_PENDING"
    )
    publication_meta["taxi_reference"] = {
        "publication_status": taxi_status,
        "model_feature_status": taxi_status,
        "provenance_reference_id": None if taxi is None else taxi["reference_id"],
        "freeze_id": None if taxi is None else taxi["freeze_id"],
    }

    # Make the plain PRE publication self-contained.  M1 must not have to
    # re-read raw/reference objects to recover values or lineage.
    for field, supported in published.items():
        meta = publication_meta[field]
        payload = supported.value if isinstance(supported.value, dict) else None
        meta["value"] = supported.value
        meta["unit"] = supported.unit
        meta["support_state"] = supported.support_state.value
        meta["reference_id"] = (
            payload.get("reference_id") if payload is not None else None
        ) or meta.get("provenance_reference_id")
        meta["fallback_level"] = (
            payload.get("fallback_level") if payload is not None else None
        )
        meta["provenance"] = (
            payload.get("provenance") if payload is not None else None
        ) or {"reference_id": meta.get("provenance_reference_id")}

    return published, publication_meta
