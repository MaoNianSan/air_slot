from __future__ import annotations

from .contracts import (
    COST_CHANNELS,
    ActionCostSpec,
    ActionResponseParameterSpec,
    M3ContractBundle,
    ParameterStatus,
)


SYNTHETIC_FIXTURE_VERSION = "M3_V4_SYNTHETIC_FIXTURE_V1"


def synthetic_test_parameters(
    contract: M3ContractBundle,
) -> tuple[dict[str, ActionResponseParameterSpec], dict[str, ActionCostSpec]]:
    """Return deterministic values that are forbidden outside structural tests."""
    responses: dict[str, ActionResponseParameterSpec] = {}
    costs: dict[str, ActionCostSpec] = {}
    for index, action_id in enumerate(contract.catalog):
        if action_id == "A00":
            response_mean = 0.0
            concentration = None
            secondary = 0.0
            failure = 0.0
            fixed = {channel: 0.0 for channel in COST_CHANNELS}
            cost_cv = 0.0
        else:
            response_mean = 0.35 + 0.025 * (index % 8)
            concentration = 12.0 + float(index % 5)
            secondary = 0.35
            failure = 0.04 + 0.01 * (index % 4)
            fixed = {
                "F": 8.0 + float(index),
                "P": 5.0 + 0.5 * float(index),
                "R": 6.0 + 0.75 * float(index),
            }
            cost_cv = 0.12
        responses[action_id] = ActionResponseParameterSpec(
            action_library_version=contract.action_library_version,
            action_id=action_id,
            response_mean=response_mean,
            response_concentration=concentration,
            secondary_multiplier=secondary,
            failure_probability=failure,
            parameter_status=ParameterStatus.FROZEN_FOR_VALIDATION,
            parameter_source="SYNTHETIC_FIXTURE",
            parameter_version=SYNTHETIC_FIXTURE_VERSION,
            test_only=True,
        )
        costs[action_id] = ActionCostSpec(
            action_library_version=contract.action_library_version,
            action_id=action_id,
            fixed_mean_rmb=fixed,
            channel_status={
                channel: ParameterStatus.FROZEN_FOR_VALIDATION
                for channel in COST_CHANNELS
            },
            cost_cv=cost_cv,
            parameter_status=ParameterStatus.FROZEN_FOR_VALIDATION,
            parameter_source="SYNTHETIC_FIXTURE",
            parameter_version=SYNTHETIC_FIXTURE_VERSION,
            test_only=True,
        )
    return responses, costs
