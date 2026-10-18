"""Exp2 analysis-level common-scenario support.

This module does not alter M1 or M2 support semantics. It identifies the
scenario probability mass on which M1 ``D_TO`` and all seven M2 V4 outputs
are jointly usable, then computes explicitly conditional Exp2 summaries.
"""

from __future__ import annotations

from math import isclose, isfinite
from typing import Iterable, Mapping

from model.M2.contracts import M2ScenarioInput, ScenarioConsequence
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import SupportState
from model.common.estimand import FormalEstimandStatus

from .protocol import (
    COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
    COMPONENTS,
    PRIMARY_SUPPORT_THRESHOLD,
    SENSITIVITY_SUPPORT_THRESHOLD,
)

FULL_SUPPORT_THRESHOLD = 1.0
SUPPORT_TOLERANCE = 1e-9


def _finite(value: object) -> bool:
    return value is not None and isfinite(float(value))


def identify_common_supported_scenarios(
    typed: Iterable[M2ScenarioInput],
    mapped: Iterable[ScenarioConsequence],
    registry: FrozenData2CUNormalizationRegistry,
) -> tuple[dict[str, object], ...]:
    """Return aligned scenario records with typed unsupported reasons."""
    cu_registry = getattr(registry, "registry", registry)
    inputs = tuple(typed)
    outputs = tuple(mapped)
    if not inputs or len(inputs) != len(outputs):
        raise ValueError("EXP2_NODE_SCENARIO_CARDINALITY_INVALID")
    if len({item.scenario_id for item in inputs}) != len(inputs):
        raise ValueError("EXP2_DUPLICATE_SCENARIO_ID")

    records: list[dict[str, object]] = []
    for scenario, consequence in zip(inputs, outputs):
        if (
            scenario.episode_id,
            scenario.decision_node_id,
            scenario.scenario_id,
        ) != (
            consequence.episode_id,
            consequence.decision_node_id,
            consequence.scenario_id,
        ):
            raise ValueError("EXP2_M1_M2_SCENARIO_IDENTITY_MISMATCH")
        if not isclose(
            float(scenario.scenario_weight),
            float(consequence.scenario_weight),
            abs_tol=1e-12,
        ):
            raise ValueError("EXP2_M1_M2_SCENARIO_WEIGHT_MISMATCH")

        component_rows = tuple(consequence.component_vector.rows)
        if tuple(row.component_id for row in component_rows) != COMPONENTS:
            raise ValueError("EXP2_EXACT_SEVEN_COMPONENT_VECTOR_REQUIRED")

        delay_supported = (
            scenario.d_to_support is not SupportState.ABSTAIN
            and _finite(scenario.d_to_minutes)
        )
        component_support: dict[str, bool] = {}
        unsupported_reasons: list[str] = []
        if not delay_supported:
            unsupported_reasons.append("D_TO")

        for row in component_rows:
            supported = (
                row.support_state is not SupportState.ABSTAIN
                and _finite(row.native_quantity)
                and _finite(row.constructed_value_cu)
                and row.cu_status is CUNormalizationStatus.CU_FROZEN
                and row.cu_quantity.compatible_with_registry(cu_registry)
            )
            component_support[row.component_id] = supported
            if not supported:
                unsupported_reasons.append(row.component_id)

        all_components_supported = all(component_support.values())
        formal_status = FormalEstimandStatus(
            consequence.formal_estimand_value.status
        )
        formal_available = formal_status is FormalEstimandStatus.FORMAL_AVAILABLE
        if formal_available != all_components_supported:
            raise RuntimeError("EXP2_M2_FORMAL_COMPONENT_SUPPORT_MISMATCH")

        records.append(
            {
                "scenario_id": int(scenario.scenario_id),
                "scenario_weight": float(scenario.scenario_weight),
                "common_supported": bool(
                    delay_supported and all_components_supported
                ),
                "unsupported_reasons": tuple(unsupported_reasons),
                "delay_to": (
                    float(scenario.d_to_minutes) if delay_supported else None
                ),
                "component_rows": component_rows,
                "formal_scenario_status": formal_status.value,
            }
        )

    total_weight = sum(float(row["scenario_weight"]) for row in records)
    if not isclose(total_weight, 1.0, abs_tol=1e-6):
        raise ValueError("EXP2_SCENARIO_WEIGHTS_MUST_SUM_TO_ONE")
    if any(float(row["scenario_weight"]) <= 0 for row in records):
        raise ValueError("EXP2_SCENARIO_WEIGHTS_MUST_BE_POSITIVE")
    return tuple(records)


def compute_common_support_mass(records: Iterable[Mapping[str, object]]) -> float:
    """Sum scenario weights on common support; never use a fixed count."""
    mass = sum(
        float(row["scenario_weight"])
        for row in records
        if bool(row["common_supported"])
    )
    if mass < -SUPPORT_TOLERANCE or mass > 1.0 + SUPPORT_TOLERANCE:
        raise ValueError("EXP2_COMMON_SUPPORT_MASS_OUT_OF_RANGE")
    return min(1.0, max(0.0, float(mass)))


def support_flags(mass: float) -> dict[str, bool]:
    """Apply the frozen 90%, 50%, and full-support thresholds."""
    if not isfinite(float(mass)) or not -SUPPORT_TOLERANCE <= mass <= 1.0 + SUPPORT_TOLERANCE:
        raise ValueError("EXP2_COMMON_SUPPORT_MASS_INVALID")
    return {
        "support_primary": bool(
            mass >= PRIMARY_SUPPORT_THRESHOLD
            or isclose(mass, PRIMARY_SUPPORT_THRESHOLD, abs_tol=SUPPORT_TOLERANCE)
        ),
        "support_sensitivity": bool(
            mass >= SENSITIVITY_SUPPORT_THRESHOLD
            or isclose(
                mass, SENSITIVITY_SUPPORT_THRESHOLD, abs_tol=SUPPORT_TOLERANCE
            )
        ),
        "support_full": bool(
            isclose(mass, FULL_SUPPORT_THRESHOLD, abs_tol=SUPPORT_TOLERANCE)
        ),
    }


def conditional_node_summary(
    records: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Compute node summaries conditional on Exp2 common scenario support."""
    rows = tuple(records)
    mass = compute_common_support_mass(rows)
    selected = tuple(row for row in rows if bool(row["common_supported"]))
    flags = support_flags(mass)
    result: dict[str, object] = {
        "common_support_rule_id": "EXP2_COMMON_SUPPORT_MASS_V1",
        "common_support_estimand": COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
        "common_support_mass": mass,
        "common_support_scenario_count": len(selected),
        "scenario_count_total": len(rows),
        **flags,
        "conditional_aggregate_complete": bool(selected),
        "formal_full_support": flags["support_full"],
        "full_support": flags["support_full"],
        "full_support_mass": mass,
    }

    if not selected:
        result["delay_to_mean_cs"] = None
        result["formal_delay_mean_if_full"] = None
        for component in COMPONENTS:
            result[f"{component}_native_cs"] = None
            result[f"Z_{component}_cs"] = None
            result[f"{component}_native_if_full"] = None
            result[f"Z_{component}_if_full"] = None
        return result

    def conditional_mean(values: Iterable[float], weights: Iterable[float]) -> float:
        return sum(value * weight for value, weight in zip(values, weights)) / mass

    selected_weights = tuple(float(row["scenario_weight"]) for row in selected)
    result["delay_to_mean_cs"] = conditional_mean(
        (float(row["delay_to"]) for row in selected), selected_weights
    )
    for component_index, component in enumerate(COMPONENTS):
        component_rows = tuple(
            row["component_rows"][component_index] for row in selected
        )
        result[f"{component}_native_cs"] = conditional_mean(
            (float(row.native_quantity) for row in component_rows), selected_weights
        )
        result[f"Z_{component}_cs"] = conditional_mean(
            (float(row.constructed_value_cu) for row in component_rows),
            selected_weights,
        )

    if flags["support_full"]:
        result["formal_delay_mean_if_full"] = result["delay_to_mean_cs"]
        for component in COMPONENTS:
            result[f"{component}_native_if_full"] = result[
                f"{component}_native_cs"
            ]
            result[f"Z_{component}_if_full"] = result[f"Z_{component}_cs"]
    else:
        result["formal_delay_mean_if_full"] = None
        for component in COMPONENTS:
            result[f"{component}_native_if_full"] = None
            result[f"Z_{component}_if_full"] = None
    return result
