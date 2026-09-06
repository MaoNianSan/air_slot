from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd
import pytest

from exp.exp2.priority import add_domain_scores
from exp.shared.contracts import (
    PRIORITY_CONTRACT_VERSION,
    SHARED_PRIORITY_AUTHORITY,
    SupportedScore,
)
from exp.shared.recovery_priority import (
    compute_aggregate_priority,
    compute_domain_scores,
    compute_equal_component_priority,
    compute_no_f_execution_priority,
    materialize_priority_score_record,
    materialize_priority_scores,
    summarize_cu_components,
    summarize_delay_score,
    summarize_native_components,
    validate_authoritative_dependencies,
)
from model.M2.context import build_m2_seven_component_scope
from model.M2.contracts import (
    AvailableComponentSumDiagnostic,
    ComponentVector,
    ConsequenceRow,
    ExposureConfidence,
    FormalEstimandValue,
    M2ScenarioInput,
    NativeQuantity,
    ScenarioConsequence,
    SourceType,
)
from model.M2.cu.registry import FrozenData2CUNormalizationRegistry
from model.M2.scientific_registry import load_active_m2_cu_registry
from model.M2.valuation import M2CUNormalizationAdapter
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.cu_normalization import CUNormalizationStatus
from model.common.enums import EvidenceClass, SupportState
from model.common.estimand import FormalEstimandStatus

ROOT = Path(__file__).resolve().parents[2]
HEAD = "b6ed055d3ce92892b76eca99624d865f9d83444c"


@dataclass(frozen=True)
class ScenarioStub:
    episode_id: str
    decision_node_id: str
    scenario_id: int
    scenario_weight: float
    d_to_minutes: float | None
    d_to_support: str
    decision_time_utc: str = "2019-09-01T00:00:00Z"
    operational_stage: str = "PRE_IB"


def _scenarios(
    values=(10.0, 20.0, 40.0),
    weights=(0.2, 0.3, 0.5),
    *,
    node="node",
):
    return tuple(
        ScenarioStub(
            episode_id="episode",
            decision_node_id=node,
            scenario_id=index,
            scenario_weight=weight,
            d_to_minutes=value,
            d_to_support="SUPPORTED" if value is not None else "ABSTAIN",
        )
        for index, (value, weight) in enumerate(zip(values, weights))
    )


def _native(
    component: str,
    *,
    scenario_id: int,
    scenario_weight: float,
    native_value: float | None,
) -> NativeQuantity:
    supported = native_value is not None
    return NativeQuantity(
        component_id=component,
        scenario_id=scenario_id,
        scenario_weight=scenario_weight,
        native_quantity=native_value,
        native_unit="synthetic_native_unit",
        driver="synthetic_contract_fixture",
        evidence_class=(
            EvidenceClass.DERIVED if supported else EvidenceClass.UNSUPPORTED
        ),
        support_state=(SupportState.SUPPORTED if supported else SupportState.ABSTAIN),
        source_type=SourceType.SCENARIO_ASSUMPTION,
        reference_source="SYNTHETIC_CONTRACT_FIXTURE",
        reference_lineage=("SYNTHETIC_CONTRACT_FIXTURE",),
        confidence=(ExposureConfidence.HIGH if supported else ExposureConfidence.NONE),
        reason_code=None if supported else "SYNTHETIC_COMPONENT_UNSUPPORTED",
    )


def _consequence(
    cu_values: dict[str, float | None],
    *,
    scenario_id: int = 0,
    scenario_weight: float = 1.0,
    node: str = "node",
    registry_override=None,
) -> ScenarioConsequence:
    frozen = load_active_m2_cu_registry()
    adapter = registry_override or FrozenData2CUNormalizationRegistry(frozen)
    scope = build_m2_seven_component_scope()
    rows: list[ConsequenceRow] = []
    for component in CONSEQUENCE_COMPONENTS:
        cu_value = cu_values.get(component, 0.0)
        native_value = (
            None if cu_value is None else float(cu_value) * frozen.scale(component)
        )
        rows.append(
            adapter.value(
                _native(
                    component,
                    scenario_id=scenario_id,
                    scenario_weight=scenario_weight,
                    native_value=native_value,
                )
            )
        )
    valued = tuple(row for row in rows if row.constructed_value_cu is not None)
    formal_ok = len(valued) == len(CONSEQUENCE_COMPONENTS)
    formal = FormalEstimandValue(
        value_cu=(
            sum(float(row.constructed_value_cu) for row in valued)
            if formal_ok
            else None
        ),
        status=(
            FormalEstimandStatus.FORMAL_AVAILABLE
            if formal_ok
            else FormalEstimandStatus.FORMAL_AGGREGATE_UNRESOLVED
        ),
        estimand_id=scope.estimand_id,
        estimand_version=scope.estimand_version,
        scope_hash=scope.scope_hash,
        cu_normalization_registry_id=scope.cu_normalization_registry_id,
        aggregation_rule_id=scope.aggregation_rule_id,
        included_components=scope.included_components,
        reason_code=None if formal_ok else "INCLUDED_COMPONENT_ABSTAIN",
    )
    return ScenarioConsequence(
        episode_id="episode",
        decision_node_id=node,
        scenario_id=scenario_id,
        scenario_weight=scenario_weight,
        consequence_scope=scope,
        component_vector=ComponentVector(rows=tuple(rows)),
        available_component_sum_diagnostic=AvailableComponentSumDiagnostic(
            value_cu=(
                sum(float(row.constructed_value_cu) for row in valued)
                if valued
                else None
            ),
            included_components=tuple(row.component_id for row in valued),
            status="DIAGNOSTIC_AVAILABLE" if valued else "NO_VALUED_COMPONENTS",
        ),
        formal_estimand_value=formal,
        pre_lineage=("SYNTHETIC_PRE",),
        reference_lineage=("SYNTHETIC_CONTRACT_FIXTURE",),
        m1_scenario_seed_key=f"seed-{scenario_id}",
    )


def _supported_components(values: dict[str, float]) -> dict[str, SupportedScore]:
    return {
        component: SupportedScore(value=float(values[component]), support="SUPPORTED")
        for component in CONSEQUENCE_COMPONENTS
    }


def _arithmetic_values() -> dict[str, float]:
    return {
        "F_continuity": 3.0,
        "F_execution": 6.0,
        "F_propagation": 9.0,
        "P_time": 2.0,
        "P_itinerary": 4.0,
        "P_service": 6.0,
        "R_operating": 5.0,
    }


def test_weighted_d_to_mean_is_not_simple_mean():
    assert summarize_delay_score(_scenarios()).value == pytest.approx(28.0)


def test_d_to_identity_is_validated_upstream_and_shared_uses_d_to():
    valid = M2ScenarioInput(
        episode_id="episode",
        decision_node_id="node",
        scenario_id=0,
        scenario_weight=1.0,
        t_ib_a00_utc=None,
        r_ib_minutes=None,
        d_ob_minutes=10.0,
        d_tx_minutes=4.0,
        d_to_minutes=14.0,
        r_ib_support=SupportState.ABSTAIN,
        d_ob_support=SupportState.SUPPORTED,
        d_tx_support=SupportState.SUPPORTED,
        d_to_support=SupportState.SUPPORTED,
        pre_lineage=("pre",),
        reference_lineage=("reference",),
        m1_scenario_seed_key="seed",
    )
    assert summarize_delay_score((valid,)).value == 14.0
    with pytest.raises(ValueError, match="M2_D_TO_IDENTITY_VIOLATION"):
        M2ScenarioInput.model_validate(
            {**valid.model_dump(mode="python"), "d_to_minutes": 15.0}
        )


def test_weights_must_sum_to_one_without_normalization():
    with pytest.raises(ValueError, match="DELAY_PRIORITY_WEIGHTS_MUST_SUM_TO_ONE"):
        summarize_delay_score(_scenarios(values=(10.0, 20.0), weights=(0.3, 0.3)))


def test_valid_zero_is_supported_but_missing_is_unsupported():
    supported = summarize_native_components((_consequence({}, scenario_weight=1.0),))
    assert supported["P_service"].value == 0.0
    assert supported["P_service"].support == "SUPPORTED"
    missing = summarize_native_components(
        (_consequence({"P_service": None}, scenario_weight=1.0),)
    )
    assert missing["P_service"].value is None
    assert missing["P_service"].support == "UNSUPPORTED"


def test_exact_fpr_and_primary_arithmetic():
    domains = compute_domain_scores(_supported_components(_arithmetic_values()))
    assert domains["score_F"].value == pytest.approx(6.0)
    assert domains["score_P"].value == pytest.approx(4.0)
    assert domains["score_R"].value == pytest.approx(5.0)
    assert compute_aggregate_priority(domains).value == pytest.approx(5.0)


def test_no_f_execution_preserves_top_level_domain_balance():
    components = _supported_components(_arithmetic_values())
    assert compute_no_f_execution_priority(components).value == pytest.approx(5.0)


def test_equal_component_score():
    components = _supported_components(_arithmetic_values())
    assert compute_equal_component_priority(components).value == pytest.approx(5.0)


def test_passenger_fail_closed_without_collapsing_other_domains():
    values = _supported_components(_arithmetic_values())
    values["P_service"] = SupportedScore(
        value=None,
        support="UNSUPPORTED",
        reason_codes=("P_SERVICE_UNSUPPORTED",),
    )
    domains = compute_domain_scores(values)
    assert domains["score_F"].support == "SUPPORTED"
    assert domains["score_R"].support == "SUPPORTED"
    assert domains["score_P"].support == "UNSUPPORTED"
    assert compute_aggregate_priority(domains).support == "UNSUPPORTED"
    assert compute_no_f_execution_priority(values, domains).support == "UNSUPPORTED"


def test_cu_registry_lineage_rejects_mixed_registry():
    dependency = validate_authoritative_dependencies()
    result = summarize_cu_components((_consequence(_arithmetic_values()),))
    assert all(item.support == "SUPPORTED" for item in result.values())
    alternate = dependency["cu_registry"].model_copy(
        update={"registry_id": "M2_DATA2_FORMAL_CU_V3", "registry_hash": ""}
    )
    with pytest.raises(RuntimeError, match="BLOCK_MIXED_CU_REGISTRY"):
        summarize_cu_components(
            (
                _consequence(
                    _arithmetic_values(),
                    registry_override=M2CUNormalizationAdapter(alternate),
                ),
            )
        )


def test_shared_score_is_independent_of_cohort_membership():
    first_scenarios = _scenarios(values=(10.0,), weights=(1.0,), node="node-a")
    first_consequence = (_consequence(_arithmetic_values(), node="node-a"),)
    single = materialize_priority_scores(
        ((first_scenarios, first_consequence, ("fixture",)),),
        repository_head=HEAD,
    )[0]
    second_scenarios = _scenarios(values=(90.0,), weights=(1.0,), node="node-b")
    second_consequence = (_consequence(_arithmetic_values(), node="node-b"),)
    cohort = materialize_priority_scores(
        (
            (second_scenarios, second_consequence, ("fixture",)),
            (first_scenarios, first_consequence, ("fixture",)),
        ),
        repository_head=HEAD,
    )
    repeated = next(item for item in cohort if item.decision_node_id == "node-a")
    assert repeated.artifact_id == single.artifact_id
    assert repeated.score_C == single.score_C


def test_scenario_permutation_invariance():
    scenarios = _scenarios()
    outputs = tuple(
        _consequence(
            _arithmetic_values(),
            scenario_id=item.scenario_id,
            scenario_weight=item.scenario_weight,
        )
        for item in scenarios
    )
    first = materialize_priority_score_record(
        scenarios,
        outputs,
        repository_head=HEAD,
        m1_lineage=("fixture",),
    )
    second = materialize_priority_score_record(
        tuple(reversed(scenarios)),
        tuple(reversed(outputs)),
        repository_head=HEAD,
        m1_lineage=("fixture",),
    )
    assert first.artifact_id == second.artifact_id


def test_duplicate_scenario_id_rejected():
    rows = _scenarios(values=(10.0, 20.0), weights=(0.5, 0.5))
    with pytest.raises(ValueError, match="FAIL_DUPLICATE_SCENARIO_ID"):
        summarize_delay_score((rows[0], replace(rows[1], scenario_id=0)))


def test_mixed_decision_nodes_rejected():
    rows = _scenarios(values=(10.0, 20.0), weights=(0.5, 0.5))
    with pytest.raises(ValueError, match="FAIL_MIXED_DECISION_NODES"):
        summarize_delay_score((rows[0], replace(rows[1], decision_node_id="other")))


def test_m1_m2_scenario_alignment_is_exact():
    scenarios = _scenarios(values=(10.0,), weights=(1.0,))
    output = _consequence(_arithmetic_values(), scenario_id=1)
    with pytest.raises(RuntimeError, match="BLOCK_M1_M2_SCENARIO_ALIGNMENT_MISMATCH"):
        materialize_priority_score_record(
            scenarios,
            (output,),
            repository_head=HEAD,
            m1_lineage=("fixture",),
        )


def test_shared_module_has_no_m3_or_m4_dependency():
    source = (ROOT / "exp" / "shared" / "recovery_priority.py").read_text(
        encoding="utf-8"
    )
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not any(name.startswith(("model.M3", "model.M4")) for name in imported)


def test_shared_module_has_no_raw_data_dependency():
    source = (ROOT / "exp" / "shared" / "recovery_priority.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not any(name.startswith(("data1", "data2")) for name in imported)
    assert "open" not in calls


def test_phase0_dependency_validation_does_not_access_final_test():
    before = load_active_m2_cu_registry().final_test_access_count
    dependency = validate_authoritative_dependencies()
    after = load_active_m2_cu_registry().final_test_access_count
    assert before == after == 0
    assert dependency["registry_id"] == "M2_DATA2_FORMAL_CU_V4"


def test_output_contract_contains_scores_not_ranks():
    record = materialize_priority_score_record(
        _scenarios(values=(10.0,), weights=(1.0,)),
        (_consequence(_arithmetic_values()),),
        repository_head=HEAD,
        m1_lineage=("fixture",),
    )
    fields = set(record.model_dump(mode="json"))
    assert {"delay_score", "score_F", "score_P", "score_R", "score_C"} <= fields
    assert not {"rank", "percentile", "top10_flag", "priority_class"} & fields
    assert record.priority_contract_version == PRIORITY_CONTRACT_VERSION
    assert record.scientific_contract_authority == "HUMAN_APPROVED"
    assert record.scientific_contract_status == "FROZEN_FOR_EXP2_EXP3_EXP4"
    assert record.artifact_stage == "DEVELOPMENT_ONLY_PHASE0_VALIDATION"
    assert record.final_test_authorized is False
    assert record.paper_result is False


def test_exp2_domain_adapter_delegates_shared_arithmetic():
    frame = pd.DataFrame(
        [{f"Z_{component}": value for component, value in _arithmetic_values().items()}]
    )
    result = add_domain_scores(frame).iloc[0]
    assert result["score_F"] == pytest.approx(6.0)
    assert result["score_P"] == pytest.approx(4.0)
    assert result["score_R"] == pytest.approx(5.0)
    assert result["score_C"] == pytest.approx(5.0)
    assert bool(result["conditional_aggregate_complete"])


def test_scientific_contract_is_human_approved_and_frozen():
    assert PRIORITY_CONTRACT_VERSION == "AIR_SLOT_SHARED_PRIORITY_CONTRACT_V1_20260906"
    assert SHARED_PRIORITY_AUTHORITY.authority == "HUMAN_APPROVED"
    assert SHARED_PRIORITY_AUTHORITY.status == "FROZEN_FOR_EXP2_EXP3_EXP4"
    assert SHARED_PRIORITY_AUTHORITY.final_test_authorized is False
