import json

import pytest

from model.M2.cu.registry import M2Data2FormalCuRegistry
from model.M2.scientific_registry import (
    load_active_m2_cu_registry,
    load_active_passenger_consequence_design,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.errors import ContractError


def _registry_payload():
    with open("registries/m2_data2_formal_cu_v4.json", encoding="utf-8") as stream:
        return json.load(stream)


def test_active_registry_and_design_are_v4():
    assert load_active_m2_cu_registry().registry_id == "M2_DATA2_FORMAL_CU_V4"
    assert load_active_passenger_consequence_design()["version"] == "4.0.0"


def test_v4_has_exactly_seven_positive_train_scales():
    registry = load_active_m2_cu_registry()
    assert registry.formal_scope == CONSEQUENCE_COMPONENTS
    assert set(registry.train_scale_artifact) == set(CONSEQUENCE_COMPONENTS)
    assert registry.assumption_scale_artifact is None
    for component in CONSEQUENCE_COMPONENTS:
        item = registry.train_scale_artifact[component]
        assert item["median"] > 0
        assert item["positive_n"] > 0
        assert item["population_rows"] >= item["positive_n"]


@pytest.mark.parametrize("missing", CONSEQUENCE_COMPONENTS)
def test_v4_rejects_each_missing_train_scale(missing):
    payload = _registry_payload()
    payload.pop("registry_hash")
    payload["train_scale_artifact"].pop(missing)
    with pytest.raises(ContractError, match="M2_V4_REQUIRES_SEVEN_TRAIN_SCALES"):
        M2Data2FormalCuRegistry.model_validate(payload)

