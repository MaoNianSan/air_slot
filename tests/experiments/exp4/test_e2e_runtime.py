"""Exp4D development E2E runtime repeats contract (operational adequacy)."""

import json
from pathlib import Path

from exp.exp4.e2e_runtime import run

ROOT = Path(__file__).resolve().parents[3]


def test_e2e_runtime_repeats_emit_adequacy_metrics(tmp_path: Path):
    outputs = run(root=ROOT, repeats=2, output_root=tmp_path)
    metrics = json.loads((tmp_path / "EXP4_E2E_RUNTIME_METRICS.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "COMPLETE_ENGINEERING_ADEQUACY_DIAGNOSTIC"
    assert metrics["role"] == "OPERATIONAL_ADEQUACY_NOT_SCIENTIFIC_EVIDENCE"
    stats = metrics["e2e_percentiles_seconds"]
    assert stats["p50"] is not None and stats["p50"] <= stats["p95"] <= stats["p99"]
    assert stats["p95"] < 300
    for budget in (60, 120, 300):
        rate = metrics["within_budget_rates"][f"WITHIN_{budget}S"]
        assert 0.0 <= rate <= 1.0
    assert set(metrics["stage_percentiles_seconds"]) == {
        "pre_state_load", "m1_scenario_read", "m2_consequence_read",
        "m3_action_risk", "ranking_output_serialization",
    }
    assert metrics["ranking_authority"] == "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL"
    assert metrics["safety"] == {
        "AUTHORITATIVE_RANKING": False,
        "DEVELOPMENT_TUNING": False,
        "FINAL_TEST_ACCESS_COUNT": 0,
        "PAPER_FULL_RUN": False,
        "SCIENTIFIC_CLAIM": False,
    }
    repeats_payload = json.loads((tmp_path / "EXP4_E2E_RUNTIME_REPEATS.json").read_text(encoding="utf-8"))
    assert len(repeats_payload["repeats"]) == 2
    for row in repeats_payload["repeats"]:
        assert row["ranking_rows"] == 23 * 3
    manifest = json.loads((tmp_path / "EXP4_E2E_RUNTIME_EXECUTION_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["role"] == "OPERATIONAL_ADEQUACY_NOT_SCIENTIFIC_EVIDENCE"
    assert manifest["artifact_hashes"]["metrics"] == metrics["artifact_hash"]
    assert manifest["safety"]["FINAL_TEST_ACCESS_COUNT"] == 0
    assert manifest["safety"]["PAPER_FULL_RUN"] is False
    assert outputs["manifest"].is_file() and outputs["table"].is_file()
