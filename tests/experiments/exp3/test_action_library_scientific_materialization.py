import json
from pathlib import Path

from exp.exp3.action_library_scientific_materialization import materialize
from model.M3.registry import PRINCIPAL_IDS


ROOT = Path(__file__).resolve().parents[3]


def test_action_library_is_paper_supported_without_formal_effect_overclaim(tmp_path):
    paths = materialize(root=ROOT, output_root=tmp_path)
    artifact = json.loads(paths["artifact"].read_text(encoding="utf-8"))

    assert artifact["status"] == "M3_PAPER_SUPPORTED_ACTION_LIBRARY_MATERIALIZED"
    assert artifact["schema_version"] == "M3_ACTION_LIBRARY_SCIENTIFIC_MATERIALIZATION_V2"
    assert artifact["action_count"] == 23
    assert tuple(row["action_id"] for row in artifact["action_evidence_table"]) == PRINCIPAL_IDS
    assert artifact["execution_status_counts"] == {"conditional": 22, "executable": 1}
    assert all(row["literature_reference"] for row in artifact["action_evidence_table"])
    assert all(row["consequence_literature"] for row in artifact["action_evidence_table"])
    assert all(row["effect_mechanism"] for row in artifact["action_evidence_table"])
    assert artifact["formal_support_upgrade"] is False
    assert artifact["non_a00_v2_execution_enabled"] is True
    assert artifact["exp3_readiness_impact"]["formal_executable_non_a00_count"] == 22
    assert artifact["exp3_readiness_impact"]["formal_multi_action_cohort"] == "READY_SCENARIO_CONDITIONAL_AUTHORITATIVE_RANKING_GATED"
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
