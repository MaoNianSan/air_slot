import json
from pathlib import Path

from exp.workflows.m1_v2_development_semantic_reconciliation import materialize_semantic_reconciliation


ROOT = Path(__file__).resolve().parents[2]


def test_semantic_reconciliation_separates_aliases_from_stage_drift(tmp_path: Path):
    output = materialize_semantic_reconciliation(
        root=ROOT,
        output=tmp_path / "semantic_reconciliation.json",
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    comparison = payload["semantic_comparison"]
    assert payload["status"] == "M1_V2_DEVELOPMENT_INFERENCE_BINDING_BLOCKED_STAGE_SEMANTIC_DRIFT"
    assert comparison["expected_node_count"] == 69
    assert comparison["reconstructed_node_count"] == 69
    assert comparison["core_identity_exact"] is True
    assert comparison["typed_legal_record_alias_count"] == 69
    assert comparison["stage_exact_match_count"] == 66
    assert comparison["stage_mismatch_count"] == 3
    assert {item["node_index"] for item in comparison["stage_mismatches"]} == {21, 11, 13}
    assert payload["FINAL_TEST_ACCESS_COUNT"] == 0
    assert payload["PAPER_FULL_RUN"] is False
    assert payload["downstream_boundary"]["synthetic_metrics_generated"] is False
