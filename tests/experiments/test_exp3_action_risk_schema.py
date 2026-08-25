"""Exp3 full-development action-risk parquet schema contract (A-SET chain)."""

import json
from pathlib import Path

import pyarrow.parquet as pq

from exp.exp3.global_development import ACTION_RISK_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
ACTION_RISK = ROOT / "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
METRICS = ROOT / "artifacts/experiments/exp3/full_development_v1/EXP3_FULL_DEVELOPMENT_METRICS.json"


def test_action_risk_schema_has_nullable_double_conditional_columns():
    names = {field.name: field for field in ACTION_RISK_SCHEMA}
    for column in (
        "conditional_expected_constructed_eur", "conditional_constructed_eur_variance",
        "conditional_constructed_eur_var_alpha", "conditional_constructed_eur_cvar_alpha",
        "conditional_residual_risk", "conditional_diagnostic_rank",
    ):
        assert names[column].type in ("double", "int64"), column
    for column in ("p_itinerary_event_count", "p_service_event_count"):
        assert names[column].type == "double", column
    assert names["pending_monetary_event_status"].type == "string"


def test_materialized_action_risk_matches_fixed_schema():
    if not ACTION_RISK.is_file():
        return
    actual = pq.ParquetFile(ACTION_RISK).schema_arrow
    assert actual == ACTION_RISK_SCHEMA


def test_action_risk_row_count():
    if not ACTION_RISK.is_file():
        return
    rows = pq.ParquetFile(ACTION_RISK).metadata.num_rows
    assert rows == 1769 * 23 * 3  # nodes x actions x LOW/BASE/HIGH


def test_metrics_carry_conditional_diagnostic_scope():
    if not METRICS.is_file():
        return
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    assert payload["status"] == "COMPLETE_WITH_CONDITIONAL_5_ANCHOR_RANKING_AND_FORMAL_NOT_RUN"
    assert payload["formal_complete_chain"]["authoritative_ranking"] is False
    assert payload["formal_complete_chain"]["support_status"] == "NOT_RUN"
    assert payload["safety"]["AUTHORITATIVE_RANKING"] is False
    assert payload["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert payload["safety"]["PAPER_FULL_RUN"] is False
    definition = payload["ranking_definition"]
    assert definition["subset"] == "5-ANCHOR SUBSET"
    assert definition["components"] == [
        "F_continuity", "F_execution", "F_propagation", "P_time", "R_operating",
    ]
    assert definition["units"] == "constructed_EUR"
    assert definition["registry_hash"].startswith("sha256:")
    assert definition["semantics"] == "CONSTRUCTED_INTERNAL_LOSS_NOT_CAUSAL_NOT_REGRET_NOT_OPTIMAL"
    assert definition["top1_level"] == "ASSUMPTION_GROUNDED"
    assert definition["excluded_components"] == ["P_itinerary", "P_service"]


def test_action_risk_rows_annotate_pending_monetary_event_status():
    if not ACTION_RISK.is_file():
        return
    reader = pq.ParquetFile(ACTION_RISK)
    assert reader.schema_arrow == ACTION_RISK_SCHEMA
    for row_group in range(min(reader.num_row_groups, 3)):
        for row in reader.read_row_group(row_group).to_pylist():
            assert row["pending_monetary_event_status"] == "EVENT_COUNTS_ONLY_MONETARY_NOT_ANCHORED"
