from __future__ import annotations

from numbers import Real
from typing import Any, Mapping

from ..action_contract import load_action_contract
from .contracts import (
    COST_CHANNELS,
    EXPECTED_ACTION_IDS,
    FORBIDDEN_ACTION_IDS,
    FORBIDDEN_COMBINATION_TOKENS,
    M2_SUBITEM_CONTRACT_VERSION,
    M3_ACTION_LIBRARY_VERSION,
    M3_CONTRACT_VERSION,
    M3_RESPONSE_CONTRACT_VERSION,
    SUBITEMS_M2_V2,
    ActionCatalogEntry,
    ActionCostSpec,
    ActionFootprintSpec,
    ActionResponseParameterSpec,
    FootprintRole,
    M3ContractBundle,
    OutcomeCoverage,
    ParameterStatus,
)


def _optional_float(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError(f"M3_PARAMETER_TYPE_INVALID:{field}")
    return float(value)


def _m3_mapping(source: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if source is None:
        return load_action_contract(M3_CONTRACT_VERSION)
    candidate = source.get("m3") if "m3" in source else source
    if not isinstance(candidate, Mapping):
        raise ValueError("M3_CONTRACT_MISMATCH:missing M3 mapping")
    return candidate


def load_m3_contract(source: Mapping[str, Any] | None = None) -> M3ContractBundle:
    m3 = _m3_mapping(source)
    identity = str(m3.get("identity", {}).get("name", ""))
    versions = m3.get("version", {})
    status = m3.get("status", {})
    if identity != M3_CONTRACT_VERSION:
        raise ValueError(f"M3_CONTRACT_MISMATCH:{identity}")
    if versions.get("action_library") != M3_ACTION_LIBRARY_VERSION:
        raise ValueError("M3_CONTRACT_MISMATCH:action library version")
    if versions.get("response_contract") != M3_RESPONSE_CONTRACT_VERSION:
        raise ValueError("M3_CONTRACT_MISMATCH:response contract version")
    if not isinstance(status.get("scientific_approved"), bool) or not isinstance(
        status.get("publication_allowed"), bool
    ):
        raise ValueError("M3_CONTRACT_MISMATCH:status booleans")

    actions = m3.get("actions")
    if not isinstance(actions, list):
        raise ValueError("M3_CONTRACT_MISMATCH:actions")
    ids = tuple(str(item.get("action_id", "")) for item in actions)
    if ids != EXPECTED_ACTION_IDS or FORBIDDEN_ACTION_IDS.intersection(ids):
        raise ValueError("M3_CONTRACT_MISMATCH:atomic action library")
    if len(set(ids)) != len(ids):
        raise ValueError("M3_CONTRACT_MISMATCH:duplicate action_id")

    catalog: dict[str, ActionCatalogEntry] = {}
    footprints: dict[str, ActionFootprintSpec] = {}
    responses: dict[str, ActionResponseParameterSpec] = {}
    costs: dict[str, ActionCostSpec] = {}
    for raw in actions:
        action_id = str(raw["action_id"])
        action_name = str(raw["action_name"])
        identity_text = " ".join((action_name, str(raw["action_family"]))).upper()
        mechanism_text = str(raw["mechanism"]).upper()
        mechanism_tokens = tuple(
            token for token in FORBIDDEN_COMBINATION_TOKENS if token != "WITH"
        )
        if any(token in identity_text for token in FORBIDDEN_COMBINATION_TOKENS) or any(
            token in mechanism_text for token in mechanism_tokens
        ):
            raise ValueError(f"M3_CONTRACT_MISMATCH:combined action:{action_id}")
        parameter_status = ParameterStatus(str(raw["parameter_status"]))
        catalog[action_id] = ActionCatalogEntry(
            contract_identity=identity,
            action_library_version=M3_ACTION_LIBRARY_VERSION,
            action_id=action_id,
            action_name=action_name,
            action_family=str(raw["action_family"]),
            mechanism=str(raw["mechanism"]),
            lead_time=_optional_float(raw.get("lead_time"), f"{action_id}.lead_time"),
            applicable_stage=tuple(str(value) for value in raw["applicable_stage"]),
            outcome_coverage=OutcomeCoverage(str(raw["outcome_coverage"])),
            parameter_status=parameter_status,
        )

        footprint_raw = raw.get("footprint", {})
        if tuple(footprint_raw) != SUBITEMS_M2_V2:
            raise ValueError(f"M3_M2_CONTRACT_MISMATCH:unknown subitem:{action_id}")
        footprints[action_id] = ActionFootprintSpec(
            action_library_version=M3_ACTION_LIBRARY_VERSION,
            action_id=action_id,
            roles={name: FootprintRole(str(footprint_raw[name])) for name in SUBITEMS_M2_V2},
        )

        response = raw.get("response", {})
        responses[action_id] = ActionResponseParameterSpec(
            action_library_version=M3_ACTION_LIBRARY_VERSION,
            action_id=action_id,
            response_mean=_optional_float(response.get("response_mean"), f"{action_id}.response_mean"),
            response_concentration=_optional_float(
                response.get("response_concentration"), f"{action_id}.response_concentration"
            ),
            secondary_multiplier=_optional_float(
                response.get("secondary_multiplier"), f"{action_id}.secondary_multiplier"
            ),
            failure_probability=_optional_float(
                response.get("failure_probability"), f"{action_id}.failure_probability"
            ),
            parameter_status=ParameterStatus(str(response["parameter_status"])),
            parameter_source=str(response["parameter_source"]),
            parameter_version=str(response["parameter_version"]),
            test_only=bool(response.get("test_only", False)),
        )

        cost = raw.get("cost", {})
        costs[action_id] = ActionCostSpec(
            action_library_version=M3_ACTION_LIBRARY_VERSION,
            action_id=action_id,
            fixed_mean_rmb={
                channel: _optional_float(cost[channel].get("mean_rmb"), f"{action_id}.cost.{channel}")
                for channel in COST_CHANNELS
            },
            channel_status={
                channel: ParameterStatus(str(cost[channel]["status"]))
                for channel in COST_CHANNELS
            },
            cost_cv=_optional_float(cost.get("cost_cv"), f"{action_id}.cost_cv"),
            parameter_status=ParameterStatus(str(cost["parameter_status"])),
            parameter_source=str(cost["parameter_source"]),
            parameter_version=str(cost["parameter_version"]),
            test_only=bool(cost.get("test_only", False)),
        )

    required_m2 = {
        "contract_version": str(m3.get("required_m2_contract", "")),
        "subitem_contract_version": str(m3.get("required_subitem_contract", "")),
        "constructed_unit_version": str(m3.get("required_cu_version", "")),
        "valuation_version": str(m3.get("required_valuation_version", "")),
    }
    if required_m2["subitem_contract_version"] != M2_SUBITEM_CONTRACT_VERSION:
        raise ValueError("M3_CONTRACT_MISMATCH:required subitem contract")
    return M3ContractBundle(
        contract_identity=identity,
        action_library_version=M3_ACTION_LIBRARY_VERSION,
        response_contract_version=M3_RESPONSE_CONTRACT_VERSION,
        parameter_freeze_status=str(status["parameter_freeze"]),
        scientific_approved=bool(status["scientific_approved"]),
        publication_allowed=bool(status["publication_allowed"]),
        formal_library_status=str(status["formal_library"]),
        response_draw_count=int(m3["response_draw_count"]),
        base_seed=int(m3["base_seed"]),
        fixed_random_streams=bool(m3["fixed_random_streams"]),
        required_m2=required_m2,
        catalog=catalog,
        footprints=footprints,
        response_parameters=responses,
        cost_parameters=costs,
    )


def load_actions(scientific: Mapping[str, Any]) -> dict[str, ActionCatalogEntry]:
    """Return only the active V4 atomic catalog."""
    return dict(load_m3_contract(scientific).catalog)
