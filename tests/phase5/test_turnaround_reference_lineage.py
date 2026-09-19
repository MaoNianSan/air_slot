"""Freeze-precheck (2026-09-19): corrected A2 turnaround reference lineage.

The audit showed the superseded reference ``sha256:7c6ac016...`` was not stale
metadata: it resolved the M2 node-reference bundle at decision time through
``F_continuity = max(0, R_IB - turnaround_reference)``. These tests pin the
corrected lineage, the separation between the M2 node-reference median and the
Stage-II Q20 lower-tail support, and the recomputed ``F_continuity`` Train
scale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from exp.exp2 import development_inputs
from model.M2.context import load_data2_reference_bundle
from model.M2.scientific_registry import load_active_v2_cu_registry
from model.common.identity import content_id
from validation.v2_phase5 import common as phase5_common


ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = ROOT / "artifacts" / "diagnostics" / "v2_phase5_development"
PRECHECK_DIR = ROOT / "artifacts" / "diagnostics" / "v2_freeze_precheck"
SCALE_CORRECTION_PATH = (
    PRECHECK_DIR / "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json"
)
FREEZE_DRAFT_PATH = ROOT / "registries" / "v2_scientific_freeze_draft.json"
FREEZE_SUMMARY_PATH = ROOT / "docs" / "V2_SCIENTIFIC_FREEZE_SUMMARY.md"

CORRECTED_REFERENCE_ID = (
    "sha256:aa241b902536c500c21e6a9563ba3c9ac563d1167d4220c77a1e89771677ad57"
)
SUPERSEDED_REFERENCE_ID = (
    "sha256:7c6ac01673f200260fc925eb4c0b57f143fcc34532832375124945252b69707c"
)
SEMANTIC_CORRECTION = "BTS_SIGNED_DELAY_SEMANTIC_CORRECTION"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_active_m2_node_reference_is_the_corrected_a2_artifact():
    payload = development_inputs._reference_payloads()["turnaround"]
    assert development_inputs.TURNAROUND_A2_REFERENCE == (
        phase5_common.CORRECTED_TURNAROUND_REFERENCE_PATH
    )
    assert payload["reference_id"] == CORRECTED_REFERENCE_ID
    assert payload["semantic_correction"] == SEMANTIC_CORRECTION
    assert payload["global_value_minutes"] == pytest.approx(57.0)
    assert payload["global_sample_count"] == 2668529
    assert payload["cells_count"] == 349
    assert payload["reference_id"] != SUPERSEDED_REFERENCE_ID


def test_reference_bundle_binds_only_the_corrected_node_reference():
    bundle = load_data2_reference_bundle(development_inputs._reference_payloads())
    assert bundle.reference_ids["turnaround"] == CORRECTED_REFERENCE_ID
    assert SUPERSEDED_REFERENCE_ID not in set(bundle.reference_ids.values())
    resolved = bundle.turnaround.lookup("ABE")
    assert resolved.value is not None
    corrected = _read(phase5_common.CORRECTED_TURNAROUND_REFERENCE_PATH)
    cells = {cell["airport_id"]: cell["value_minutes"] for cell in corrected["cells"]}
    assert resolved.value == pytest.approx(cells["ABE"])


def test_superseded_reference_is_retained_as_provenance_only():
    registry = load_active_v2_cu_registry()
    entry = registry.reference_artifacts["turnaround"]
    assert entry["reference_id"] == CORRECTED_REFERENCE_ID
    assert entry["path"] == (
        "artifacts\\diagnostics\\m1_v2_data_gate_a2"
        "\\DATA2_TURNAROUND_REFERENCE_GATE_A2_DIAGNOSTIC.json"
    )
    assert entry["superseded_reference_id"] == SUPERSEDED_REFERENCE_ID
    assert entry["semantic_correction"] == SEMANTIC_CORRECTION
    superseded = _read(phase5_common.SUPERSEDED_TURNAROUND_REFERENCE_PATH)
    assert superseded["reference_id"] == SUPERSEDED_REFERENCE_ID
    assert superseded["global_value_minutes"] == pytest.approx(51.0)


def test_m2_median_reference_and_stage2_q20_bound_are_separate_quantities():
    summary = _read(PHASE_DIR / "TRAIN_TURNAROUND_HEADROOM_SUMMARY.json")
    reference = summary["turnaround_reference"]
    assert reference["reference_id"] == CORRECTED_REFERENCE_ID
    assert reference["global_value_minutes"] == pytest.approx(57.0)
    quantiles = summary["turnaround"]["quantile_minutes"]
    assert quantiles["q20"] == pytest.approx(41.0)
    assert summary["turnaround"]["nominal_quantile"] == 0.20
    assert quantiles["q20"] != pytest.approx(reference["global_value_minutes"])
    assert reference["scope"] == "M2_NODE_REFERENCE_BUNDLE_FOR_F_CONTINUITY"
    assert reference["statistic_id"] == "MEDIAN"
    assert reference["applicability_scope"] == "AIRPORT_GROUP"
    assert reference["cells_count"] == 349
    assert reference["distinct_from_stage2_lower_bound"] is True
    stage2 = summary["stage2_turnaround_lower_bound"]
    assert stage2["scope"] == "M3_STAGE2_FEASIBILITY_ONLY"
    assert stage2["value_minutes"] == pytest.approx(41.0)
    assert stage2["sensitivity_minutes"] == {
        "q10": pytest.approx(34.0),
        "q30": pytest.approx(47.0),
    }
    assert stage2["population_rows"] == summary["rotation_count"]
    assert stage2["value_minutes"] != pytest.approx(
        reference["global_value_minutes"]
    )


def test_f_continuity_train_scale_is_recomputed_from_the_corrected_reference():
    if not SCALE_CORRECTION_PATH.is_file():
        pytest.skip(f"scale correction not materialized: {SCALE_CORRECTION_PATH}")
    payload = _read(SCALE_CORRECTION_PATH)
    assert payload["component"] == "F_continuity"
    assert payload["scale_rule"] == "Median_Train(q_k | q_k > 0)"
    assert payload["population_rows"] == 2668531
    assert payload["final_test_access_count"] == 0
    assert payload["paper_full_run"] is False
    assert payload["reference_lineage"]["active_reference_id"] == (
        CORRECTED_REFERENCE_ID
    )
    assert payload["reference_lineage"]["superseded_reference_id"] == (
        SUPERSEDED_REFERENCE_ID
    )
    assert payload["superseded_scale"]["median"] == pytest.approx(43.0)
    assert payload["superseded_scale"]["positive_n"] == 206787
    stripped = dict(payload)
    declared = stripped.pop("artifact_hash")
    assert declared == content_id(stripped)

    registry = load_active_v2_cu_registry()
    active = registry.train_scale_artifact["F_continuity"]
    assert registry.scale("F_continuity") == pytest.approx(payload["median"])
    assert active["artifact_hash"] == declared
    assert active["median"] == pytest.approx(payload["median"])
    assert active["positive_n"] == payload["positive_n"]
    assert active["population_rows"] == payload["population_rows"]


def test_f_continuity_correction_leaves_the_other_principal_scales_inherited():
    registry = load_active_v2_cu_registry()
    for component, expected in (
        ("F_execution", 17.0),
        ("F_propagation", 10.0),
        ("P_time", 990.3555555555556),
        ("R_operating", 5.0),
    ):
        assert registry.scale(component) == pytest.approx(expected)
    assert registry.registry_id == "M2_DATA2_FORMAL_CU_V5"


def test_freeze_draft_records_the_precheck_without_activation():
    draft = _read(FREEZE_DRAFT_PATH)
    precheck = draft["turnaround_reference_precheck"]
    assert precheck["audit_finding"] == (
        "SUPERSEDED_REFERENCE_WAS_ACTIVE_NOT_STALE_METADATA"
    )
    assert precheck["active_reference"]["reference_id"] == CORRECTED_REFERENCE_ID
    assert precheck["superseded_reference"]["reference_id"] == (
        SUPERSEDED_REFERENCE_ID
    )
    assert precheck["superseded_reference"]["status"] == (
        "SUPERSEDED_PROVENANCE_ONLY"
    )
    delta = precheck["reference_delta"]
    assert delta["shared_cells"] == 349
    assert delta["changed_cells"] == 332
    assert delta["max_abs_delta_minutes"] == pytest.approx(41.5)
    assert delta["global_median_delta_minutes"] == pytest.approx(6.0)
    assert precheck["semantics"]["same_quantity"] is False
    assert precheck["semantics"]["stage2_nominal_minutes"] == pytest.approx(41.0)
    assert precheck["semantics"]["scalar_substitution_rejected"] is True
    assert precheck["m1_retrained_this_round"] is False
    assert precheck["new_final_test_access_this_round"] is False
    assert draft["status"] == "DRAFT_NOT_ACTIVATED"
    assert draft["freeze_commit"] == "PENDING"
    assert draft["new_final_test_execution"] is False
    rulings = {item["id"] for item in draft["rulings_this_round"]}
    assert {"R7", "R8"} <= rulings
    summary = FREEZE_SUMMARY_PATH.read_text(encoding="utf-8")
    assert "Turnaround reference freeze-precheck" in summary
