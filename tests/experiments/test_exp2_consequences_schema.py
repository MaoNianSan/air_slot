"""Exp2 full-development consequences parquet schema contract (G-Tail chain)."""

import json
from pathlib import Path

import pyarrow.parquet as pq

from exp.exp2.global_development import CONSEQUENCE_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_MANIFEST = ROOT / "artifacts/experiments/exp2/full_development_scenarios_v1/M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIO_MANIFEST.json"
CONSEQUENCES = ROOT / "artifacts/experiments/exp2/full_development_v1/M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet"
METRICS = ROOT / "artifacts/experiments/exp2/full_development_v1/EXP2_FULL_DEVELOPMENT_METRICS.json"


def test_consequence_schema_is_fixed_double_columns():
    expected_names = [field.name for field in CONSEQUENCE_SCHEMA]
    assert "formal_five_component_value_cu" in expected_names
    assert "seven_component_value_cu" in expected_names
    assert all(field.type == "double" for field in CONSEQUENCE_SCHEMA if field.name.endswith("_value_cu"))


def test_materialized_consequences_match_fixed_schema():
    if not CONSEQUENCES.is_file():
        return
    actual = pq.ParquetFile(CONSEQUENCES).schema_arrow
    assert actual == CONSEQUENCE_SCHEMA


def test_consequence_row_count_matches_scenario_manifest():
    if not (CONSEQUENCES.is_file() and SCENARIO_MANIFEST.is_file()):
        return
    manifest = json.loads(SCENARIO_MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["row_count"]
    actual = pq.ParquetFile(CONSEQUENCES).metadata.num_rows
    assert actual == expected


def test_metrics_carry_assumption_grounded_tail_scores():
    if not METRICS.is_file():
        return
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    variants = payload.get("metrics", payload)
    for variant in ("EXP2A_POINT", "EXP2A_MARGINAL", "EXP2A_JOINT"):
        state_crps = variants[variant].get("state_crps", {})
        assert state_crps.get("support_status") == "ASSUMPTION_GROUNDED", variant
        assert state_crps.get("claim") == "ASSUMPTION_GROUNDED_NOT_EMPIRICAL_TAIL_CALIBRATION", variant
        assert "T-BASE" in state_crps.get("schemes", {}) and "T-PARAM" in state_crps.get("schemes", {}), variant


def test_metrics_carry_5_anchor_m4_ranking_contract():
    if not METRICS.is_file():
        return
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    ranking = payload.get("metrics", {}).get("M4_RANKING")
    assert ranking is not None
    assert ranking["support_status"] == "ASSUMPTION_GROUNDED"
    assert ranking["subset"] == "5-ANCHOR SUBSET"
    assert ranking["components"] == [
        "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating",
    ]
    assert ranking["units"] == "constructed_EUR"
    assert ranking["registry_hash"].startswith("sha256:")
    assert ranking["semantics"] == "CONSTRUCTED_INTERNAL_LOSS_NOT_CAUSAL_NOT_REGRET_NOT_OPTIMAL"
    assert ranking["excluded_components"] == ["P_itinerary", "P_service"]


def test_consequences_annotate_pending_components_monetary_not_anchored():
    if not CONSEQUENCES.is_file():
        return
    reader = pq.ParquetFile(CONSEQUENCES)
    seen = 0
    for row_group in range(min(reader.num_row_groups, 3)):
        for row in reader.read_row_group(row_group).to_pylist():
            components = json.loads(row["components_json"])
            for item in components:
                if item["component_id"] in ("P_itinerary", "P_service"):
                    assert item.get("monetary_status") == "NOT_ANCHORED", item
                    seen += 1
    assert seen > 0
