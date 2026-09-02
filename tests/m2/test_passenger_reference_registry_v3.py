import pytest

from model.M2.freeze import M2Data2FormalCuRegistry
from model.common.errors import ContractError


COMPONENTS = (
    "F_continuity", "F_execution", "F_propagation", "P_time",
    "P_itinerary", "P_service", "R_operating",
)


def _references():
    return {
        name: {
            "path": f"artifacts/diagnostics/passenger_reference_freeze/{name}.json",
            "artifact_hash": f"sha256:{index:064d}",
            "reference_id": f"sha256:{index + 10:064d}",
            "manifest_freeze_id": f"sha256:{index + 20:064d}",
        }
        for index, name in enumerate(
            ("turnaround", "taxi", "downstream_exposure", "expected_pax", "connection_share"), 1
        )
    }


def _scales():
    return {
        component: {
            "median": float(index), "positive_n": 10, "population_rows": 20,
            "unit": "unit", "definition": component,
        }
        for index, component in enumerate(COMPONENTS, 1)
    }


def test_v3_requires_seven_empirical_train_scales_and_passenger_references():
    registry = M2Data2FormalCuRegistry(
        registry_id="M2_DATA2_FORMAL_CU_V3",
        schema_version="M2_DATA2_FORMAL_CU_V3",
        formal_scope=COMPONENTS,
        train_scale_artifact=_scales(),
        reference_artifacts=_references(),
        component_weights={component: 1.0 for component in COMPONENTS},
    )
    assert registry.scale("P_time") == 4.0
    assert registry.scale("P_itinerary") == 5.0
    assert registry.scale("P_service") == 6.0
    with pytest.raises(ContractError, match="M2_V3_REQUIRES_SEVEN_TRAIN_SCALES"):
        M2Data2FormalCuRegistry(
            registry_id="M2_DATA2_FORMAL_CU_V3",
            schema_version="M2_DATA2_FORMAL_CU_V3",
            formal_scope=COMPONENTS,
            train_scale_artifact={key: value for key, value in _scales().items() if key != "P_service"},
            reference_artifacts=_references(),
            component_weights={component: 1.0 for component in COMPONENTS},
        )
