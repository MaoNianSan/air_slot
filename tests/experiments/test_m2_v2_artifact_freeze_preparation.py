import json
from pathlib import Path

from exp.workflows.m2_v2_artifact_freeze_preparation import COMPONENTS, prepare_artifact_freeze


ROOT = Path(__file__).resolve().parents[2]


def test_m2_v2_freeze_preparation_is_typed_and_keeps_unresolved_support_explicit(tmp_path):
    paths = prepare_artifact_freeze(root=ROOT, output_root=tmp_path)
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    typed = json.loads(paths["typed_output_contract"].read_text(encoding="utf-8"))
    lineage = json.loads(paths["lineage_schema"].read_text(encoding="utf-8"))
    validation = json.loads(paths["validation_report"].read_text(encoding="utf-8"))
    readiness = json.loads(paths["readiness"].read_text(encoding="utf-8"))

    assert manifest["status"] == "M2_V2_ARTIFACT_FREEZE_READY"
    assert tuple(manifest["component_order"]) == COMPONENTS
    assert manifest["m1_binding"]["model_id"] == "M1_V2_GRU_H32"
    assert manifest["existing_v1_registry"]["reuse_policy"] == "PROVENANCE_ONLY_NOT_V2_RELABELLED"

    assert tuple(typed["component_order"]) == COMPONENTS
    assert typed["scalar_aggregation"]["value"] is None
    assert typed["scalar_aggregation"]["sortable"] is False
    assert typed["scalar_aggregation"]["status"] == "BLOCKED_M2_V2_FORMAL_AGGREGATE_UNRESOLVED"
    p_itinerary = next(row for row in typed["component_rows"] if row["component_id"] == "P_itinerary")
    p_service = next(row for row in typed["component_rows"] if row["component_id"] == "P_service")
    assert p_itinerary["support_contract"] == "ABSTAIN_UNSUPPORTED_CURRENT_DATA2_CONTRACT"
    assert p_service["support_contract"] == "ABSTAIN_UNSUPPORTED_CURRENT_DATA2_CONTRACT"
    assert typed["no_monetary_overclaim"] is True
    assert typed["no_unsupported_cu_mapping"] is True
    assert typed["no_zero_fill"] is True

    assert "NO_MISSING_LINEAGE_FIELDS" in lineage["invariants"]
    assert validation["status"] == "READY_WITH_FORMAL_AGGREGATE_BLOCKED"
    assert validation["checks"]["NO_MONETARY_OVERCLAIM"]["status"] == "PASS"
    assert validation["checks"]["NO_UNSUPPORTED_CU_MAPPING"]["status"] == "PASS"
    assert validation["checks"]["P_ITINERARY_P_SERVICE"]["status"] == "BLOCKED"
    assert readiness["status"] == "M2_V2_ARTIFACT_FREEZE_READY"
    assert readiness["artifact_status"] == "BLOCKED_M2_V2_FORMAL_VALUES_AND_AGGREGATE"
    assert readiness["safety"]["EXP2_RUNS_THIS_PREPARATION"] == 0
    assert readiness["safety"]["EXP3_RUNS_THIS_PREPARATION"] == 0
    assert readiness["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert readiness["safety"]["PAPER_FULL_RUN"] is False
