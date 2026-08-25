"""M4 constructed-EUR monetary mapping plan (decision 2026-08-24 D1) tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from exp.workflows.monetary_mapping_plan_materialization import build_plan
from model.M4.monetary_mapping_plan import (
    EU261Staircase,
    EU261Tier,
    MonetaryConversionPlan,
    MonetaryMappingPlanRegistry,
    NumericAnchorStatus,
    NumericFreezeStatus,
    OpsComponentRule,
    OpsCostBand,
    OPS_LAYER,
    PASSENGER_LAYER,
)
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registries" / "m4_eur_mapping_assumption_grounded_v1.json"
REFERENCES = ("REF_A", "REF_B")


def _ops_rule(
    component_id: str,
    *,
    layer: str = OPS_LAYER,
    base_money: float | None = None,
    anchor_reason: str | None = None,
) -> OpsComponentRule:
    if base_money is not None:
        return OpsComponentRule(
            component_id=component_id,
            layer=layer,
            base_per_cu_money=base_money,
            base_reference=REFERENCES,
            anchor_status=NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED,
            anchor_reason=anchor_reason or "anchor applies directly",
            bands=(
                OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=base_money * 0.5),
                OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=base_money),
                OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=base_money * 2.0),
            ),
        )
    return OpsComponentRule(
        component_id=component_id,
        layer=layer,
        base_per_cu_money=None,
        base_reference=REFERENCES,
        anchor_status=NumericAnchorStatus.HUMAN_DECISION_REQUIRED,
        anchor_reason=anchor_reason or "no per-CU anchor in retrieved literature",
        bands=(
            OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=None),
            OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=None),
            OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=None),
        ),
    )


def _frozen_conversion_plan() -> MonetaryConversionPlan:
    return MonetaryConversionPlan(
        status="FROZEN",
        issue="dual EUR-native layers; no cross-currency conversion",
        options=(
            {
                "option_id": "OPTION_A_DUAL_LAYER",
                "description": "dual layer without conversion",
                "assumptions": ("no exchange-rate assumption",),
                "recommended": True,
            },
            {
                "option_id": "OPTION_B_FIXED_RATE",
                "description": "fixed reference rate conversion",
                "assumptions": ("requires a reference rate",),
                "recommended": False,
            },
        ),
    )


def _plan_registry(**overrides) -> MonetaryMappingPlanRegistry:
    values = {
        "numeric_freeze_status": NumericFreezeStatus.FROZEN_ASSUMPTION_GROUNDED,
        "monetary_ground_truth_claim": False,
        "claim_statement": "constructed scale anchored on EUROCONTROL EUR-basis values, not a currency conversion",
        "ops_components": tuple(
            _ops_rule(
                component,
                layer=PASSENGER_LAYER if component.startswith("P_") else OPS_LAYER,
                base_money=None if component in ("P_itinerary", "P_service") else 50.0,
            )
            for component in CONSEQUENCE_COMPONENTS
        ),
        "eu261": EU261Staircase(
            trigger_minutes=180,
            tau_comp_options_minutes=(150, 180, 210),
            tau_comp_selected_minutes=180,
            tau_comp_sensitivity_minutes=(150, 210),
            tiers=(
                EU261Tier(max_distance_km=1500, compensation_eur=250),
                EU261Tier(max_distance_km=3500, compensation_eur=400),
                EU261Tier(max_distance_km=None, compensation_eur=600),
            ),
            regulatory_reference=REFERENCES,
        ),
        "conversion_plan": _frozen_conversion_plan(),
        "references": REFERENCES,
    }
    values.update(overrides)
    return MonetaryMappingPlanRegistry(**values)


class TestOpsComponentRule:
    def test_frozen_rule_requires_matching_bands(self):
        rule = _ops_rule("F_continuity", base_money=72.0)
        assert rule.base_per_cu_money == 72.0
        assert tuple(band.per_cu_money for band in rule.bands) == (36.0, 72.0, 144.0)

    def test_wrong_band_values_rejected(self):
        with pytest.raises(ValidationError):
            OpsComponentRule(
                component_id="F_continuity",
                layer=OPS_LAYER,
                base_per_cu_money=72.0,
                base_reference=REFERENCES,
                anchor_status=NumericAnchorStatus.FROZEN_ASSUMPTION_GROUNDED,
                anchor_reason="anchor applies directly",
                bands=(
                    OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=1.0),
                    OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=72.0),
                    OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=144.0),
                ),
            )

    def test_wrong_band_order_rejected(self):
        with pytest.raises(ValidationError):
            OpsComponentRule(
                component_id="F_continuity",
                layer=OPS_LAYER,
                base_per_cu_money=None,
                base_reference=REFERENCES,
                anchor_status=NumericAnchorStatus.HUMAN_DECISION_REQUIRED,
                anchor_reason="no per-CU anchor in retrieved literature",
                bands=(
                    OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=None),
                    OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=None),
                    OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=None),
                ),
            )

    def test_pending_anchor_requires_reason(self):
        with pytest.raises(ValidationError):
            OpsComponentRule(
                component_id="P_itinerary",
                layer=PASSENGER_LAYER,
                base_per_cu_money=None,
                base_reference=REFERENCES,
                anchor_status=NumericAnchorStatus.HUMAN_DECISION_REQUIRED,
                anchor_reason=None,
                bands=(
                    OpsCostBand(band_id="LOW", scale_factor=0.5, per_cu_money=None),
                    OpsCostBand(band_id="BASE", scale_factor=1.0, per_cu_money=None),
                    OpsCostBand(band_id="HIGH", scale_factor=2.0, per_cu_money=None),
                ),
            )


class TestPlanRegistry:
    def test_exact_seven_components(self):
        registry = _plan_registry()
        assert tuple(rule.component_id for rule in registry.ops_components) == CONSEQUENCE_COMPONENTS

    def test_frozen_status_requires_numbers_claim_and_conversion(self):
        with pytest.raises(ValidationError):
            _plan_registry(claim_statement="")
        with pytest.raises(ValidationError):
            _plan_registry(
                conversion_plan=MonetaryConversionPlan(
                    status="PLAN_REQUIRING_HUMAN_CONFIRMATION",
                    issue="not frozen",
                    options=(
                        {
                            "option_id": "A",
                            "description": "a",
                            "assumptions": ("x",),
                            "recommended": True,
                        },
                    ),
                )
            )
        rules = tuple(
            _ops_rule(component, base_money=None)
            for component in CONSEQUENCE_COMPONENTS
        )
        with pytest.raises(ValidationError):
            _plan_registry(ops_components=rules)

    def test_pending_components_allowed_under_frozen_registry(self):
        registry = _plan_registry()
        assert registry.numeric_frozen is True
        assert registry.pending_anchor_components == ("P_itinerary", "P_service")
        cu = {component: 2.0 for component in CONSEQUENCE_COMPONENTS}
        money = registry.ops_money(cu)
        assert money is not None
        assert set(money) == {"F_continuity", "F_execution", "F_propagation", "P_time", "R_operating"}
        assert money["F_continuity"] == 100.0
        assert money["P_time"] == 100.0
        assert "P_itinerary" not in money
        assert "P_service" not in money

    def test_ground_truth_claim_forbidden(self):
        with pytest.raises(ValidationError):
            _plan_registry(monetary_ground_truth_claim=True)

    def test_safety_fields(self):
        registry = _plan_registry()
        assert registry.final_test_access_count == 0
        assert registry.paper_full_run is False

    def test_hash_consistency(self):
        registry = _plan_registry()
        payload = registry.registry_payload()
        payload["registry_hash"] = registry.digest()
        reloaded = MonetaryMappingPlanRegistry(**payload)
        assert reloaded.digest() == registry.digest()

    def test_conversion_plan_single_recommendation(self):
        with pytest.raises(ValidationError):
            _plan_registry(
                conversion_plan=MonetaryConversionPlan(
                    status="FROZEN",
                    issue="issue",
                    options=(
                        {
                            "option_id": "A",
                            "description": "a",
                            "assumptions": ("x",),
                            "recommended": True,
                        },
                        {
                            "option_id": "B",
                            "description": "b",
                            "assumptions": ("y",),
                            "recommended": True,
                        },
                    ),
                )
            )

    def test_eu261_selected_tau_not_in_sensitivity(self):
        with pytest.raises(ValidationError):
            EU261Staircase(
                trigger_minutes=180,
                tau_comp_options_minutes=(150, 180, 210),
                tau_comp_selected_minutes=180,
                tau_comp_sensitivity_minutes=(150, 180, 210),
                tiers=(
                    EU261Tier(max_distance_km=1500, compensation_eur=250),
                    EU261Tier(max_distance_km=3500, compensation_eur=400),
                    EU261Tier(max_distance_km=None, compensation_eur=600),
                ),
                regulatory_reference=REFERENCES,
            )

    def test_eu261_compensation_staircase(self):
        registry = _plan_registry()
        staircase = registry.eu261
        assert staircase.compensation_eur(delay_minutes=170, distance_km=900) == 0.0
        assert staircase.compensation_eur(delay_minutes=180, distance_km=900) == 250.0
        assert staircase.compensation_eur(delay_minutes=200, distance_km=2000) == 400.0
        assert staircase.compensation_eur(delay_minutes=200, distance_km=4000) == 600.0


class TestMaterializedRegistry:
    def test_registry_file_loads_and_hashes(self):
        assert REGISTRY_PATH.is_file(), REGISTRY_PATH
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        registry = MonetaryMappingPlanRegistry(**payload)
        assert registry.registry_hash == registry.digest()
        assert registry.monetary_system_id == "EUR"
        assert registry.numeric_freeze_status is NumericFreezeStatus.FROZEN_ASSUMPTION_GROUNDED
        assert registry.monetary_ground_truth_claim is False
        assert "EUR" in registry.claim_statement
        assert "not a currency conversion" in registry.claim_statement
        assert registry.pending_anchor_components == ("P_itinerary", "P_service")
        assert registry.eu261.tau_comp_selected_minutes == 180
        assert registry.eu261.tau_comp_sensitivity_minutes == (150, 210)
        assert registry.conversion_plan.status == "FROZEN"

    def test_registry_units_are_eur_native(self):
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert all(
            band["unit"] == "constructed_EUR_per_CU"
            for rule in payload["ops_components"]
            for band in rule["bands"]
        )
        assert "constructed_USD" not in json.dumps(payload)
        assert "USD" not in json.dumps(payload)

    def test_registry_frozen_values(self):
        registry = MonetaryMappingPlanRegistry(
            **json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        )
        by_id = {rule.component_id: rule for rule in registry.ops_components}
        assert by_id["F_continuity"].base_per_cu_money == 72.0
        assert by_id["F_execution"].base_per_cu_money == 72.0
        assert by_id["F_propagation"].base_per_cu_money == 72.0
        assert by_id["R_operating"].base_per_cu_money == 72.0
        assert by_id["P_time"].base_per_cu_money == 0.30
        assert by_id["P_itinerary"].anchor_status is NumericAnchorStatus.HUMAN_DECISION_REQUIRED
        assert by_id["P_service"].anchor_status is NumericAnchorStatus.HUMAN_DECISION_REQUIRED

    def test_registry_file_safety(self):
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert payload["final_test_access_count"] == 0
        assert payload["paper_full_run"] is False

    def test_build_plan_matches_materialized_registry(self):
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        assert build_plan().digest() == payload["registry_hash"]
