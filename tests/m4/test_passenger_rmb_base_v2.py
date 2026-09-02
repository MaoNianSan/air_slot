from model.M4.scientific_registry import PRINCIPAL_RMB_COMPONENTS, load_active_rmb_mapping


def test_rmb_base_v2_maps_all_seven_components_with_identity_beta():
    registry = load_active_rmb_mapping()
    values = {component: float(index) for index, component in enumerate(PRINCIPAL_RMB_COMPONENTS, 1)}
    assert registry.registry_id == "M4_RMB_BASE_MAPPING_V2"
    assert tuple(registry.component_mappings) == PRINCIPAL_RMB_COMPONENTS
    assert registry.to_money(values) == 28.0
    assert registry.to_component_money(values)["P_itinerary"] == 5.0
    assert registry.to_component_money(values)["P_service"] == 6.0
