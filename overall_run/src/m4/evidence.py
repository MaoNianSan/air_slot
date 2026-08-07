from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from ..m2.contracts import AvailabilityStatus, M2InputBundle
from .contracts import M4ContractError, M4EvidenceContext


PRE_LINEAGE_KEY = "__pre_lineage__"
PRE_STAGE_KEY = "__stage__"


@dataclass(frozen=True)
class EvidenceRequirement:
    fields: tuple[str, ...]
    missing_reason: str
    conditional_when_proxy: bool = True


REQUIRED_EVIDENCE_BY_ACTION: Mapping[str, tuple[EvidenceRequirement, ...]] = {
    "A00": (),
    "A11": (EvidenceRequirement(("connection_slack", "connection_pressure"), "PASSENGER_CONNECTION_NOT_FORMAL"),),
    "A12": (EvidenceRequirement(("execution_window_margin",), "PRE_EVIDENCE_UNSUPPORTED"),),
    "A13": (EvidenceRequirement(("taxi_reference",), "TAXI_REFERENCE_UNSUPPORTED"),),
    "A21": (EvidenceRequirement(("execution_window_margin",), "PRE_EVIDENCE_UNSUPPORTED"),),
    "A22": (EvidenceRequirement(("airport_flow_pressure",), "PRE_EVIDENCE_UNSUPPORTED"),),
    "A23": (EvidenceRequirement(("airport_flow_pressure",), "PRE_EVIDENCE_UNSUPPORTED"),),
    "A31": (EvidenceRequirement(("rebooking_scarcity",), "PASSENGER_CONNECTION_NOT_FORMAL"),),
    "A33": (EvidenceRequirement(("passenger_care_rule", "passenger_load_proxy"), "PASSENGER_CONNECTION_NOT_FORMAL"),),
    "A41": (EvidenceRequirement(("gate_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A42": (EvidenceRequirement(("ground_handler_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A43": (EvidenceRequirement(("tow_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A51": (EvidenceRequirement(("aircraft_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A52": (EvidenceRequirement(("aircraft_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A53": (EvidenceRequirement(("standby_aircraft_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A61": (EvidenceRequirement(("crew_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A62": (EvidenceRequirement(("standby_crew_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A63": (EvidenceRequirement(("crew_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A64": (EvidenceRequirement(("crew_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
    "A71": (),
    "A72": (EvidenceRequirement(("aircraft_resource_availability",), "RESOURCE_NETWORK_NOT_AVAILABLE"),),
}


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _status(value: object) -> str:
    return str(getattr(value, "value", value)).upper()


def _lineage_value(provenance: Mapping[str, Mapping[str, object]], key: str) -> object | None:
    direct = provenance.get(PRE_LINEAGE_KEY, {}).get(key)
    if direct is not None:
        return direct
    for item in provenance.values():
        if isinstance(item, Mapping) and item.get(key) is not None:
            return item[key]
    return None


def _evidence_type(
    field: str,
    provenance: Mapping[str, Mapping[str, object]],
    support: Mapping[str, object],
) -> str:
    item = provenance.get(field, {})
    explicit = item.get("evidence_type") if isinstance(item, Mapping) else None
    if explicit:
        return str(explicit).upper()
    label = _status(support.get(field, "UNSUPPORTED"))
    if label in {AvailabilityStatus.PROXY_AVAILABLE.value, "EMPIRICAL_REFERENCE"}:
        return "EMPIRICAL_REFERENCE"
    if label == AvailabilityStatus.UNSUPPORTED.value:
        return "UNSUPPORTED"
    return "UNKNOWN"


def validate_forbidden_inferences(bundle: M2InputBundle) -> None:
    provenance = bundle.context_provenance
    resource = provenance.get("resource_availability", {})
    resource_text = json.dumps(resource, ensure_ascii=True, sort_keys=True).lower()
    if "airport_flow_pressure" in resource_text or "ground_support_pressure" in resource_text:
        raise M4ContractError("M4_FORBIDDEN_PRESSURE_TO_RESOURCE_INFERENCE")
    ground = provenance.get("ground_handler_availability", {})
    ground_text = json.dumps(ground, ensure_ascii=True, sort_keys=True).lower()
    if "ground_support_pressure" in ground_text or "ground_occupancy" in ground_text:
        raise M4ContractError("M4_FORBIDDEN_OCCUPANCY_TO_HANDLER_INFERENCE")
    for field in ("continuity_exposure", "downstream_leg_count"):
        item = provenance.get(field, {})
        if bool(item.get("future_observed_chain_used", False)):
            raise M4ContractError("M4_FORBIDDEN_FUTURE_OBSERVED_CHAIN")
    for field, item in provenance.items():
        if not isinstance(item, Mapping):
            continue
        if bool(item.get("proxy_labeled_observed", False)):
            raise M4ContractError(f"M4_FORBIDDEN_PROXY_TO_OBSERVED:{field}")


def build_evidence_context(bundle: M2InputBundle) -> M4EvidenceContext:
    validate_forbidden_inferences(bundle)
    provenance = bundle.context_provenance
    lineage = dict(provenance.get(PRE_LINEAGE_KEY, {}))
    contract_id = str(_lineage_value(provenance, "pre_contract_id") or "UNKNOWN")
    schema_version = str(_lineage_value(provenance, "pre_schema_version") or "UNKNOWN")
    research_revision = str(
        _lineage_value(provenance, "pre_research_revision") or "UNKNOWN"
    )
    input_rule_hash = _lineage_value(provenance, "input_rule_registry_hash")
    formula_hash = _lineage_value(provenance, "formula_registry_hash")
    availability = str(
        _lineage_value(provenance, "availability_policy_status") or "UNKNOWN"
    )
    field_names = sorted(
        set(bundle.context_support)
        | {name for name in provenance if not name.startswith("__")}
    )
    evidence_types = {
        field: _evidence_type(field, provenance, bundle.context_support)
        for field in field_names
    }
    proxy_statuses = {
        field: str(
            provenance.get(field, {}).get(
                "proxy_status", bundle.audit_context.proxy_status.get(field, "NONE")
            )
        )
        for field in field_names
    }
    assumption_matches = {
        field: str(provenance.get(field, {}).get("assumption_match_status", "NOT_APPLICABLE"))
        for field in field_names
    }
    unsupported = tuple(
        field for field, value in evidence_types.items() if value == "UNSUPPORTED"
    )
    scenario = tuple(
        field for field, value in evidence_types.items() if value == "SCENARIO_PARAMETER"
    )
    reasons: list[str] = []
    if (
        contract_id == "AIR_CHAIN_CORE_V2"
        and schema_version == "air-chain-core-2.0"
        and research_revision == "AIR_CHAIN_CORE_V2_R2"
    ):
        reasons.append("PRE_R2_COMPATIBILITY_ONLY")
    elif not (
        contract_id == "AIR_CHAIN_CORE_V2"
        and schema_version == "air-chain-core-2.1"
        and research_revision == "AIR_CHAIN_CORE_V2_R3"
    ):
        reasons.append("PRE_R3_NOT_AVAILABLE")
    if schema_version == "air-chain-core-2.1" and (not input_rule_hash or not formula_hash):
        reasons.append("PRE_R3_REGISTRY_MISSING")
    payload = {
        "lineage": lineage,
        "contract_id": contract_id,
        "schema_version": schema_version,
        "research_revision": research_revision,
        "pre_bundle_id": bundle.metadata.pre_bundle_id,
        "information_cutoff": bundle.metadata.information_cutoff,
        "evidence_types": evidence_types,
        "proxy_statuses": proxy_statuses,
        "assumption_matches": assumption_matches,
    }
    return M4EvidenceContext(
        pre_contract_id=contract_id,
        pre_schema_version=schema_version,
        pre_research_revision=research_revision,
        pre_bundle_id=bundle.metadata.pre_bundle_id,
        information_cutoff=bundle.metadata.information_cutoff,
        availability_policy_status=availability,
        input_rule_registry_hash=str(input_rule_hash) if input_rule_hash else None,
        formula_registry_hash=str(formula_hash) if formula_hash else None,
        evidence_types=evidence_types,
        proxy_statuses=proxy_statuses,
        assumption_match_statuses=assumption_matches,
        unsupported_fields=unsupported,
        scenario_parameter_fields=scenario,
        lineage_hash=_canonical_hash(payload),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def evidence_reasons_for_action(
    action_id: str,
    context: M4EvidenceContext,
) -> tuple[str, ...]:
    reasons: list[str] = list(context.reason_codes)
    for requirement in REQUIRED_EVIDENCE_BY_ACTION.get(action_id, ()):
        available = False
        proxy_only = False
        for field in requirement.fields:
            evidence = context.evidence_types.get(field, "UNSUPPORTED")
            assumption = context.assumption_match_statuses.get(field, "NOT_APPLICABLE")
            if evidence in {"DERIVED", "EMPIRICAL_REFERENCE", "EXTERNAL_STANDARD"}:
                available = True
            if evidence == "EMPIRICAL_REFERENCE" or context.proxy_statuses.get(field, "NONE") not in {
                "NONE", "NOT_APPLICABLE", "OBSERVED"
            }:
                proxy_only = True
            if evidence == "SCENARIO_PARAMETER":
                reasons.append("PRE_SCENARIO_PARAMETER_REQUIRED")
            if evidence == "EXTERNAL_STANDARD" and assumption not in {
                "MATCH", "MATCHED", "PASS", "NOT_APPLICABLE"
            }:
                reasons.append("PRE_ASSUMPTION_MISMATCH")
        if not available:
            reasons.append(requirement.missing_reason)
        elif proxy_only and requirement.conditional_when_proxy:
            reasons.append("M2_PROXY_DEPENDENT")
    return tuple(dict.fromkeys(reasons))
