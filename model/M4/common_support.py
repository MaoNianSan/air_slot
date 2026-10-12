from __future__ import annotations

from math import isclose, isfinite
from typing import Any

from model.M2.contracts import M2ScenarioInput, ScenarioConsequence
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import SupportState
from model.common.errors import ContractError

WEIGHT_REL_TOL = 1e-9
WEIGHT_ABS_TOL = 1e-12
MASS_REL_TOL = 1e-9
MASS_ABS_TOL = 1e-9


def _fail(code: str) -> None:
    raise ContractError(code)


def _finite(value: Any) -> bool:
    return value is not None and isfinite(float(value))


def _state_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def validate_node_inputs(
    node,
    scenarios: tuple[M2ScenarioInput, ...],
    consequences: tuple[ScenarioConsequence, ...],
) -> None:
    if not scenarios or len(scenarios) != len(consequences):
        _fail("M4_SCENARIO_CARDINALITY_INVALID")
    scenario_ids = tuple(item.scenario_id for item in scenarios)
    consequence_ids = tuple(item.scenario_id for item in consequences)
    if len(set(scenario_ids)) != len(scenario_ids) or len(set(consequence_ids)) != len(consequence_ids):
        _fail("M4_DUPLICATE_SCENARIO_ID")
    if node is not None and any(
        (item.episode_id, item.decision_node_id)
        != (node.episode_id, node.decision_node_id)
        for item in scenarios + consequences
    ):
        _fail("M4_NODE_IDENTITY_MISMATCH")
    if scenario_ids != consequence_ids:
        _fail("M4_SCENARIO_IDENTITY_MISMATCH")
    for left, right in zip(scenarios, consequences, strict=True):
        if not isclose(
            float(left.scenario_weight),
            float(right.scenario_weight),
            rel_tol=WEIGHT_REL_TOL,
            abs_tol=WEIGHT_ABS_TOL,
        ):
            _fail("M4_SCENARIO_WEIGHT_MISMATCH")
    weights = tuple(float(item.scenario_weight) for item in scenarios)
    if any(not isfinite(item) or item <= 0 for item in weights) or not isclose(
        sum(weights), 1.0, rel_tol=WEIGHT_REL_TOL, abs_tol=1e-6
    ):
        _fail("M4_SCENARIO_WEIGHTS_INVALID")
    if any(
        tuple(row.component_id for row in item.component_vector.rows)
        != CONSEQUENCE_COMPONENTS
        for item in consequences
    ):
        _fail("M4_SEVEN_COMPONENT_VECTOR_REQUIRED")


def common_support_records(
    scenarios: tuple[M2ScenarioInput, ...],
    consequences: tuple[ScenarioConsequence, ...],
    registry: FrozenData2CUNormalizationRegistry,
) -> tuple[dict[str, object], ...]:
    cu_registry = getattr(registry, "registry", registry)
    records: list[dict[str, object]] = []
    for scenario, consequence in zip(scenarios, consequences, strict=True):
        delay_ok = _state_value(scenario.d_to_support) != "ABSTAIN" and _finite(
            scenario.d_to_minutes
        )
        native_ok = True
        cu_ok = True
        reasons: list[str] = []
        rows = consequence.component_vector.rows
        for row in rows:
            native = _state_value(row.support_state) != "ABSTAIN" and _finite(
                row.native_quantity
            )
            cu_status = _state_value(row.cu_status)
            cu = (
                cu_status == CUNormalizationStatus.CU_FROZEN.value
                and _finite(row.constructed_value_cu)
                and row.cu_quantity.compatible_with_registry(cu_registry)
            )
            native_ok &= native
            cu_ok &= cu
            if not native:
                reasons.append(f"{row.component_id}:NATIVE_UNSUPPORTED")
            if not cu:
                reasons.append(f"{row.component_id}:CU_UNSUPPORTED")
        if not delay_ok:
            reasons.append("D_TO_UNSUPPORTED")
        records.append(
            {
                "scenario_id": scenario.scenario_id,
                "scenario_weight": float(scenario.scenario_weight),
                "common_supported": delay_ok and native_ok and cu_ok,
                "delay": float(scenario.d_to_minutes) if delay_ok else None,
                "rows": rows,
                "reasons": tuple(reasons),
            }
        )
    return tuple(records)


def common_support_mass(records: tuple[dict[str, object], ...]) -> float:
    value = sum(
        float(item["scenario_weight"])
        for item in records
        if bool(item["common_supported"])
    )
    if value < -MASS_ABS_TOL or value > 1 + MASS_ABS_TOL:
        _fail("M4_COMMON_SUPPORT_MASS_INVALID")
    return min(1.0, max(0.0, value))


def support_flags(mass: float) -> tuple[bool, bool, bool]:
    if not isfinite(float(mass)) or mass < -MASS_ABS_TOL or mass > 1 + MASS_ABS_TOL:
        _fail("M4_COMMON_SUPPORT_MASS_INVALID")
    return (
        isclose(mass, 0.90, rel_tol=MASS_REL_TOL, abs_tol=MASS_ABS_TOL) or mass > 0.90,
        isclose(mass, 0.50, rel_tol=MASS_REL_TOL, abs_tol=MASS_ABS_TOL) or mass > 0.50,
        isclose(mass, 1.00, rel_tol=MASS_REL_TOL, abs_tol=MASS_ABS_TOL),
    )


def conditional_mean(
    records: tuple[dict[str, object], ...],
    value_getter,
    mass: float,
) -> float | None:
    selected = tuple(item for item in records if bool(item["common_supported"]))
    if not selected or mass <= 0:
        return None
    return sum(
        float(item["scenario_weight"]) * float(value_getter(item))
        for item in selected
    ) / mass


def summarize_common_support(
    scenarios: tuple[M2ScenarioInput, ...],
    consequences: tuple[ScenarioConsequence, ...],
    registry: FrozenData2CUNormalizationRegistry,
) -> dict[str, object]:
    """Return the model-layer conditional support summary without disk access."""
    validate_node_inputs(None, scenarios, consequences)
    records = common_support_records(scenarios, consequences, registry)
    mass = common_support_mass(records)
    primary, sensitivity, full = support_flags(mass)
    return {
        "records": records,
        "common_support_mass": mass,
        "support_primary": primary,
        "support_sensitivity": sensitivity,
        "support_full": full,
        "delay_mean_cs": conditional_mean(records, lambda item: item["delay"], mass),
    }


__all__ = [
    "common_support_mass",
    "common_support_records",
    "conditional_mean",
    "support_flags",
    "summarize_common_support",
    "validate_node_inputs",
]
