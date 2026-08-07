from __future__ import annotations

from typing import Iterable

import numpy as np

from ..m2.contracts import M2_CONTRACT_VERSION, M2InputBundle, M2SampleLoss
from ..m3.artifact import M3Artifact
from ..m3.contracts import (
    COST_CHANNELS,
    EXPECTED_ACTION_IDS,
    M3_ACTION_LIBRARY_VERSION,
    M3_CONTRACT_VERSION,
    M3_RESPONSE_CONTRACT_VERSION,
    SUBITEMS_M2_V2,
)
from .contracts import M4ContractError, M4UpstreamBlocked


SUBITEMS_BY_CHANNEL = {
    "F": SUBITEMS_M2_V2[0:3],
    "P": SUBITEMS_M2_V2[3:6],
    "R": SUBITEMS_M2_V2[6:9],
}


def _status(value: object) -> str:
    return str(getattr(value, "value", value))


def _finite_nonnegative(value: object, code: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise M4ContractError(code) from exc
    if not np.isfinite(number) or number < 0.0:
        raise M4ContractError(code)
    return number


def validate_m2_inputs(
    bundle: M2InputBundle,
    losses: tuple[M2SampleLoss, ...],
) -> np.ndarray:
    if not isinstance(bundle, M2InputBundle) or not isinstance(losses, tuple):
        raise M4ContractError("M4_LEGACY_M2_CHANNEL_ARRAYS_RETIRED")
    if bundle.metadata.m2_contract_version != M2_CONTRACT_VERSION:
        raise M4ContractError("M4_M2_CONTRACT_MISMATCH")
    if not losses or len(losses) != len(bundle.joint_scenarios):
        raise M4ContractError("M4_M2_SAMPLE_COUNT_MISMATCH")
    if tuple(bundle.subitem_activation) != SUBITEMS_M2_V2:
        raise M4ContractError("M4_M2_SUBITEM_ACTIVATION_SCHEMA_MISMATCH")

    weights: list[float] = []
    for expected_id, loss in enumerate(losses):
        if loss.sample_id != expected_id:
            raise M4ContractError("M4_M2_SAMPLE_ID_ALIGNMENT_FAILED")
        if loss.episode_id != bundle.metadata.episode_id:
            raise M4ContractError("M4_M2_EPISODE_ALIGNMENT_FAILED")
        if loss.snapshot_id != bundle.metadata.snapshot_id:
            raise M4ContractError("M4_M2_SNAPSHOT_ALIGNMENT_FAILED")
        if tuple(loss.subitem_loss_rmb) != SUBITEMS_M2_V2:
            raise M4ContractError(f"M4_M2_SUBITEM_SCHEMA_MISMATCH:{expected_id}")
        if tuple(loss.channel_loss_rmb) != COST_CHANNELS:
            raise M4ContractError(f"M4_M2_CHANNEL_SCHEMA_MISMATCH:{expected_id}")

        subitems = {
            name: _finite_nonnegative(
                loss.subitem_loss_rmb[name],
                f"M4_M2_SUBITEM_VALUE_MISSING_OR_INVALID:{expected_id}:{name}",
            )
            for name in SUBITEMS_M2_V2
        }
        channels = {
            channel: _finite_nonnegative(
                loss.channel_loss_rmb[channel],
                f"M4_M2_CHANNEL_VALUE_MISSING_OR_INVALID:{expected_id}:{channel}",
            )
            for channel in COST_CHANNELS
        }
        total = _finite_nonnegative(
            loss.total_pre_action_loss_rmb,
            f"M4_M2_TOTAL_VALUE_MISSING_OR_INVALID:{expected_id}",
        )
        for channel, names in SUBITEMS_BY_CHANNEL.items():
            expected_channel = sum(subitems[name] for name in names)
            if not np.isclose(channels[channel], expected_channel, atol=1e-8, rtol=1e-8):
                raise M4ContractError(
                    f"M4_M2_CHANNEL_IDENTITY_FAILURE:{expected_id}:{channel}"
                )
        if not np.isclose(total, sum(subitems.values()), atol=1e-8, rtol=1e-8):
            raise M4ContractError(f"M4_M2_TOTAL_IDENTITY_FAILURE:{expected_id}")
        weights.append(
            _finite_nonnegative(
                loss.sample_weight,
                f"M4_M2_SAMPLE_WEIGHT_INVALID:{expected_id}",
            )
        )
    result = np.asarray(weights, dtype=float)
    if float(result.sum()) <= 0.0:
        raise M4ContractError("M4_M2_SAMPLE_WEIGHT_SUM_NONPOSITIVE")
    return result


def validate_m3_artifact(artifact: M3Artifact, *, formal_mode: bool) -> None:
    if not isinstance(artifact, M3Artifact):
        raise M4ContractError("M4_LEGACY_M3_CHANNEL_RECOVERY_RETIRED")
    metadata = dict(artifact.version_metadata)
    if artifact.contract_version != M3_CONTRACT_VERSION:
        raise M4ContractError("M4_M3_CONTRACT_MISMATCH")
    if metadata.get("action_library") != M3_ACTION_LIBRARY_VERSION:
        raise M4ContractError("M4_M3_ACTION_LIBRARY_MISMATCH")
    if metadata.get("response_contract") != M3_RESPONSE_CONTRACT_VERSION:
        raise M4ContractError("M4_M3_RESPONSE_CONTRACT_MISMATCH")
    if tuple(artifact.action_catalog) != EXPECTED_ACTION_IDS:
        raise M4ContractError("M4_M3_ACTION_CATALOG_MISMATCH")
    if tuple(artifact.subitem_recovery_rates) != EXPECTED_ACTION_IDS:
        raise M4ContractError("M4_M3_RECOVERY_ACTION_SCHEMA_MISMATCH")
    if tuple(artifact.implementation_costs_rmb) != EXPECTED_ACTION_IDS:
        raise M4ContractError("M4_M3_COST_ACTION_SCHEMA_MISMATCH")
    if not artifact.artifact_hash or not artifact.sample_hash:
        raise M4ContractError("M4_M3_HASH_MISSING")

    draw_ids = np.asarray(artifact.response_draw_ids)
    if draw_ids.ndim != 1 or len(draw_ids) == 0:
        raise M4ContractError("M4_M3_RESPONSE_DRAWS_EMPTY")
    if not np.array_equal(draw_ids, np.arange(len(draw_ids))):
        raise M4ContractError("M4_M3_RESPONSE_DRAW_IDS_NONCONTIGUOUS")
    for action_id in EXPECTED_ACTION_IDS:
        recovery = np.asarray(artifact.subitem_recovery_rates[action_id], dtype=float)
        costs = np.asarray(artifact.implementation_costs_rmb[action_id], dtype=float)
        if recovery.shape != (len(draw_ids), len(SUBITEMS_M2_V2)):
            raise M4ContractError(f"M4_M3_RECOVERY_SHAPE_INVALID:{action_id}")
        if costs.shape != (len(draw_ids), len(COST_CHANNELS)):
            raise M4ContractError(f"M4_M3_COST_SHAPE_INVALID:{action_id}")
        if not np.isfinite(recovery).all() or np.any((recovery < 0.0) | (recovery > 1.0)):
            raise M4ContractError(f"M4_M3_RECOVERY_RANGE_INVALID:{action_id}")
        if not np.isfinite(costs).all() or np.any(costs < 0.0):
            raise M4ContractError(f"M4_M3_COST_RANGE_INVALID:{action_id}")
    if not np.all(np.asarray(artifact.subitem_recovery_rates["A00"]) == 0.0):
        raise M4ContractError("M4_A00_RECOVERY_IDENTITY_FAILURE")
    if not np.all(np.asarray(artifact.implementation_costs_rmb["A00"]) == 0.0):
        raise M4ContractError("M4_A00_COST_IDENTITY_FAILURE")

    if formal_mode:
        if artifact.test_only:
            raise M4UpstreamBlocked("TEST_ONLY_ARTIFACT")
        if artifact.parameter_freeze_status != "DONE":
            raise M4UpstreamBlocked("M3_PARAMETER_NOT_FROZEN")
        if artifact.formal_library_status != "READY":
            raise M4UpstreamBlocked("M3_FORMAL_LIBRARY_NOT_READY")
        publication_allowed = metadata.get("publication_allowed")
        if publication_allowed not in {True, "true", "TRUE", "YES"}:
            raise M4UpstreamBlocked("M3_FORMAL_LIBRARY_NOT_READY")


def formal_m2_blockers(bundle: M2InputBundle, losses: Iterable[M2SampleLoss]) -> tuple[str, ...]:
    reasons: list[str] = []
    if _status(bundle.input_status) == "PARTIAL":
        reasons.append("M2_INPUT_PARTIAL")
    if _status(bundle.input_status) == "ABSTAIN":
        reasons.append("M2_INPUT_ABSTAIN")
    if _status(bundle.valuation_context.parameter_status) != "CONFIGURED":
        reasons.append("M2_VALUATION_NOT_FROZEN")
    if bundle.valuation_context.test_only:
        reasons.append("TEST_ONLY_ARTIFACT")
    if bundle.audit_context.formal_reconstruction_gate != "PASS":
        reasons.append("M2_INPUT_ABSTAIN")
    if bundle.audit_context.audit_status != "VALIDATED":
        reasons.append("CONTRACT_MISMATCH")
    if any("UNRESOLVED" in str(loss.tail_resolution_status) for loss in losses):
        reasons.append("M2_TAIL_UNRESOLVED")
    return tuple(dict.fromkeys(reasons))
