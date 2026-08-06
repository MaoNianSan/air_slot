from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..utils import stable_hash, stable_seed
from .artifact import M3Artifact
from .compatibility import validate_m2_compatibility
from .contracts import (
    COST_CHANNELS,
    SUBITEMS_M2_V2,
    ActionCostSpec,
    ActionResponseParameterSpec,
    FootprintRole,
    M3ContractBundle,
    ParameterStatus,
)
from .costs import generate_implementation_costs
from .footprint import footprint_frame, validate_semantic_footprints
from .parameters import synthetic_test_parameters


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return stable_hash(payload)


def _validate_parameter_sets(
    contract: M3ContractBundle,
    responses: Mapping[str, ActionResponseParameterSpec],
    costs: Mapping[str, ActionCostSpec],
    *,
    formal: bool,
) -> None:
    if tuple(responses) != tuple(contract.catalog) or tuple(costs) != tuple(contract.catalog):
        raise RuntimeError("M3_PARAMETER_ACTION_COVERAGE_MISMATCH")
    for action_id in contract.catalog:
        response = responses[action_id]
        cost = costs[action_id]
        if formal:
            if (
                response.parameter_status is not ParameterStatus.FROZEN_FOR_VALIDATION
                or cost.parameter_status is not ParameterStatus.FROZEN_FOR_VALIDATION
                or response.test_only
                or cost.test_only
            ):
                raise RuntimeError(f"M3_PARAMETER_NOT_FROZEN:{action_id}")
        elif not response.test_only or not cost.test_only:
            raise RuntimeError(f"M3_TEST_FIXTURE_MARKER_REQUIRED:{action_id}")
        if action_id == "A00":
            continue
        values = (
            response.response_mean,
            response.response_concentration,
            response.secondary_multiplier,
            response.failure_probability,
        )
        if any(value is None for value in values):
            raise RuntimeError(f"M3_PARAMETER_NOT_FROZEN:{action_id}:response")
        if not 0.0 < float(response.response_mean) < 1.0:
            raise ValueError(f"M3_RESPONSE_MEAN_INVALID:{action_id}")
        if float(response.response_concentration) <= 0.0:
            raise ValueError(f"M3_RESPONSE_CONCENTRATION_INVALID:{action_id}")
        if not 0.0 <= float(response.secondary_multiplier) <= 1.0:
            raise ValueError(f"M3_SECONDARY_MULTIPLIER_INVALID:{action_id}")
        if not 0.0 <= float(response.failure_probability) <= 1.0:
            raise ValueError(f"M3_FAILURE_PROBABILITY_INVALID:{action_id}")


def _response_parameter_frame(
    parameters: Mapping[str, ActionResponseParameterSpec],
) -> pd.DataFrame:
    return pd.DataFrame([asdict(parameters[action_id]) for action_id in parameters])


def _cost_parameter_frame(parameters: Mapping[str, ActionCostSpec]) -> pd.DataFrame:
    rows = []
    for action_id, item in parameters.items():
        row = asdict(item)
        fixed = row.pop("fixed_mean_rmb")
        statuses = row.pop("channel_status")
        row.update({f"fixed_mean_rmb_{channel}": fixed[channel] for channel in COST_CHANNELS})
        row.update({f"status_{channel}": statuses[channel] for channel in COST_CHANNELS})
        rows.append(row)
    return pd.DataFrame(rows)


def generate_m3_library(
    contract: M3ContractBundle,
    *,
    n_draws: int | None = None,
    base_seed: int | None = None,
    response_parameters: Mapping[str, ActionResponseParameterSpec] | None = None,
    cost_parameters: Mapping[str, ActionCostSpec] | None = None,
    m2_contract: Mapping[str, Any] | Any | None = None,
    formal: bool = True,
) -> M3Artifact:
    validate_semantic_footprints(contract)
    draw_count = contract.response_draw_count if n_draws is None else int(n_draws)
    seed = contract.base_seed if base_seed is None else int(base_seed)
    if draw_count <= 0:
        raise ValueError("M3_RESPONSE_DRAW_COUNT_MUST_BE_POSITIVE")
    responses = response_parameters or contract.response_parameters
    costs = cost_parameters or contract.cost_parameters
    _validate_parameter_sets(contract, responses, costs, formal=formal)
    compatibility = (
        validate_m2_compatibility(contract, m2_contract).as_dict()
        if m2_contract is not None
        else {"status": "NOT_CHECKED"}
    )
    if compatibility["status"] != "PASS":
        raise RuntimeError("M3_M2_CONTRACT_MISMATCH:compatibility not checked")

    recovery_by_action: dict[str, np.ndarray] = {}
    cost_by_action: dict[str, np.ndarray] = {}
    success_by_action: dict[str, np.ndarray] = {}
    intensity_by_action: dict[str, np.ndarray] = {}
    audit_rows = []
    response_draw_ids = np.arange(draw_count, dtype=np.int32)
    for action_id in contract.catalog:
        response = responses[action_id]
        cost = costs[action_id]
        random_parameter_version = f"{response.parameter_version}|{cost.parameter_version}"
        recovery = np.zeros((draw_count, len(SUBITEMS_M2_V2)), dtype=np.float64)
        if action_id == "A00":
            success = np.ones(draw_count, dtype=bool)
            intensity = np.zeros(draw_count, dtype=np.float64)
        else:
            success_rng = np.random.default_rng(stable_seed(
                seed,
                contract.action_library_version,
                random_parameter_version,
                action_id,
                "success",
            ))
            intensity_rng = np.random.default_rng(stable_seed(
                seed,
                contract.action_library_version,
                random_parameter_version,
                action_id,
                "response_intensity",
            ))
            success = success_rng.random(draw_count) >= float(response.failure_probability)
            alpha = float(response.response_mean) * float(response.response_concentration)
            beta = (1.0 - float(response.response_mean)) * float(response.response_concentration)
            intensity = intensity_rng.beta(alpha, beta, size=draw_count)
            for index, subitem_id in enumerate(SUBITEMS_M2_V2):
                role = contract.footprints[action_id].roles[subitem_id]
                weight = (
                    1.0
                    if role is FootprintRole.PRIMARY
                    else float(response.secondary_multiplier)
                    if role is FootprintRole.SECONDARY
                    else 0.0
                )
                recovery[:, index] = np.where(success, weight * intensity, 0.0)
        implementation_cost = generate_implementation_costs(
            cost,
            n_draws=draw_count,
            base_seed=seed,
            action_library_version=contract.action_library_version,
            random_parameter_version=random_parameter_version,
        )
        recovery_by_action[action_id] = recovery
        cost_by_action[action_id] = implementation_cost
        success_by_action[action_id] = success
        intensity_by_action[action_id] = intensity
        none_columns = [
            index
            for index, subitem_id in enumerate(SUBITEMS_M2_V2)
            if contract.footprints[action_id].roles[subitem_id] is FootprintRole.NONE
        ]
        audit_rows.append({
            "action_id": action_id,
            "response_draw_count": draw_count,
            "empirical_failure_rate": 0.0 if action_id == "A00" else float((~success).mean()),
            "recovery_min": float(recovery.min()),
            "recovery_max": float(recovery.max()),
            "implementation_cost_min_rmb": float(implementation_cost.min()),
            "implementation_cost_max_rmb": float(implementation_cost.max()),
            "structural_none_exact": bool(
                not none_columns or np.all(recovery[:, none_columns] == 0.0)
            ),
        })

    footprint_table = footprint_frame(contract)
    response_table = _response_parameter_frame(responses)
    cost_table = _cost_parameter_frame(costs)
    action_library_hash = _canonical_hash([asdict(item) for item in contract.catalog.values()])
    footprint_hash = _canonical_hash(footprint_table.to_dict("records"))
    parameter_hash = _canonical_hash({
        "response": response_table.to_dict("records"),
        "cost": cost_table.to_dict("records"),
    })
    sample_hash = _canonical_hash({
        action_id: {
            "recovery": recovery_by_action[action_id].tolist(),
            "cost": cost_by_action[action_id].tolist(),
            "success": success_by_action[action_id].astype(int).tolist(),
            "intensity": intensity_by_action[action_id].tolist(),
        }
        for action_id in contract.catalog
    })
    version_metadata = {
        "identity": contract.contract_identity,
        "action_library": contract.action_library_version,
        "response_contract": contract.response_contract_version,
        "subitem_contract": contract.required_m2["subitem_contract_version"],
    }
    artifact_hash = _canonical_hash({
        "version": version_metadata,
        "action_library_hash": action_library_hash,
        "footprint_hash": footprint_hash,
        "parameter_hash": parameter_hash,
        "sample_hash": sample_hash,
    })
    artifact = M3Artifact(
        response_draw_ids=response_draw_ids,
        subitem_recovery_rates=recovery_by_action,
        implementation_costs_rmb=cost_by_action,
        success_draws=success_by_action,
        response_intensities=intensity_by_action,
        action_catalog=contract.catalog,
        footprint_table=footprint_table,
        response_parameter_table=response_table,
        cost_parameter_table=cost_table,
        response_audit=pd.DataFrame(audit_rows),
        version_metadata=version_metadata,
        action_library_hash=action_library_hash,
        footprint_hash=footprint_hash,
        parameter_hash=parameter_hash,
        sample_hash=sample_hash,
        artifact_hash=artifact_hash,
        m2_compatibility=compatibility,
        parameter_freeze_status="NOT_READY",
        formal_library_status=contract.formal_library_status,
        test_only=not formal,
    )
    _validate_artifact(artifact, contract)
    return artifact


def generate_test_fixture_library(
    contract: M3ContractBundle,
    *,
    n_draws: int,
    base_seed: int,
    m2_contract: Mapping[str, Any] | Any,
) -> M3Artifact:
    responses, costs = synthetic_test_parameters(contract)
    return generate_m3_library(
        contract,
        n_draws=n_draws,
        base_seed=base_seed,
        response_parameters=responses,
        cost_parameters=costs,
        m2_contract=m2_contract,
        formal=False,
    )


def _validate_artifact(artifact: M3Artifact, contract: M3ContractBundle) -> None:
    if tuple(artifact.subitem_recovery_rates) != tuple(contract.catalog):
        raise RuntimeError("M3_ACTION_COVERAGE_FAILURE")
    for action_id in contract.catalog:
        recovery = np.asarray(artifact.subitem_recovery_rates[action_id], dtype=float)
        costs = np.asarray(artifact.implementation_costs_rmb[action_id], dtype=float)
        if recovery.shape != (artifact.n_draws, len(SUBITEMS_M2_V2)):
            raise RuntimeError(f"M3_RESPONSE_SHAPE_FAILURE:{action_id}")
        if costs.shape != (artifact.n_draws, len(COST_CHANNELS)):
            raise RuntimeError(f"M3_COST_SHAPE_FAILURE:{action_id}")
        if not np.isfinite(recovery).all() or np.any((recovery < 0.0) | (recovery > 1.0)):
            raise RuntimeError(f"M3_RECOVERY_BOUND_FAILURE:{action_id}")
        if not np.isfinite(costs).all() or np.any(costs < 0.0):
            raise RuntimeError(f"M3_COST_BOUND_FAILURE:{action_id}")
    if not np.all(artifact.subitem_recovery_rates["A00"] == 0.0):
        raise RuntimeError("M3_A00_RECOVERY_IDENTITY_FAILURE")
    if not np.all(artifact.implementation_costs_rmb["A00"] == 0.0):
        raise RuntimeError("M3_A00_COST_IDENTITY_FAILURE")
    if not np.all(artifact.success_draws["A00"]):
        raise RuntimeError("M3_A00_SUCCESS_IDENTITY_FAILURE")
