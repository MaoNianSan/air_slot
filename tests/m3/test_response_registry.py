"""M3_RESPONSE_SCENARIO_V1 registry + engine focused tests.

Covers: 23-action set, A00 NOT_REQUIRED, non-A00 FROZEN/PURE_SCENARIO,
tier->parameter materialization (LOW/BASE/HIGH), hash fail-closed,
structural-vs-response action-set match, manifest write-once, and the
deterministic response engine (spec sections 5-15).
"""

import json
from pathlib import Path

import pytest

from model.M3.registry_layer.actions import ActionRegistry
from model.M3.response_layer.core import (
    response_draw,
    scenario_update,
)
from model.M3.response_registry import (
    PRINCIPAL_IDS,
    REGISTRY_ID,
    ResponseScenarioRegistry,
    load_response_registry,
)
from model.common.errors import ContractError, RegistryError


ROOT = Path(__file__).resolve().parents[2]
RESPONSE_PATH = ROOT / "registries" / "m3_response_scenarios.yaml"
STRUCTURAL_PATH = ROOT / "registries" / "action_templates.yaml"

EXPECTED_TIERS = {
    "A00": "", "A11": "T1", "A13": "T2", "A21": "T1", "A22": "T3", "A23": "T3",
    "A31": "T1", "A32": "T2", "A33": "T1", "A41": "T2", "A42": "T2", "A43": "T3",
    "A51": "T2", "A52": "T3", "A53": "T2", "A54": "T4", "A55": "T4",
    "A61": "T2", "A62": "T2", "A63": "T4", "A64": "T3", "A71": "T5", "A72": "T6",
}

TIER_PARAMS = {
    "T1": (0.80, 0.70), "T2": (0.65, 0.60), "T3": (0.50, 0.50),
    "T4": (0.35, 0.45), "T5": (0.95, 0.90), "T6": (0.90, 0.85),
}


@pytest.fixture(scope="module")
def registry() -> ResponseScenarioRegistry:
    return load_response_registry(RESPONSE_PATH, structural_path=STRUCTURAL_PATH)


def test_identity_and_action_set(registry):
    assert registry.registry_id == REGISTRY_ID
    assert registry.schema_version == REGISTRY_ID
    assert tuple(registry.actions) == PRINCIPAL_IDS
    assert registry.registry_hash == registry.digest()
    assert registry.registry_hash.startswith("sha256:")


def test_a00_and_frozen_contract(registry):
    a00 = registry.actions["A00"]
    assert a00.response_parameter_status == "NOT_REQUIRED"
    assert a00.response_model == "DETERMINISTIC"
    assert a00.value == 0.0
    for template_id, action in registry.actions.items():
        if template_id == "A00":
            continue
        assert action.response_parameter_status == "FROZEN"
        assert action.response_provenance == "ASSUMPTION_GROUNDED"
        assert action.response_model == "BERNOULLI_BETA"
        assert action.assumption_grounded is not None


def test_tiers_match_spec_table(registry):
    for template_id, expected_tier in EXPECTED_TIERS.items():
        assert registry.actions[template_id].tier == expected_tier, template_id
    for tier_name, (prob, mean) in TIER_PARAMS.items():
        tier = registry.tiers[tier_name]
        assert tier["success_probability"] == prob
        assert tier["beta_mean"] == mean


def test_structural_action_set_matches_response_registry(registry):
    structural = ActionRegistry.load(STRUCTURAL_PATH)
    structural_ids = tuple(item.template_id for item in structural.templates)
    assert structural_ids == PRINCIPAL_IDS
    assert len(structural_ids) == 23


def test_sensitivity_materialization_bounds(registry):
    for template_id in ("A11", "A54", "A72"):
        base = registry.parameters(template_id, sensitivity="BASE")
        low = registry.parameters(template_id, sensitivity="LOW")
        high = registry.parameters(template_id, sensitivity="HIGH")
        for level, params in (("BASE", base), ("LOW", low), ("HIGH", high)):
            assert params["response_parameter_status"] == "FROZEN"
            assert params["response_provenance"] == "ASSUMPTION_GROUNDED"
            assert params["assumption_grounded"] is not None
            assert 0.05 <= params["success_probability"] <= 0.95
            assert 0.20 <= params["mean_intensity"] <= 0.95
            assert params["concentration"] == 12.0
        assert low["success_probability"] <= base["success_probability"] <= high["success_probability"]
        assert low["mean_intensity"] <= base["mean_intensity"] <= high["mean_intensity"]
        assert low["sensitivity_level"] == "LOW"
        assert high["sensitivity_level"] == "HIGH"


def test_a00_parameters_deterministic(registry):
    params = registry.parameters("A00", sensitivity="BASE")
    assert params["response_model"] == "DETERMINISTIC"
    assert params["response_parameter_status"] == "NOT_REQUIRED"
    assert params["value"] == 0.0


def test_hash_fail_closed_on_payload_change(registry):
    original = registry.digest()
    mutated = registry.model_copy(deep=True)
    mutated.actions["A11"] = mutated.actions["A11"].model_copy(
        update={"tier": "T3"}
    )
    assert mutated.digest() != original
    with pytest.raises(RegistryError):
        registry.parameters("A99", sensitivity="BASE")


def test_registry_identity_fail_closed():
    import yaml

    raw = yaml.safe_load(RESPONSE_PATH.read_text(encoding="utf-8"))
    sensitivity = dict(raw["sensitivity"])
    payload = dict(raw)
    payload["principal_sensitivity_axis"] = sensitivity.pop(
        "principal_axis", "RESPONSE_EFFICACY"
    )
    payload["sensitivity"] = sensitivity
    payload["actions"] = {
        action_id: {"template_id": action_id, **(item or {})}
        for action_id, item in raw["actions"].items()
    }
    payload["registry_id"] = "WRONG_ID"
    with pytest.raises(RegistryError, match="M3_RESPONSE_REGISTRY_IDENTITY_MISMATCH"):
        ResponseScenarioRegistry.model_validate(payload)


def test_manifest_write_once_and_hashes(registry, tmp_path):
    output = tmp_path / "M3_RESPONSE_SCENARIO_V1_MANIFEST.json"
    registry.write_manifest(output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["registry_hash"] == registry.digest()
    assert payload["formal_support_upgrade"] is False
    assert payload["final_test_access_count"] == 0
    assert payload["paper_full_run"] is False
    assert len(payload["action_ids"]) == 23
    with pytest.raises(RegistryError, match="M3_RESPONSE_MANIFEST_EXISTS"):
        registry.write_manifest(output)


def test_response_draw_determinism_and_registry_keying(registry):
    params = registry.parameters("A11", sensitivity="BASE")
    kwargs = dict(
        seed=7,
        episode_id="E1",
        decision_node_id="N1",
        scenario_id="S1",
        action_template_id="A11",
        parameters=params,
        response_registry_hash=registry.digest(),
        sensitivity_level="BASE",
    )
    first = response_draw(**kwargs)
    second = response_draw(**kwargs)
    assert first == second
    assert 0.0 <= first <= 1.0
    changed = response_draw(
        **dict(kwargs, response_registry_hash="sha256:" + "0" * 64)
    )
    assert changed != first


def test_response_draw_deterministic_a00(registry):
    params = registry.parameters("A00", sensitivity="BASE")
    assert response_draw(
        seed=1, episode_id="E", decision_node_id="N", scenario_id="S",
        action_template_id="A00", parameters=params,
        response_registry_hash=registry.digest(),
    ) == 0.0


def test_scenario_update_formula():
    post = scenario_update(
        pre_cu=10.0, mitigation_coefficient=0.8, rho=0.5,
        induced_score=2.0, induced_score_to_cu=0.10,
    )
    assert post == pytest.approx(10.0 * (1 - 0.8 * 0.5) + 0.2)
    with pytest.raises(ContractError, match="M3_SCENARIO_UPDATE_MITIGATION_OUT_OF_RANGE"):
        scenario_update(
            pre_cu=1.0, mitigation_coefficient=2.0, rho=1.0,
            induced_score=0.0, induced_score_to_cu=0.10,
        )
