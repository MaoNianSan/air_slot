"""Active M4 BASE RMB measurement and risk-policy registry tests."""

from __future__ import annotations

import json
from pathlib import Path

from model.M4.residual_risk import load_active_risk_policy
from model.M4.scientific_registry import (
    PRINCIPAL_RMB_COMPONENTS,
    load_active_risk_policy_payload,
    load_active_rmb_mapping,
)


ROOT = Path(__file__).resolve().parents[2]


def test_active_rmb_registry_is_base_only_constructed_measurement():
    registry = load_active_rmb_mapping()
    assert registry.monetary_system_id == "RMB"
    assert registry.authoritative is True
    assert tuple(registry.component_mappings) == PRINCIPAL_RMB_COMPONENTS
    assert {
        rule.parameters[0].value for rule in registry.component_mappings.values()
    } == {1.0}
    mapped = registry.to_component_money(
        {component: 2.0 for component in PRINCIPAL_RMB_COMPONENTS}
    )
    assert mapped == {component: 2.0 for component in PRINCIPAL_RMB_COMPONENTS}


def test_active_rmb_registry_maps_passenger_components_without_zero_fill():
    registry = load_active_rmb_mapping()
    assert registry.to_component_money({"P_itinerary": 1.0}) == {"P_itinerary": 1.0}
    assert registry.to_component_money({"P_service": 1.0}) == {"P_service": 1.0}


def test_active_rmb_claim_boundary_rejects_currency_or_cost_claims():
    payload = json.loads(
        (ROOT / "registries/m4_rmb_base_mapping_v2.json").read_text(encoding="utf-8")
    )
    assert payload["scientific_status"] == "FROZEN"
    assert payload["implementation_status"] == "MATCH"
    assert payload["base_beta"] == 1.0
    assert "not currency conversion" in payload["claim_boundary"]
    assert "empirical airline loss" in payload["claim_boundary"]


def test_active_risk_policy_materializes_frozen_objective():
    payload = load_active_risk_policy_payload()
    policy = load_active_risk_policy()
    assert payload["policy_id"] == "M4_RISK_POLICY_BASE_V1"
    assert payload["lambda"] == 0.25
    assert policy.alpha == 0.90
    assert policy.expected_loss_coefficient == 0.75
    assert policy.cvar_coefficient == 0.25
    assert policy.expected_loss_coefficient + policy.cvar_coefficient == 1.0
    assert policy.policy_status.value == "FROZEN"


def test_superseded_eur_registries_are_not_active_loader_inputs():
    active_loader = (ROOT / "model/M4/scientific_registry.py").read_text(
        encoding="utf-8"
    )
    assert "m4_eur_mapping" not in active_loader
    assert "monetary_mapping_registry" not in active_loader


def test_superseded_eur_builder_is_not_an_active_runtime_module():
    assert not (ROOT / "model/M4/monetary_mapping_registry.py").exists()
