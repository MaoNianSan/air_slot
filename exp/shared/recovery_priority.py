"""Shared node-level recovery-priority candidate computations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from math import fsum, isclose, isfinite
from typing import Any

from model.M2.contracts import (
    ScenarioConsequence,
    ScenarioConsequenceDistribution,
)
from model.M2.context import build_m2_seven_component_scope
from model.M2.cu.registry import (
    FrozenData2CUNormalizationRegistry,
    M2Data2FormalCuRegistry,
)
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus

from .contracts import (
    ComponentSupportRecord,
    NamedSupportRecord,
    PRIORITY_INTERFACE_HASH,
    PRIORITY_INTERFACE_VERSION,
    RecoveryPriorityScoreRecord,
    SupportedScore,
)

WEIGHT_TOLERANCE = 1e-6
ALIGNMENT_TOLERANCE = 1e-12
FLIGHT_COMPONENTS = ("F_continuity", "F_execution", "F_propagation")
PASSENGER_COMPONENTS = ("P_time", "P_itinerary", "P_service")


def _state_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _finite_nonnegative(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(float(value))
        and float(value) >= 0
    )


def _items(
    consequences: Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
) -> tuple[ScenarioConsequence, ...]:
    if isinstance(consequences, ScenarioConsequenceDistribution):
        return consequences.consequences
    return tuple(consequences)


def _validate_node_rows(rows: Sequence[Any], *, prefix: str) -> tuple[Any, ...]:
    items = tuple(rows)
    if not items:
        raise ValueError(f"{prefix}_REQUIRES_SCENARIOS")
    identities = {(item.episode_id, item.decision_node_id) for item in items}
    if len(identities) != 1:
        raise ValueError("FAIL_MIXED_DECISION_NODES")
    scenario_ids = tuple(item.scenario_id for item in items)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("FAIL_DUPLICATE_SCENARIO_ID")
    weights = tuple(float(item.scenario_weight) for item in items)
    if any(not isfinite(weight) or weight <= 0 for weight in weights):
        raise ValueError(f"{prefix}_SCENARIO_WEIGHT_INVALID")
    if not isclose(fsum(weights), 1.0, abs_tol=WEIGHT_TOLERANCE):
        raise ValueError(f"{prefix}_WEIGHTS_MUST_SUM_TO_ONE")
    return tuple(sorted(items, key=lambda item: item.scenario_id))


def validate_authoritative_dependencies(
    registry: M2Data2FormalCuRegistry | None = None,
) -> dict[str, Any]:
    active = registry or load_active_m2_cu_registry()
    scope = build_m2_seven_component_scope()
    if active.registry_id != "M2_DATA2_FORMAL_CU_V4":
        raise RuntimeError("BLOCK_SHARED_PRIORITY_DEPENDENCY:M2_ACTIVE_REGISTRY_NOT_V4")
    if active.registry_hash != active.digest():
        raise RuntimeError("BLOCK_SHARED_PRIORITY_DEPENDENCY:M2_REGISTRY_HASH_MISMATCH")
    if tuple(active.formal_scope) != tuple(CONSEQUENCE_COMPONENTS):
        raise RuntimeError("BLOCK_SHARED_PRIORITY_DEPENDENCY:M2_V4_SCOPE_MISMATCH")
    if active.support_rule != "UNAVAILABLE_ABSTAIN_NO_DROP_RENORM_ZERO_PROXY":
        raise RuntimeError("BLOCK_SHARED_PRIORITY_DEPENDENCY:M2_SUPPORT_RULE_MISMATCH")
    if active.scientific_status != "FROZEN" or active.implementation_status != "MATCH":
        raise RuntimeError("BLOCK_SHARED_PRIORITY_DEPENDENCY:M2_AUTHORITY_NOT_FROZEN")
    if active.final_test_access_count != 0:
        raise RuntimeError("FINAL_TEST_ACCESS_VIOLATION")
    if scope.cu_normalization_registry_id != active.registry_id:
        raise RuntimeError("BLOCK_CONTRACT_RECONCILIATION_REQUIRED")
    if tuple(scope.included_components) != tuple(CONSEQUENCE_COMPONENTS):
        raise RuntimeError("BLOCK_CONTRACT_RECONCILIATION_REQUIRED")
    cu_registry = FrozenData2CUNormalizationRegistry(active).registry
    return {
        "registry": active,
        "scope": scope,
        "cu_registry": cu_registry,
        "registry_id": active.registry_id,
        "registry_hash": active.registry_hash,
        "cu_normalization_registry_hash": cu_registry.digest(),
        "scope_hash": scope.scope_hash,
    }


def summarize_delay_score(scenarios: Sequence[Any]) -> SupportedScore:
    items = _validate_node_rows(scenarios, prefix="DELAY_PRIORITY")
    reasons: set[str] = set()
    weighted: list[float] = []
    for item in items:
        value = getattr(item, "d_to_minutes", None)
        support = _state_value(getattr(item, "d_to_support", "ABSTAIN"))
        if support == "ABSTAIN" or value is None:
            reasons.add("DELAY_PRIORITY_UNSUPPORTED")
            continue
        if not _finite_nonnegative(value):
            raise ValueError("DELAY_PRIORITY_VALUE_INVALID")
        weighted.append(float(item.scenario_weight) * float(value))
    if reasons:
        return SupportedScore(
            value=None,
            support="UNSUPPORTED",
            reason_codes=tuple(sorted(reasons)),
        )
    return SupportedScore(value=fsum(weighted), support="SUPPORTED")


def _component_summary(
    consequences: Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
    *,
    value_field: str,
    registry: M2Data2FormalCuRegistry | None = None,
) -> dict[str, SupportedScore]:
    items = _validate_node_rows(_items(consequences), prefix="M2_PRIORITY")
    dependency = validate_authoritative_dependencies(registry)
    active = dependency["registry"]
    active_scope = dependency["scope"]
    cu_registry = dependency["cu_registry"]
    summaries: dict[str, SupportedScore] = {}
    for component in CONSEQUENCE_COMPONENTS:
        reasons: set[str] = set()
        weighted: list[float] = []
        for consequence in items:
            if (
                consequence.consequence_scope.scope_hash != active_scope.scope_hash
                or consequence.consequence_scope.cu_normalization_registry_id
                != active.registry_id
            ):
                raise RuntimeError("BLOCK_CONTRACT_RECONCILIATION_REQUIRED")
            rows = tuple(
                row
                for row in consequence.component_vector.rows
                if row.component_id == component
            )
            if len(rows) != 1:
                raise ValueError(f"PRIORITY_COMPONENT_CARDINALITY_INVALID:{component}")
            row = rows[0]
            value = getattr(row, value_field)
            if value_field == "constructed_value_cu":
                cu = row.cu_quantity
                if cu.registry_id not in (None, active.registry_id):
                    raise RuntimeError("BLOCK_MIXED_CU_REGISTRY")
                if row.cu_status is CUNormalizationStatus.CU_FROZEN and not cu.compatible_with_registry(cu_registry):
                    raise RuntimeError("BLOCK_MIXED_CU_REGISTRY")
                supported = (
                    row.cu_status is CUNormalizationStatus.CU_FROZEN
                    and value is not None
                )
                reason = row.reason_code or row.cu_status.value
            else:
                supported = _state_value(row.support_state) != "ABSTAIN" and value is not None
                reason = row.reason_code or "NATIVE_COMPONENT_UNSUPPORTED"
            if not supported:
                reasons.add(f"{component}:{reason}")
                continue
            if not _finite_nonnegative(value):
                raise ValueError(f"PRIORITY_COMPONENT_VALUE_INVALID:{component}")
            weighted.append(float(consequence.scenario_weight) * float(value))
        if reasons:
            summaries[component] = SupportedScore(
                value=None,
                support="UNSUPPORTED",
                reason_codes=tuple(sorted(reasons)),
            )
        else:
            summaries[component] = SupportedScore(
                value=fsum(weighted), support="SUPPORTED"
            )
    return summaries


def summarize_native_components(
    consequences: Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
) -> dict[str, SupportedScore]:
    return _component_summary(consequences, value_field="native_quantity")


def summarize_cu_components(
    consequences: Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
    *,
    registry: M2Data2FormalCuRegistry | None = None,
) -> dict[str, SupportedScore]:
    return _component_summary(
        consequences, value_field="constructed_value_cu", registry=registry
    )


def _mean_required(
    values: Mapping[str, SupportedScore], required: Sequence[str], reason: str
) -> SupportedScore:
    missing = tuple(name for name in required if name not in values)
    if missing:
        raise ValueError(f"PRIORITY_REQUIRED_COMPONENT_MISSING:{','.join(missing)}")
    blocked = tuple(name for name in required if values[name].support != "SUPPORTED")
    if blocked:
        return SupportedScore(
            value=None,
            support="UNSUPPORTED",
            reason_codes=(f"{reason}:{','.join(blocked)}",),
        )
    return SupportedScore(
        value=fsum(float(values[name].value) for name in required) / len(required),
        support="SUPPORTED",
    )


def compute_domain_scores(
    cu_components: Mapping[str, SupportedScore],
) -> dict[str, SupportedScore]:
    return {
        "score_F": _mean_required(
            cu_components, FLIGHT_COMPONENTS, "FLIGHT_DOMAIN_UNSUPPORTED"
        ),
        "score_P": _mean_required(
            cu_components, PASSENGER_COMPONENTS, "PASSENGER_DOMAIN_UNSUPPORTED"
        ),
        "score_R": _mean_required(
            cu_components, ("R_operating",), "OPERATING_DOMAIN_UNSUPPORTED"
        ),
    }


def compute_aggregate_priority(
    domains: Mapping[str, SupportedScore],
) -> SupportedScore:
    return _mean_required(
        domains, ("score_F", "score_P", "score_R"), "AGGREGATE_UNSUPPORTED"
    )


def compute_no_f_execution_priority(
    cu_components: Mapping[str, SupportedScore],
    domains: Mapping[str, SupportedScore] | None = None,
) -> SupportedScore:
    domain_values = domains or compute_domain_scores(cu_components)
    flight_without_execution = _mean_required(
        cu_components,
        ("F_continuity", "F_propagation"),
        "FLIGHT_NO_EXECUTION_UNSUPPORTED",
    )
    return _mean_required(
        {
            "score_F_no_F_execution": flight_without_execution,
            "score_P": domain_values["score_P"],
            "score_R": domain_values["score_R"],
        },
        ("score_F_no_F_execution", "score_P", "score_R"),
        "AGGREGATE_NO_F_EXECUTION_UNSUPPORTED",
    )


def compute_equal_component_priority(
    cu_components: Mapping[str, SupportedScore],
) -> SupportedScore:
    return _mean_required(
        cu_components,
        CONSEQUENCE_COMPONENTS,
        "EQUAL_COMPONENT_AGGREGATE_UNSUPPORTED",
    )


def _validate_m1_m2_alignment(
    scenarios: Sequence[Any], consequences: Sequence[ScenarioConsequence]
) -> None:
    m1 = _validate_node_rows(scenarios, prefix="M1_PRIORITY")
    m2 = _validate_node_rows(consequences, prefix="M2_PRIORITY")
    if (m1[0].episode_id, m1[0].decision_node_id) != (
        m2[0].episode_id,
        m2[0].decision_node_id,
    ):
        raise RuntimeError("BLOCK_M1_M2_SCENARIO_ALIGNMENT_MISMATCH")
    m1_weights = {item.scenario_id: float(item.scenario_weight) for item in m1}
    m2_weights = {item.scenario_id: float(item.scenario_weight) for item in m2}
    if set(m1_weights) != set(m2_weights) or any(
        not isclose(m1_weights[key], m2_weights[key], abs_tol=ALIGNMENT_TOLERANCE)
        for key in m1_weights.keys() & m2_weights.keys()
    ):
        raise RuntimeError("BLOCK_M1_M2_SCENARIO_ALIGNMENT_MISMATCH")


def _support_records(
    values: Mapping[str, SupportedScore], *, component: bool
) -> tuple[ComponentSupportRecord | NamedSupportRecord, ...]:
    factory = ComponentSupportRecord if component else NamedSupportRecord
    key_name = "component_id" if component else "object_id"
    return tuple(
        factory(
            **{
                key_name: name,
                "support": result.support,
                "reason_codes": result.reason_codes,
            }
        )
        for name, result in values.items()
    )


def build_priority_score_candidate(
    scenarios: Sequence[Any],
    consequences: Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
    *,
    repository_head: str,
    m1_lineage: Sequence[str],
    registry: M2Data2FormalCuRegistry | None = None,
) -> RecoveryPriorityScoreRecord:
    outputs = _items(consequences)
    _validate_m1_m2_alignment(scenarios, outputs)
    dependency = validate_authoritative_dependencies(registry)
    delay = summarize_delay_score(scenarios)
    native = summarize_native_components(outputs)
    cu = summarize_cu_components(outputs, registry=dependency["registry"])
    domains = compute_domain_scores(cu)
    aggregate = compute_aggregate_priority(domains)
    no_execution = compute_no_f_execution_priority(cu, domains)
    equal_component = compute_equal_component_priority(cu)
    first = sorted(scenarios, key=lambda item: item.scenario_id)[0]
    aggregate_values = {
        "score_C": aggregate,
        "score_C_no_F_execution": no_execution,
        "score_equal_component": equal_component,
    }
    all_results = (delay, *native.values(), *cu.values(), *domains.values(), *aggregate_values.values())
    reasons = tuple(
        sorted({reason for result in all_results for reason in result.reason_codes})
    )
    values = {
        f"native_{name}": native[name].value for name in CONSEQUENCE_COMPONENTS
    }
    values.update({f"cu_{name}": cu[name].value for name in CONSEQUENCE_COMPONENTS})
    return RecoveryPriorityScoreRecord(
        episode_id=first.episode_id,
        decision_node_id=first.decision_node_id,
        decision_time=getattr(first, "decision_time_utc", None),
        operational_stage=getattr(first, "operational_stage", None),
        delay_score=delay.value,
        **values,
        score_F=domains["score_F"].value,
        score_P=domains["score_P"].value,
        score_R=domains["score_R"].value,
        score_C=aggregate.value,
        score_C_no_F_execution=no_execution.value,
        score_equal_component=equal_component.value,
        delay_support=delay.support,
        native_component_support=_support_records(native, component=True),
        cu_component_support=_support_records(cu, component=True),
        domain_support=_support_records(domains, component=False),
        aggregate_support=_support_records(aggregate_values, component=False),
        reason_codes=reasons,
        repository_head=repository_head,
        m1_lineage=tuple(m1_lineage),
        m2_scope_hash=dependency["scope_hash"],
        m2_registry_id=dependency["registry_id"],
        m2_registry_hash=dependency["registry_hash"],
        m2_cu_normalization_registry_hash=dependency[
            "cu_normalization_registry_hash"
        ],
        priority_interface_version=PRIORITY_INTERFACE_VERSION,
        priority_interface_hash=PRIORITY_INTERFACE_HASH,
    )


def build_priority_score_candidates(
    node_inputs: Iterable[
        tuple[
            Sequence[Any],
            Sequence[ScenarioConsequence] | ScenarioConsequenceDistribution,
            Sequence[str],
        ]
    ],
    *,
    repository_head: str,
    registry: M2Data2FormalCuRegistry | None = None,
) -> tuple[RecoveryPriorityScoreRecord, ...]:
    records = tuple(
        build_priority_score_candidate(
            scenarios,
            consequences,
            repository_head=repository_head,
            m1_lineage=m1_lineage,
            registry=registry,
        )
        for scenarios, consequences, m1_lineage in node_inputs
    )
    return tuple(sorted(records, key=lambda row: (row.episode_id, row.decision_node_id)))


# Draft-name aliases retained for local callers; the returned objects remain
# candidate score records and are not formal node-table materialization.
materialize_priority_score_record = build_priority_score_candidate
materialize_priority_scores = build_priority_score_candidates


__all__ = [
    "compute_aggregate_priority",
    "compute_domain_scores",
    "compute_equal_component_priority",
    "compute_no_f_execution_priority",
    "build_priority_score_candidate",
    "build_priority_score_candidates",
    "materialize_priority_score_record",
    "materialize_priority_scores",
    "summarize_cu_components",
    "summarize_delay_score",
    "summarize_native_components",
    "validate_authoritative_dependencies",
]
