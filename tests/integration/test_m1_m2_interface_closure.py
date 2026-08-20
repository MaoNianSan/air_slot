from model.M2.contracts import M2ScenarioInput
from model.M2.mapper import M2Mapper
from model.M2.summary import summarize_formal_consequence
from model.M2.valuation import M2CUNormalizationAdapter
from model.common.cu_normalization import CUNormalizationRegistry
from model.common.estimand import ConsequenceScope, ScopeStatus
from tests.m2.test_v2_design_alignment import _m1_scenario, _runtime


SUPPORTED_COMPONENTS = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "R_operating",
)


def _typed(scenario):
    return M2ScenarioInput.from_m1(
        scenario,
        pre_lineage=("integration-pre",),
        reference_lineage=("integration-reference",),
    )


def _mapper():
    _, context = _runtime()
    scope = ConsequenceScope.create(
        estimand_id="M2_INTERFACE_INTEGRATION_TEST",
        estimand_version="TEST-1",
        included_components=SUPPORTED_COMPONENTS,
        aggregation_rule_id="TEST_SUM_SUPPORTED_FIVE",
        cu_normalization_registry_id="M2_INTERFACE_TEST_CU",
        material_coverage_contract_id="TEST_ONLY",
        scope_status=ScopeStatus.FORMAL_READY,
    )
    registry = CUNormalizationRegistry.from_scales(
        registry_id=scope.cu_normalization_registry_id,
        version="TEST-1",
        freeze_id="integration-scale-freeze",
        reference_period="train-only-test",
        scales={component: 10.0 for component in SUPPORTED_COMPONENTS},
    )
    return M2Mapper(M2CUNormalizationAdapter(registry), scope), context


def test_m1_all_scenarios_flow_to_m2_with_weights_and_risk_interface():
    mapper, context = _mapper()
    scenarios = (
        _typed(_m1_scenario(0, 0.25, d_ob=10.0, d_tx=5.0)),
        _typed(_m1_scenario(1, 0.75, d_ob=40.0, d_tx=20.0)),
    )
    distribution = mapper.map_m1_distribution(scenarios, context)
    assert len(distribution.consequences) == len(scenarios)
    assert distribution.scenario_ids == (0, 1)
    assert distribution.scenario_weights == (0.25, 0.75)
    assert all(
        output.reference_lineage
        == ("integration-reference", "taxi-ref")
        for output in distribution.consequences
    )
    summary = summarize_formal_consequence(
        distribution, cvar_alpha=0.5, tail_threshold_cu=1.0
    )
    assert summary.status == "AVAILABLE"
    assert summary.scenario_weights == (0.25, 0.75)
    assert summary.mean_cu is not None
    assert summary.variance_cu2 is not None
    assert summary.cvar_cu is not None
