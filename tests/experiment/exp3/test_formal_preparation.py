import json
from pathlib import Path

from exp.exp3.formal_preparation import FORMAL_VARIANT_IDS, prepare_formal_execution


ROOT = Path(__file__).resolve().parents[3]


def test_formal_preparation_records_variants_and_keeps_execution_gated(tmp_path):
    paths = prepare_formal_execution(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    contracts = json.loads(paths["variant_contracts"].read_text(encoding="utf-8"))
    schema = json.loads(paths["lineage_schema"].read_text(encoding="utf-8"))
    readiness = json.loads(paths["readiness"].read_text(encoding="utf-8"))

    assert manifest["status"] == "EXP3_FORMAL_EXECUTION_READY"
    assert tuple(manifest["variants"]) == FORMAL_VARIANT_IDS
    assert manifest["m1_binding"] == {"model_id": "M1_V2_GRU_H32", "modified": False}
    assert contracts["variants"]["FULL_CHAIN"]["runtime_full"] is False
    assert contracts["variants"]["MODULE_REMOVAL_M3"]["removed_output_policy"] == "ABSTAIN_NO_SUBSTITUTION"
    assert contracts["variants"]["LAG_10"]["state_vintage_lag_minutes"] == 10
    assert "MODULE_REMOVAL_OUTPUT_IS_ABSTAIN_NOT_ZERO" in schema["invariants"]
    assert readiness["preparation_status"] == "READY"
    assert readiness["execution_status"] == "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES"
    assert all(item["status"] == "BLOCKED_CURRENT_FROZEN_ARTIFACT_GATES" for item in readiness["variant_readiness"].values())
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["FULL"] is False
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
