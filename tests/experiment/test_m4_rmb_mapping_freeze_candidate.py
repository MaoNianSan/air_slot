import json
from pathlib import Path

from exp.m4_rmb_mapping_freeze_candidate import materialize
from model.common.consequence_ontology import CONSEQUENCE_COMPONENTS
from model.common.rmb_mapping import RMBMappingRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_freeze_candidate_is_transparent_and_non_authoritative(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    candidate = json.loads(paths["candidate"].read_text(encoding="utf-8"))
    registry_payload = json.loads(paths["registry"].read_text(encoding="utf-8"))
    registry = RMBMappingRegistry.model_validate(registry_payload)
    assert candidate["chain"] == "C -> CU -> RMB -> risk"
    assert candidate["freeze_status"] == "TEST_ONLY"
    assert candidate["scientific_boundary"]["authoritative_ranking_allowed"] is False
    assert tuple(candidate["component_order"]) == CONSEQUENCE_COMPONENTS
    assert registry.executable is True
    assert registry.authoritative is False
    assert len(registry.component_mappings) == 7
    assert all(rule.parameters[0].value == 1.0 for rule in registry.component_mappings.values())
    assert candidate["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0


def test_freeze_candidate_records_sensitivity_without_selection(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    candidate = json.loads(paths["candidate"].read_text(encoding="utf-8"))
    for row in candidate["components"]:
        assert row["parameter_source"] == "SCENARIO_ASSUMPTION_UNIT_NORMALIZATION"
        assert row["sensitivity_plan"]["global_scale_values"] == [0.5, 1.0, 2.0]
        assert "no Development-based selection" in row["sensitivity_plan"]["selection_rule"]
