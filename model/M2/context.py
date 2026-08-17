"""M2 scientific context construction from train-frozen Data2 references."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import Field

from model.M2.contracts import COMPONENTS, M2ScientificContext, ScientificContextValue
from model.PRE.reference.exposure_data2 import (
    Data2ExposureReference,
    data2_downstream_exposure_from_payload,
)
from model.PRE.reference.passenger_data2 import (
    Data2PassengerReference,
    data2_passenger_reference_from_payload,
)
from model.PRE.reference.taxi_data2 import (
    Data2TaxiReference,
    data2_taxi_reference_from_payload,
)
from model.PRE.reference.turnaround_data2 import (
    Data2TurnaroundReference,
    data2_turnaround_reference_from_payload,
)
from model.PRE.transformation import ConstructionType
from model.common.estimand import ConsequenceScope, ScopeStatus
from model.common.enums import EvidenceClass, SupportState
from model.common.errors import ContractError
from model.common.identity import content_id
from model.common.value_objects import FrozenModel, SupportedValue


_EXP2_FIXED_SCOPE = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "R_operating",
)


class AirportReferenceKeys(FrozenModel):
    connection_airport_id: str = Field(min_length=1)
    successor_destination_airport_id: str = Field(min_length=1)


@dataclass(frozen=True)
class M2ReferenceBundle:
    turnaround: Data2TurnaroundReference
    taxi: Data2TaxiReference
    downstream_exposure: Data2ExposureReference
    passenger: Data2PassengerReference

    @property
    def reference_ids(self) -> dict[str, str]:
        return {
            "turnaround": self.turnaround.reference_id,
            "taxi": self.taxi.reference_id,
            "downstream_exposure": self.downstream_exposure.reference_id,
            "passenger": self.passenger.reference_id,
        }


def _sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
    ):
        raise ContractError(f"M2_REFERENCE_ID_INVALID:{label}")
    return value


def _require(payload: Mapping[str, Any], key: str) -> Any:
    if key not in payload:
        raise ContractError(f"M2_REFERENCE_PAYLOAD_MISSING:{key}")
    return payload[key]


def load_data2_reference_bundle(
    payloads: Mapping[str, Any],
    *,
    expected_reference_ids: Mapping[str, str] | None = None,
) -> M2ReferenceBundle:
    """Load and structurally validate frozen Data2 reference payloads."""
    loaders = {
        "turnaround": data2_turnaround_reference_from_payload,
        "taxi": data2_taxi_reference_from_payload,
        "downstream_exposure": data2_downstream_exposure_from_payload,
        "passenger": data2_passenger_reference_from_payload,
    }
    loaded: dict[str, Any] = {}
    expected = expected_reference_ids or {}
    for name, loader in loaders.items():
        payload = _require(payloads, name)
        reference = loader(payload)
        _sha256(reference.reference_id, name)
        _sha256(reference.manifest_freeze_id, f"{name}.manifest_freeze_id")
        if name in expected and expected[name] != reference.reference_id:
            raise ContractError(f"M2_REFERENCE_ID_MISMATCH:{name}")
        loaded[name] = reference
    if (loaded["turnaround"].rule_id, loaded["turnaround"].rule_version) != (
        "DATA2_TURNAROUND_REFERENCE",
        "1.0.0",
    ):
        raise ContractError("M2_REFERENCE_RULE_MISMATCH:turnaround")
    if (loaded["taxi"].rule_id, loaded["taxi"].rule_version) != (
        "DATA2_TAXI_REFERENCE",
        "1.0.0",
    ):
        raise ContractError("M2_REFERENCE_RULE_MISMATCH:taxi")
    if (
        loaded["downstream_exposure"].rule_id,
        loaded["downstream_exposure"].rule_version,
    ) != ("DATA2_DOWNSTREAM_EXPOSURE", "1.0.0"):
        raise ContractError("M2_REFERENCE_RULE_MISMATCH:downstream_exposure")
    passenger = loaded["passenger"]
    if not passenger.rule_id.startswith("DATA2_PASSENGER_REFERENCE") or (
        passenger.rule_version != "1.0.0"
    ):
        raise ContractError("M2_REFERENCE_RULE_MISMATCH:passenger")
    return M2ReferenceBundle(
        turnaround=loaded["turnaround"],
        taxi=loaded["taxi"],
        downstream_exposure=loaded["downstream_exposure"],
        passenger=passenger,
    )


def _abstain(object_id: str, unit: str, reason: str) -> ScientificContextValue:
    return ScientificContextValue(
        object_id=object_id,
        value=None,
        unit=unit,
        support_state=SupportState.ABSTAIN,
        evidence_class=EvidenceClass.UNSUPPORTED,
        construction_type=ConstructionType.UNSUPPORTED,
        reason_code=reason,
    )


def _reference_value(
    object_id: str,
    supported: SupportedValue,
    reference: Any,
) -> ScientificContextValue:
    provenance = tuple(
        sorted(
            set(
                (
                    *supported.quality_flags,
                    f"reference_id={reference.reference_id}",
                    f"rule={reference.rule_id}@{reference.rule_version}",
                )
            )
        )
    )
    return ScientificContextValue(
        object_id=object_id,
        value=supported.value,
        unit=supported.unit,
        support_state=supported.support_state,
        evidence_class=supported.evidence_class,
        construction_type=ConstructionType.TRAIN_FROZEN_REFERENCE,
        reference_period=reference.fit_period,
        freeze_id=reference.manifest_freeze_id,
        reason_code=supported.reason_code,
        provenance=provenance,
    )


def build_m2_context(
    bundle: M2ReferenceBundle,
    airport_keys: AirportReferenceKeys,
) -> M2ScientificContext:
    """Resolve the four supported M2 inputs from train-frozen references."""
    return M2ScientificContext(
        turnaround_reference=_reference_value(
            "DATA2_TURNAROUND_REFERENCE@1.0.0",
            bundle.turnaround.lookup(airport_keys.connection_airport_id),
            bundle.turnaround,
        ),
        turnaround_floor=_abstain(
            "turnaround_floor", "minutes", "NO_TURNAROUND_FLOOR_FROZEN"
        ),
        expected_downstream_exposure=_reference_value(
            "DATA2_DOWNSTREAM_EXPOSURE@1.0.0",
            bundle.downstream_exposure.lookup(
                airport_keys.connection_airport_id
            ),
            bundle.downstream_exposure,
        ),
        passenger_exposure=_reference_value(
            f"{bundle.passenger.rule_id}@{bundle.passenger.rule_version}",
            bundle.passenger.lookup(
                airport_keys.connection_airport_id,
                airport_keys.successor_destination_airport_id,
            ),
            bundle.passenger,
        ),
        itinerary_disruption_events=_abstain(
            "itinerary_disruption_events",
            "events",
            "NO_ITINERARY_DISRUPTION_EVIDENCE_FROZEN",
        ),
        service_policy_reference=_abstain(
            "service_policy_reference",
            "minutes",
            "NO_SERVICE_POLICY_FROZEN",
        ),
        taxi_reference=_reference_value(
            "DATA2_TAXI_REFERENCE@1.0.0",
            bundle.taxi.lookup(airport_keys.connection_airport_id),
            bundle.taxi,
        ),
    )


def build_exp2_fixed_scope_pending(
    config: Mapping[str, Any] | None = None,
) -> ConsequenceScope:
    """Typed fixed Exp2 scope object with formal decisions left unresolved."""
    components = tuple(
        config.get("formal_scope") or _EXP2_FIXED_SCOPE
        if config is not None
        else _EXP2_FIXED_SCOPE
    )
    if not components or not set(components) <= set(COMPONENTS):
        raise ContractError("M2_EXP2_FIXED_SCOPE_INVALID")
    return ConsequenceScope.create(
        estimand_id="EXP2_FULL_FIXED_FORMAL_SCOPE",
        estimand_version="V5.0",
        included_components=components,
        aggregation_rule_id="PENDING_M2_FORMAL_FREEZE",
        valuation_registry_id="PENDING_M2_FORMAL_FREEZE",
        material_coverage_contract_id="PENDING_M2_FORMAL_FREEZE",
        scope_status=ScopeStatus.FORMAL_AGGREGATE_UNRESOLVED,
    )


def smoke_reference_payloads() -> dict[str, Any]:
    """Synthetic development-only payloads for CLI smoke and focused tests."""
    turnaround = {
        "reference_id": content_id({"synthetic": "turnaround"}),
        "rule_id": "DATA2_TURNAROUND_REFERENCE",
        "rule_version": "1.0.0",
        "fit_period": "2019-H1",
        "global_value_minutes": 38.0,
        "global_sample_count": 50,
        "cells": [
            {
                "airport_id": "ABE",
                "value_minutes": 38.0,
                "sample_count": 50,
                "fallback_level": "AIRPORT_CELL",
                "provenance": [
                    "airport=ABE",
                    "n=50",
                    "fallback_level=AIRPORT_CELL",
                    "DATA2_TURNAROUND_REFERENCE@1.0.0",
                ],
            }
        ],
        "manifest_freeze_id": content_id({"synthetic": "turnaround-freeze"}),
        "support_state": "SUPPORTED",
    }
    taxi = {
        "reference_id": content_id({"synthetic": "taxi"}),
        "rule_id": "DATA2_TAXI_REFERENCE",
        "rule_version": "1.0.0",
        "fit_period": "2019-H1",
        "global_value_minutes": 15.0,
        "global_sample_count": 50,
        "cells": [
            {
                "airport_id": "ABE",
                "value_minutes": 15.0,
                "sample_count": 50,
                "fallback_level": "AIRPORT_CELL",
                "provenance": [
                    "airport=ABE",
                    "n=50",
                    "fallback_level=AIRPORT_CELL",
                    "DATA2_TAXI_REFERENCE@1.0.0",
                ],
            }
        ],
        "manifest_freeze_id": content_id({"synthetic": "taxi-freeze"}),
        "support_state": "SUPPORTED",
    }
    exposure = {
        "reference_id": content_id({"synthetic": "exposure"}),
        "rule_id": "DATA2_DOWNSTREAM_EXPOSURE",
        "rule_version": "1.0.0",
        "fit_period": "2019-H1",
        "global_value_legs": 1.0,
        "global_sample_count": 50,
        "cells": [
            {
                "airport_id": "ABE",
                "value_legs": 1.0,
                "sample_count": 50,
                "fallback_level": "AIRPORT_CELL",
                "provenance": [
                    "airport=ABE",
                    "n=50",
                    "fallback_level=AIRPORT_CELL",
                    "horizon_minutes=360",
                    "DATA2_DOWNSTREAM_EXPOSURE@1.0.0",
                ],
            }
        ],
        "manifest_freeze_id": content_id({"synthetic": "exposure-freeze"}),
        "support_state": "SUPPORTED",
    }
    passenger = {
        "reference_id": content_id({"synthetic": "passenger"}),
        "rule_id": "DATA2_PASSENGER_REFERENCE_H1",
        "rule_version": "1.0.0",
        "fit_period": "2019-H1",
        "total_passengers": 100.0,
        "total_sample_count": 10,
        "route_count": 1,
        "cells": [
            {
                "origin": "ABE",
                "destination": "ATL",
                "value_passengers": 100.0,
                "sample_count": 10,
                "provenance": [
                    "route=ABE|ATL",
                    "n_coupon_records=10",
                    "raw_passenger_sum=10",
                    "scale_factor=10",
                    "DATA2_PASSENGER_REFERENCE@1.0.0",
                ],
            }
        ],
        "manifest_freeze_id": content_id({"synthetic": "passenger-freeze"}),
        "support_state": "SUPPORTED",
    }
    return {
        "turnaround": turnaround,
        "taxi": taxi,
        "downstream_exposure": exposure,
        "passenger": passenger,
    }


__all__ = [
    "AirportReferenceKeys",
    "M2ReferenceBundle",
    "build_exp2_fixed_scope_pending",
    "build_m2_context",
    "load_data2_reference_bundle",
    "smoke_reference_payloads",
]
