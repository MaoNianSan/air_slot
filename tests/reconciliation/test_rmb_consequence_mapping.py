from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.rmb_mapping import (
    RMBMappingFunction,
    RMBMappingParameter,
    RMBMappingRegistry,
    RMBMappingRule,
    RMBMappingStatus,
    RMBSourceType,
)


def _registry():
    rules = {}
    for component in CONSEQUENCE_COMPONENTS:
        rules[component] = RMBMappingRule.create(
            component_id=component,
            mapping_function=RMBMappingFunction.LINEAR_SCALE,
            parameter_version="TEST_RMB_V1",
            source_type=RMBSourceType.SCENARIO_ASSUMPTION,
            reference=("TEST_CONSTRUCTED_MAPPING",),
            freeze_id="TEST_RMB_FREEZE",
            parameters=(RMBMappingParameter(parameter_name="rmb_per_consequence_unit", value=2.0, unit="RMB/C", provenance=("TEST",)),),
            provenance=("TEST_ONLY",),
            rule_id=f"RMB_{component}",
        )
    return RMBMappingRegistry(
        registry_id="TEST_RMB_V1",
        registry_version="TEST_RMB_V1",
        status=RMBMappingStatus.TEST_ONLY,
        freeze_id="TEST_RMB_FREEZE",
        reference_period="TEST",
        component_mappings=rules,
        provenance=("TEST_ONLY",),
    )


def test_rmb_mapping_uses_consequence_values_not_cu():
    registry = _registry()
    consequence = {component: 1.0 for component in CONSEQUENCE_COMPONENTS}
    mapped = registry.to_component_rmb(consequence)
    assert mapped == {component: 2.0 for component in CONSEQUENCE_COMPONENTS}
    assert registry.to_rmb(consequence) == 14.0
    assert registry.registry_payload()["monetary_ground_truth_claim"] is False


def test_unfrozen_rmb_mapping_abstains_without_zero_fill():
    registry = RMBMappingRegistry.not_frozen()
    assert registry.to_component_rmb({"F_continuity": 1.0}) is None
    assert registry.to_rmb({"F_continuity": 1.0}) is None
