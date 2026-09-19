"""M2 CU V5 registry, design and supersession tests (Phase 2)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from model.M2.cu.registry import (
    EVENT_COMPONENTS,
    PRINCIPAL_FIVE_SCOPE,
    M2Data2FormalCuRegistry,
)
from model.M2.scientific_registry import (
    load_active_m2_cu_registry,
    load_active_passenger_consequence_design,
    load_active_v2_cu_registry,
    load_active_v2_passenger_consequence_design,
)
from model.common.errors import ContractError


ROOT = Path(__file__).resolve().parents[2]
V4_PATH = ROOT / "registries" / "m2_data2_formal_cu_v4.json"
V5_PATH = ROOT / "registries" / "m2_data2_formal_cu_v5.json"
SUPERSESSION_PATH = ROOT / "registries" / "passenger_reference_supersession_v3.json"

V4_PRINCIPAL_MEDIANS = {
    "F_execution": 17.0,
    "F_propagation": 10.0,
    "P_time": 990.3555555555556,
    "R_operating": 5.0,
}

#: The freeze-precheck (2026-09-19) recomputed F_continuity from the corrected
#: Data Gate A2 turnaround reference, so only these four V4 medians carry over
#: unchanged. F_continuity is asserted against its correction artifact.
SUPERSEDED_F_CONTINUITY_MEDIAN = 43.0
F_CONTINUITY_CORRECTION_PATH = (
    ROOT
    / "artifacts"
    / "diagnostics"
    / "v2_freeze_precheck"
    / "M2_F_CONTINUITY_TRAIN_SCALE_CORRECTED_V5.json"
)


def test_v5_registry_keeps_v4_principal_medians_and_event_unit_scales():
    registry = load_active_v2_cu_registry()
    assert registry.registry_id == "M2_DATA2_FORMAL_CU_V5"
    assert set(registry.train_scale_artifact) == set(PRINCIPAL_FIVE_SCOPE)
    for component, expected in V4_PRINCIPAL_MEDIANS.items():
        assert registry.scale(component) == pytest.approx(expected)
        assert (
            registry.train_scale_artifact[component]["median"] == expected
        )
        assert (
            registry.train_scale_artifact[component]["fit_period"] == "2019-H1"
        )
    continuity = registry.train_scale_artifact["F_continuity"]
    assert continuity["fit_period"] == "2019-H1"
    assert continuity["superseded_scale"]["median"] == pytest.approx(
        SUPERSEDED_F_CONTINUITY_MEDIAN
    )
    assert "v2_freeze_precheck" in continuity["path"]
    if F_CONTINUITY_CORRECTION_PATH.is_file():
        correction = json.loads(
            F_CONTINUITY_CORRECTION_PATH.read_text(encoding="utf-8")
        )
        assert registry.scale("F_continuity") == pytest.approx(
            correction["median"]
        )
        assert continuity["artifact_hash"] == correction["artifact_hash"]
        assert continuity["population_rows"] == correction["population_rows"]
    for component in EVENT_COMPONENTS:
        assert registry.scale(component) == pytest.approx(1.0)
    assert registry.scientific_status == "HUMAN_APPROVED_PENDING_FREEZE"


def test_v5_event_components_never_claim_an_empirical_median():
    registry = load_active_v2_cu_registry()
    for component in EVENT_COMPONENTS:
        item = registry.assumption_scale_artifact[component]
        assert item["normalization_status"] == "ASSUMPTION_EVENT_NORMALIZATION"
        assert item["empirical_train_positive_median"] is False
        assert item["scale"] == 1.0
        assert item["source"] == "ASSUMPTION_GROUNDED"


def test_v5_registry_rejects_empirical_scale_claims_or_missing_partition():
    payload = json.loads(V5_PATH.read_text(encoding="utf-8"))
    payload["registry_hash"] = ""
    with pytest.raises(ContractError):
        M2Data2FormalCuRegistry.model_validate(
            {
                **payload,
                "assumption_scale_artifact": {
                    **payload["assumption_scale_artifact"],
                    "P_itinerary": {
                        **payload["assumption_scale_artifact"]["P_itinerary"],
                        "empirical_train_positive_median": True,
                    },
                },
            }
        )
    with pytest.raises(ContractError):
        M2Data2FormalCuRegistry.model_validate(
            {
                **payload,
                "assumption_scale_artifact": {
                    **payload["assumption_scale_artifact"],
                    "P_service": {
                        **payload["assumption_scale_artifact"]["P_service"],
                        "scale": 104.88473684210527,
                    },
                },
            }
        )
    with pytest.raises(ContractError):
        M2Data2FormalCuRegistry.model_validate(
            {**payload, "formal_scope": [*payload["formal_scope"], "P_itinerary"]}
        )
    with pytest.raises(ContractError):
        M2Data2FormalCuRegistry.model_validate(
            {**payload, "final_test_access_count": 1}
        )


def test_v4_registry_file_is_retained_unchanged():
    digest = hashlib.sha256(V4_PATH.read_bytes()).hexdigest()
    assert digest == "e28ba89ef73fd5ba13ee67bd3aa16de8e097a64c133812c7ded341a9294c6e95"
    v4 = load_active_m2_cu_registry()
    assert v4.registry_id == "M2_DATA2_FORMAL_CU_V4"
    assert v4.scale("P_itinerary") == pytest.approx(9.882948210182091)
    design = load_active_passenger_consequence_design()
    assert design["version"] == "4.0.0"


def test_supersession_v3_records_draft_activation_and_no_new_final_test():
    payload = json.loads(SUPERSESSION_PATH.read_text(encoding="utf-8"))
    assert payload["registry_id"] == "PASSENGER_REFERENCE_SUPERSESSION_V3"
    assert payload["activation_status"] == "DRAFT_NOT_ACTIVATED"
    assert payload["supersedes"][0]["registry_id"] == "M2_DATA2_FORMAL_CU_V4"
    assert payload["supersedes"][0]["status"] == "SUPERSEDED_FOR_V2_CHAIN"
    assert payload["legacy_frozen_registry"]["status"] == "RETAINED_UNCHANGED"
    assert payload["m_cs_sensitivity"]["predefined_values"] == []
    assert payload["m_cs_sensitivity"]["status"] == (
        "NO_MANUSCRIPT_PREDEFINED_SENSITIVITY_VALUES"
    )
    assert payload["final_test_access_count"] == 0
    assert payload["paper_full_run"] is False
    assert payload["new_final_test_executed"] is False
    assert (
        payload["registry_payload_hash"] == load_active_v2_cu_registry().registry_hash
    )


def test_v5_design_declares_five_plus_two_partition_and_connection_share():
    payload = load_active_v2_passenger_consequence_design()
    assert payload["version"] == "5.0.0"
    assert payload["status"] == "HUMAN_APPROVED_PENDING_FREEZE"
    assert payload["activation_status"] == "DRAFT_NOT_ACTIVATED"
    partition = payload["cu_normalization_partition"]
    assert partition["principal_rule"] == "POSITIVE_TRAIN_PERIOD_MEDIAN"
    assert partition["event_rule"] == "ASSUMPTION_EVENT_NORMALIZATION"
    assert partition["event_scale"] == 1.0
    assert partition["event_components"] == ["P_itinerary", "P_service"]
    assert "connection_share" in payload["components"]["P_itinerary"]["formula"]
    assert payload["components"]["P_itinerary"]["itinerary_threshold_minutes"] == 45.0
    assert payload["components"]["P_service"]["service_threshold_minutes"] == 180.0
    assert payload["final_test_access_count"] == 0
    assert payload["paper_full_run"] is False
