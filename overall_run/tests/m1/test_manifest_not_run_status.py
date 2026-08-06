from __future__ import annotations

from overall_run.src.m1 import M1Pipeline


def test_manifest_does_not_infer_pass_from_code_or_target_support(published_bundle) -> None:
    manifest = M1Pipeline.not_run_manifest(published_bundle)
    assert manifest.feature_schema_status == "CODE_READY_NOT_RUN"
    assert manifest.snapshot_builder_status == "CODE_READY_NOT_RUN"
    assert manifest.target_support_status == "NOT_AUDITED"
    assert manifest.training_status == "NOT_RUN"
    assert manifest.checkpoint_status == "MISSING_NOT_RUN"
    assert manifest.calibration_status == "NOT_RUN"
    assert manifest.evaluation_status == "NOT_RUN"
    assert manifest.runtime_state_status == "CODE_READY_NOT_RUN"
    assert manifest.m2_interface_status == "M2_V2_CODE_READY_NOT_RUN"
    assert manifest.engineering_status == "CODE_MODIFIED_NOT_VALIDATED"
    assert manifest.scientific_status == "NOT_READY"
