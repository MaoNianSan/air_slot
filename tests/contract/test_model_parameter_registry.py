import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "MODEL_PARAMETER_REGISTRY.json"

SCIENTIFIC_STATUSES = {"FROZEN", "UNRESOLVED", "SUPERSEDED"}
IMPLEMENTATION_STATUSES = {
    "MATCH",
    "MISMATCH",
    "NOT_MATERIALIZED",
    "NOT_APPLICABLE",
}


def _entries():
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return payload, {item["parameter_id"]: item for item in payload["entries"]}


def test_parameter_registry_separates_scientific_and_implementation_status():
    payload, entries = _entries()
    assert payload["registry_id"] == "AIR_SLOT_MODEL_PARAMETER_REGISTRY"
    assert len(entries) == len(payload["entries"])
    assert all(
        item["scientific_status"] in SCIENTIFIC_STATUSES
        for item in entries.values()
    )
    assert all(
        item["implementation_status"] in IMPLEMENTATION_STATUSES
        for item in entries.values()
    )


def test_frozen_active_baseline_has_no_implementation_mismatch():
    _, entries = _entries()
    frozen = [
        item for item in entries.values() if item["scientific_status"] == "FROZEN"
    ]
    assert frozen
    assert all(item["implementation_status"] == "MATCH" for item in frozen)
    assert entries["M1_PRIMARY_HIDDEN_SIZE"]["value"] == 8
    assert entries["M1_SENSITIVITY_HIDDEN_SIZE"]["value"] == 16
    assert entries["M1_SCENARIO_COUNT"]["value"] == 64
    assert entries["M4_MONETARY_MAPPING"]["value"]["system"] == "RMB"
    assert entries["M4_RISK_POLICY"]["value"]["lambda"] == 0.25
    assert entries["M4_RISK_POLICY"]["value"]["alpha"] == 0.90
    assert entries["M1_FORECAST_HORIZONS_MINUTES"]["value"] == [0, 15, 60]
    assert entries["EVALUATION_LEAD_TIMES_MINUTES"]["value"] == [0,30,60,120,180,240,300,360,420,480]
    assert entries["M1_DELAY_THRESHOLDS_MINUTES"]["value"] == [15,30,60]
    assert entries["M2_DOWNSTREAM_EXPOSURE_HORIZON_MINUTES"]["value"] == 360
    assert entries["A21_CURRENT_FACTUAL_SEMANTICS"]["scientific_status"] == "FROZEN"
    assert entries["A71_A72_CURRENT_AUTHORITY_SEMANTICS"]["value"].endswith("UNKNOWN")
    assert entries["M4_CURRENT_SELECTION_STATE"]["implementation_status"] == "MATCH"


def test_superseded_values_are_not_active_authority():
    _, entries = _entries()
    superseded = [
        item
        for item in entries.values()
        if item["scientific_status"] == "SUPERSEDED"
    ]
    assert superseded
    assert all(
        item["implementation_status"] == "NOT_APPLICABLE"
        for item in superseded
    )
