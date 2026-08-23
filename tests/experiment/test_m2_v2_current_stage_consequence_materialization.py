import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = (
    ROOT
    / "artifacts/experiment/m2_v2_current_stage_consequences_v1"
    / "M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCES.json"
)
MANIFEST = ARTIFACT.with_name("M2_V2_CURRENT_STAGE_TYPED_CONSEQUENCE_MANIFEST.json")

COMPONENT_ORDER = (
    "F_continuity",
    "F_execution",
    "F_propagation",
    "P_time",
    "P_itinerary",
    "P_service",
    "R_operating",
)


def test_current_stage_m2_artifact_preserves_typed_abstention_and_lineage():
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert artifact["artifact_hash"] == manifest["artifact_hash"]
    assert artifact["source_m1_artifact_hash"] == manifest["source_m1_artifact_hash"]
    assert artifact["row_count"] == manifest["row_count"] == 17_250
    assert artifact["node_count"] == manifest["node_count"] == 69
    assert tuple(artifact["component_order"]) == COMPONENT_ORDER
    assert artifact["zero_fill"] is False
    assert artifact["silent_renormalization"] is False
    assert artifact["monetary_claim"] is False
    assert artifact["seven_component_status_counts"] == {"ABSTAIN": 17_250}
    assert artifact["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert artifact["safety"]["PAPER_FULL_RUN"] is False
    assert artifact["safety"]["FULL"] is False

    for row in artifact["consequences"]:
        assert tuple(item["component_id"] for item in row["components"]) == COMPONENT_ORDER
        unresolved = {item["component_id"]: item for item in row["components"]}
        for component_id in ("P_itinerary", "P_service"):
            assert unresolved[component_id]["support_state"] == "ABSTAIN"
            assert unresolved[component_id]["constructed_value_cu"] is None
            assert unresolved[component_id]["reference_lineage"]
        assert row["seven_component_status"] == "ABSTAIN"
        assert row["seven_component_value_cu"] is None

