from model.M2.contracts import ConsequenceRow
from model.M2.rmb_adapter import consequence_component
from model.M2.contracts import ExposureConfidence, SourceType
from model.common.enums import EvidenceClass, SupportState


def test_m2_rmb_adapter_exposes_native_consequence_not_cu():
    row = ConsequenceRow.model_construct(
        component_id="F_continuity",
        scenario_id=0,
        scenario_weight=1.0,
        aspect="Flight",
        native_quantity=12.0,
        native_unit="minutes",
        driver="test",
        support_state=SupportState.SUPPORTED,
        evidence_class=EvidenceClass.DIRECT,
        source_type=SourceType.DATA,
        reference_source="TEST",
        reference_lineage=("sha256:" + "1" * 64,),
        confidence=ExposureConfidence.HIGH,
        native_artifact_id="sha256:" + "2" * 64,
    )
    value = consequence_component(row)
    assert value["consequence_value"] == 12.0
    assert "value_cu" not in value
