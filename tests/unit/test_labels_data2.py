from pathlib import Path

import pytest
import yaml

from model.PRE.transformation import (
    ConstructionType,
    TransformationStatus,
    current_transformation_registry,
)
from model.PRE.feature_registry.loader import load_registry_bundle
from model.common.enums import EvidenceClass
from model.common.errors import ContractError


def test_three_label_rules_registered_and_frozen():
    registry = current_transformation_registry()
    for rule_id in ("DATA2_LABEL_R_IB", "DATA2_LABEL_DELTA_OB", "DATA2_LABEL_T_TX"):
        rule = registry.get(rule_id, "1.0.0")
        assert rule.status is TransformationStatus.FROZEN
        assert rule.construction_type is ConstructionType.DETERMINISTIC_DERIVATION
        assert rule.availability_basis.value == "POSTHOC_ONLY"
        assert rule.evidence_class is EvidenceClass.DIRECT
        assert rule.support_ceiling is EvidenceClass.DIRECT


def test_label_formulas_and_caps_are_frozen():
    registry = current_transformation_registry()
    ib = registry.get("DATA2_LABEL_R_IB", "1.0.0")
    ob = registry.get("DATA2_LABEL_DELTA_OB", "1.0.0")
    tx = registry.get("DATA2_LABEL_T_TX", "1.0.0")
    assert "max(0, pred.actual_arrival_utc - decision_time)" in ib.formula_or_algorithm
    assert "m1_r_ib_max_finite_minutes=360" in ib.formula_or_algorithm
    assert "DELTA_OB = succ.actual_departure_utc - succ.scheduled_departure_utc" in ob.formula_or_algorithm
    assert "-180..+180" in ob.formula_or_algorithm
    assert "succ.taxi_out_minutes" in tx.formula_or_algorithm
    assert "m1_t_tx_max_finite_minutes=60" in tx.formula_or_algorithm
    for rule in (ib, ob, tx):
        assert "no clip" in rule.formula_or_algorithm
        assert "STAGE_GATED" in rule.formula_or_algorithm


def test_label_formulas_match_foundation_config_caps():
    # The D2-8 freeze must agree with the shared foundation config that M1
    # actually consumes; any drift would change label binning silently.
    cfg = yaml.safe_load(Path("configs/scientific/foundation.yaml").read_text(encoding="utf-8"))
    params = cfg["parameters"]
    assert params["m1_r_ib_max_finite_minutes"]["value"] == 360
    assert "m1_delta_ob_max_finite_minutes" not in params
    assert params["m1_t_tx_max_finite_minutes"]["value"] == 60
    assert params["m1_r_ib_max_finite_minutes"]["freeze_state"] == "FROZEN"


def test_data_usage_rule_entries_frozen_eval_outcome():
    bundle = load_registry_bundle(Path("registries"))
    rules = {r.rule_id: r for r in bundle.data_usage_rules}
    for rid, cap in (("D2-LABEL-R-IB", "360"), ("D2-LABEL-DELTA-OB", "180"),
                     ("D2-LABEL-T-TX", "60")):
        rule = rules[rid]
        assert rule.freeze_state.value == "FROZEN"
        assert rule.dataset_id == "data2_2019"
        assert rule.decision_time_role.value == "EVAL_OUTCOME"
        assert rule.availability_rule == "posthoc_only"
        assert rule.evidence_class.value == "DIRECT"
        assert rule.support_ceiling.value == "DIRECT"
        assert "M1" in rule.downstream_consumers
        assert cap in rule.raw_semantics
        assert "D2-BTS-ACTUAL" in rule.external_evidence_rule_ids


def test_data1_rules_untouched_by_label_freeze():
    bundle = load_registry_bundle(Path("registries"))
    rules = {r.rule_id: r for r in bundle.data_usage_rules}
    # data1 label semantics live in the D1-* event rules and foundation
    # config; none of them were rewritten by D2-8.
    for rid in ("D1-OPENSKY-STATE", "D1-OPENSKY-FLIGHT", "D1-OPENSKY-FLIGHT-EVENT",
                "D1-TRAJECTORY-EVENT", "D1-METAR", "D1-EUROSTAT"):
        assert rid in rules
        assert rules[rid].freeze_state.value == "FROZEN"
        assert rules[rid].dataset_id == "data1_2019"
    assert all(r.dataset_id == "data2_2019" for rid, r in rules.items()
               if rid.startswith("D2-LABEL"))


def test_label_rules_have_no_inference_evidence_role():
    # POSTHOC_ONLY is a hard boundary: labels must never be usable as
    # decision-time inference evidence.
    bundle = load_registry_bundle(Path("registries"))
    for rule in bundle.data_usage_rules:
        if rule.rule_id.startswith("D2-LABEL"):
            assert rule.decision_time_role.value == "EVAL_OUTCOME"
            assert "INFERENCE_EVIDENCE" not in rule.decision_time_role.value
            assert "POSTHOC" in rule.availability_rule.upper() or "posthoc" in rule.availability_rule
