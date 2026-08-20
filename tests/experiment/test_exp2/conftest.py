import pytest


@pytest.fixture
def m1_scenarios():
    return (
        {"scenario_id": 0, "scenario_weight": 1 / 3, "D_OB": 3.0, "D_TX": 2.0, "D_TO": 5.0, "lineage": ("m1:0",)},
        {"scenario_id": 1, "scenario_weight": 1 / 3, "D_OB": 6.0, "D_TX": 4.0, "D_TO": 10.0, "lineage": ("m1:1",)},
        {"scenario_id": 2, "scenario_weight": 1 / 3, "D_OB": 9.0, "D_TX": 8.0, "D_TO": 17.0, "lineage": ("m1:2",)},
    )


@pytest.fixture
def m2_consequences():
    component_ids = (
        "F_continuity", "F_execution", "F_propagation", "P_time",
        "P_itinerary", "P_service", "R_operating",
    )
    channels = ("Flight", "Flight", "Flight", "Passenger", "Passenger", "Passenger", "Resource")
    scenarios = []
    for scenario_id in range(3):
        components = tuple(
            {
                "component_id": component_id,
                "aspect": channel,
                "constructed_value_cu": float(index + scenario_id),
                "support_state": "SUPPORTED",
                "reference_lineage": (f"m2:{scenario_id}:{component_id}",),
            }
            for index, (component_id, channel) in enumerate(zip(component_ids, channels, strict=True), start=1)
        )
        scenarios.append({
            "scenario_id": scenario_id,
            "scenario_weight": 1 / 3,
            "components": components,
        })
    return tuple(scenarios)
