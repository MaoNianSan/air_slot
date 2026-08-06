from __future__ import annotations

from src.m3 import evaluate_m3_structure, sample_count_stability


def test_artifact_frames_and_hashes_are_stable(fixture_artifact) -> None:
    response = fixture_artifact.response_samples_frame()
    costs = fixture_artifact.implementation_costs_frame()
    assert len(response) == 18 * 256 * 9
    assert len(costs) == 18 * 256
    assert response["action_library_version"].nunique() == 1
    assert costs["action_library_version"].nunique() == 1
    for value in (
        fixture_artifact.action_library_hash,
        fixture_artifact.footprint_hash,
        fixture_artifact.parameter_hash,
        fixture_artifact.sample_hash,
        fixture_artifact.artifact_hash,
    ):
        assert len(value) == 64


def test_structure_evaluation_is_not_scientific_pass(m3_contract, fixture_artifact) -> None:
    result = evaluate_m3_structure(m3_contract, fixture_artifact)
    assert result["M3_EVALUATION_SCIENTIFIC_STATUS"] == "STRUCTURE_ONLY"
    assert result["A00_identity"] is True
    assert result["structural_none_exactness"] is True
    assert result["M2_compatibility"] is True
    assert result["parameter_readiness"] == "NOT_READY"
    assert result["M4_status"] == "BLOCKED"


def test_sample_count_stability_only_reports(m3_contract, cfg) -> None:
    frame = sample_count_stability(
        m3_contract,
        cfg.scientific["m2"],
        draw_counts=(100, 500),
        base_seed=23,
    )
    assert frame["response_draw_count"].tolist() == [100, 500]
    assert "selected_draw_count" not in frame.columns
