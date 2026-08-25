"""OUTPUT_CONTRACT_20260823 acceptance tests (section 7)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from exp.common.result_schema import MetricLevel, SupportStatus
from exp.exp1.full_state_metrics import (
    DELAY_EVENT_REASON,
    M1_PREDICTIVE_REASON,
    M4_GATE_REASON,
    compute_full_state_metrics,
)
from exp.exp1.run import (
    ALLOWED_MANIFEST_VARIANTS,
    OFFICIAL_VARIANTS,
    REQUIRED_OUTPUTS,
    _cohort_metric_rows,
    validate as validate_exp1,
)
from exp.exp3.run import _metric_rows_from_exp3_metrics
from exp.reporting.output_contract import (
    CI_UNAVAILABLE,
    METRIC_CSV_COLUMNS,
    METRIC_REGISTRY,
    N_EPISODES_UNAVAILABLE,
    build_leakage_audit,
    build_parity_audit,
    build_split_audit,
    metric_contract,
    require_output_safety,
    rows_from_global_metrics,
    validate_artifacts,
    validate_metric_row,
    write_experiment_artifacts,
    write_from_global_metrics,
)
from model.common.errors import ContractError
from model.common.identity import content_id

ROOT = Path(__file__).resolve().parents[2]

VARIANTS = ("EXP1A_NO_DIRECT_REUSE", "EXP1A_FULL", "EXP1B_CURRENT", "EXP1B_ADAPTIVE_HISTORY")


def _metric_rows():
    return (
        {
            "experiment": "EXP1", "variant": "EXP1A_FULL", "metric_id": "CRPS_PRIMITIVE_TARGET",
            "value": 21.3, "support": "SUPPORTED", "estimate": 21.3,
            "ci_lower": 20.1, "ci_upper": 22.5, "n_episodes": 128,
        },
        {
            "experiment": "EXP1", "variant": "EXP1A_FULL", "metric_id": "TOP1_ACTION_DISAGREEMENT",
            "value": None, "support": "NOT_RUN",
            "reason": "NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE",
        },
        {
            "experiment": "EXP1", "variant": "EXP1A_NO_DIRECT_REUSE",
            "metric_id": "CRPS_PRIMITIVE_TARGET", "value": 22.0, "support": "SUPPORTED",
            "estimate": 22.0, "ci_lower": 20.8, "ci_upper": 23.2, "n_episodes": 128,
        },
    )


def _definitions():
    return {
        variant: {
            "variant_id": variant, "subexperiment": variant[:5],
            "changed_factor": variant, "fixed_factor": ("cohort", "seed"),
            "claim_scope": "INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        }
        for variant in VARIANTS
    }


def _cohort():
    return {
        "dataset_id": "DATA2", "split": "DEVELOPMENT", "episode_count": 128,
        "node_count": 1769, "scenario_count_per_node": 250, "seed": 0,
    }


def _write_bundle(tmp_path: Path, name: str = "run") -> Path:
    output = tmp_path / name
    write_experiment_artifacts(
        experiment_id="EXP1", output_root=output, metric_rows=_metric_rows(),
        cohort=_cohort(), variants=VARIANTS, variant_definitions=_definitions(),
        frozen_hashes={"model_hash": "sha256:" + "1" * 64},
        config_hash="sha256:" + "2" * 64,
        interpretation="Development-only Exp1 evidence.",
        claim_scope="INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        limitations=("Decision metrics stay NOT_RUN at the M4 gate.",),
        omega_insight="Operational action value requires a frozen mapping.",
        condition_of={variant: variant for variant in VARIANTS},
        split_rows=(),
        leakage_rows=(),
        root=ROOT,
    )
    return output


def test_artifact_set_schema_and_hash_roundtrip(tmp_path):
    output = _write_bundle(tmp_path)
    expected = (
        "exp1_protocol_manifest.json", "exp1_variant_manifest.json",
        "exp1_split_audit.json", "exp1_leakage_audit.json", "exp1_parity_audit.json",
        "exp1_metrics.csv", "exp1_summary.json", "exp1_main_table.csv",
        "exp1_main_table.tex", "exp1_interpretation.md",
    )
    for name in expected:
        assert (output / name).is_file(), name
    result = validate_artifacts("EXP1", output)
    assert result["status"] == "OUTPUT_CONTRACT_ARTIFACTS_VALIDATED"
    summary = json.loads((output / "exp1_summary.json").read_text(encoding="utf-8"))
    assert summary["schema_version"] == "AIR_SLOT_EXP_SUMMARY_V1"
    assert summary["experiment_id"] == "EXP1"
    assert summary["paper_result"] is False
    assert summary["safety"] == {
        "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
        "AUTHORITATIVE_RANKING": False,
    }
    assert any(item["support_status"] == "NOT_RUN" for item in summary["headline"])
    with (output / "exp1_metrics.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert tuple(header) == METRIC_CSV_COLUMNS
    tex = (output / "exp1_main_table.tex").read_text(encoding="utf-8")
    assert "\\toprule" in tex and "\\midrule" in tex and "\\bottomrule" in tex
    assert "\\caption{" in tex


def test_determinism_artifact_hash_and_bootstrap(tmp_path):
    first = _write_bundle(tmp_path, "run_a")
    second = _write_bundle(tmp_path, "run_b")
    for name in ("exp1_protocol_manifest.json", "exp1_variant_manifest.json", "exp1_summary.json"):
        left = json.loads((first / name).read_text(encoding="utf-8"))["artifact_hash"]
        right = json.loads((second / name).read_text(encoding="utf-8"))["artifact_hash"]
        assert left == right, name
    scenario_rows = []
    label_rows = []
    for episode in ("E1", "E2"):
        for node in ("N1", "N2"):
            observed = {"T_IB_REMAINING_HAZARD": 20.0, "D_OB": 10.0, "D_TX": 8.0}
            label_rows.append({
                "episode_id": episode, "decision_node_id": node,
                "target_name": "T_IB_REMAINING_HAZARD", "active": True, "value": 20.0,
            })
            label_rows.append({
                "episode_id": episode, "decision_node_id": node,
                "target_name": "D_OB", "active": True, "value": 10.0,
            })
            label_rows.append({
                "episode_id": episode, "decision_node_id": node,
                "target_name": "D_TX", "active": True, "value": 8.0,
            })
            for scenario in range(4):
                scenario_rows.append({
                    "episode_id": episode, "decision_node_id": node,
                    "scenario_id": scenario, "T_IB_A00": 15.0 + scenario,
                    "D_OB": 9.0 + scenario, "D_TX": 7.0 + scenario,
                })
    first_run = compute_full_state_metrics(
        scenario_rows=scenario_rows, label_rows=label_rows, variants=("EXP1A_FULL",), seed=7,
    )
    second_run = compute_full_state_metrics(
        scenario_rows=scenario_rows, label_rows=label_rows, variants=("EXP1A_FULL",), seed=7,
    )
    crps = first_run["EXP1A_FULL"]["CRPS_PRIMITIVE_TARGET"]
    assert crps.support_status is SupportStatus.SUPPORTED
    assert crps.value is not None
    assert crps.metadata["bootstrap"]["replicates"] == 2000
    assert crps.metadata["bootstrap"]["seed"] == 7
    assert second_run["EXP1A_FULL"]["CRPS_PRIMITIVE_TARGET"].value == crps.value


def test_split_and_leakage_audits_detect_violations():
    clean = [{"episode_id": "E1", "split": "DEVELOPMENT", "information_cutoff": "10:00", "decision_time": "10:05"}]
    assert build_split_audit(clean)["verdict"] == "PASS"
    leaky = [{"episode_id": "E1", "split": "DEVELOPMENT", "information_cutoff": "10:10", "decision_time": "10:05"}]
    audit = build_split_audit(leaky)
    assert audit["verdict"] == "FAIL"
    assert audit["checks"]["no_future_information"] is False
    cross_split = [
        {"episode_id": "E1", "split": "DEVELOPMENT"},
        {"episode_id": "E1", "split": "TEST"},
    ]
    assert build_split_audit(cross_split)["verdict"] == "FAIL"
    assert build_leakage_audit([{"role": "EVALUATION", "realized_outcome": 1.0}])["verdict"] == "PASS"
    leaky_outcome = build_leakage_audit(
        [{"role": "INFERENCE", "contains_labels": True}]
    )
    assert leaky_outcome["verdict"] == "FAIL"
    assert leaky_outcome["checks"]["realized_outcome_evaluation_only"] is False


def test_parity_audit_defaults_and_overrides():
    exp2 = build_parity_audit("EXP2", {})
    assert exp2["checks"]["exp2a_marginal_weight_parity"] is True
    assert exp2["checks"]["exp2b_coarse_no_hidden_7comp_access"] is True
    exp4 = build_parity_audit("EXP4", {})
    assert exp4["checks"]["exp4d_shared_recomputed_output_parity"] is True
    overridden = build_parity_audit("EXP4", {"exp4d_shared_recomputed_output_parity": False})
    assert overridden["verdict"] == "FAIL"


def test_safety_refuses_nonzero_final_test_and_paper_full():
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_FINAL_TEST_ACCESS_NONZERO"):
        require_output_safety({"safety": {"FINAL_TEST_ACCESS_COUNT": 1, "PAPER_FULL_RUN": False}})
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_PAPER_FULL_FORBIDDEN"):
        require_output_safety({"safety": {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": True}})
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_AUTHORITATIVE_RANKING_FORBIDDEN"):
        require_output_safety({"safety": {"AUTHORITATIVE_RANKING": True}})


def test_metric_row_validation_rules():
    base = {"experiment": "EXP1", "variant": "EXP1A_FULL", "metric_id": "CRPS_PRIMITIVE_TARGET"}
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_VALUE_FORBIDDEN"):
        validate_metric_row({**base, "value": 1.0, "support": "NOT_RUN"})
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_VALUE_REQUIRED"):
        validate_metric_row({**base, "value": None, "support": "SUPPORTED"})
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_REASON_REQUIRED"):
        validate_metric_row({**base, "value": None, "support": "NOT_RUN"})
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_METRIC_UNREGISTERED"):
        validate_metric_row({**base, "metric_id": "INVENTED_METRIC", "value": None, "support": "NOT_RUN", "reason": "x"})


def test_registry_covers_contract_section3():
    required = {
        "EXP1": ("STATE_REPRESENTATION_DIFFERENCE", "CRPS_PRIMITIVE_TARGET", "TOP1_ACTION_DISAGREEMENT", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", "BRIER_PRINCIPAL_DELAY_EVENT", "CALIBRATION", "COVERAGE"),
        "EXP2": ("CRPS", "BRIER", "CALIBRATION", "COVERAGE", "VARIOGRAM_SCORE", "MARGINAL_WEIGHT_CHECK", "TOP1_ACTION_DISAGREEMENT", "COMPLETE_REFERENCE_J_DIAGNOSTIC", "ACTION_FAMILY_COMPOSITION"),
        "EXP3": ("ONE_SHOT_ANCHOR", "RECOMMENDATION_EXECUTABLE_RATE", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK", "TOP1_ACTION_AGREEMENT", "STATE_VINTAGE_COVERAGE"),
        "EXP4": ("MAE_MINUTES", "CRPS", "LEAD_TIME_CONTRACT", "FORMAL_RECOMMENDATION_AVAILABILITY", "DATA1_DATA2_SEMANTIC_GATE", "E2E_P50_SECONDS", "E2E_P95_SECONDS", "E2E_P99_SECONDS", "WITHIN_60S", "WITHIN_120S", "WITHIN_300S"),
    }
    for experiment_id, metric_ids in required.items():
        for metric_id in metric_ids:
            assert metric_contract(experiment_id, metric_id) is not None, f"{experiment_id}:{metric_id}"


def test_exp1_state_metrics_gates_are_explicit():
    scenario_rows = [
        {"episode_id": "E1", "decision_node_id": "N1", "scenario_id": 0,
         "T_IB_A00": 10.0, "D_OB": 5.0, "D_TX": 4.0},
        {"episode_id": "E1", "decision_node_id": "N1", "scenario_id": 1,
         "T_IB_A00": 12.0, "D_OB": 6.0, "D_TX": 5.0},
    ]
    label_rows = [
        {"episode_id": "E1", "decision_node_id": "N1", "target_name": "T_IB_REMAINING_HAZARD", "active": True, "value": 11.0},
        {"episode_id": "E1", "decision_node_id": "N1", "target_name": "D_OB", "active": True, "value": 5.5},
        {"episode_id": "E1", "decision_node_id": "N1", "target_name": "D_TX", "active": True, "value": 4.5},
    ]
    observations = compute_full_state_metrics(
        scenario_rows=scenario_rows, label_rows=label_rows,
        variants=("EXP1A_FULL",), seed=0,
    )
    metrics = observations["EXP1A_FULL"]
    assert metrics["CRPS_PRIMITIVE_TARGET"].support_status is SupportStatus.SUPPORTED
    assert metrics["STATE_REPRESENTATION_DIFFERENCE"].metadata["reason"] == M1_PREDICTIVE_REASON
    assert metrics["BRIER_PRINCIPAL_DELAY_EVENT"].metadata["reason"] == DELAY_EVENT_REASON
    assert metrics["TOP1_ACTION_DISAGREEMENT"].metadata["reason"] == M4_GATE_REASON
    assert metrics["EXPOST_MODEL_IMPLIED_RESIDUAL_RISK"].metadata["reason"] == M4_GATE_REASON


def test_exp1_run_variant_contract_rejects_legacy_tuple(tmp_path):
    import shutil

    assert OFFICIAL_VARIANTS == (
        "EXP1A_NO_DIRECT_REUSE", "EXP1A_FULL", "EXP1B_CURRENT", "EXP1B_ADAPTIVE_HISTORY",
    )
    assert OFFICIAL_VARIANTS in ALLOWED_MANIFEST_VARIANTS
    output_root = ROOT / "artifacts/experiment/exp1_full_development"
    manifest_path = output_root / "EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    if manifest_path.is_file():
        result = validate_exp1(ROOT, output_root)
        assert result["status"] == "EXP1_OFFICIAL_READY"
        # A manifest carrying a legacy (non-official) variant tuple must be rejected.
        legacy_root = ROOT / "artifacts/diagnostics/test_tmp_exp1_legacy_variants"
        legacy_root.mkdir(parents=True, exist_ok=True)
        try:
            for name in (manifest_path.name, *REQUIRED_OUTPUTS):
                shutil.copy2(output_root / name, legacy_root / name)
            legacy_manifest_path = legacy_root / manifest_path.name
            legacy_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
            legacy_manifest["variants"] = ["EXP1A_POINT", "EXP1A_MARGINAL", "EXP1A_JOINT"]
            legacy_manifest_path.write_text(json.dumps(legacy_manifest), encoding="utf-8")
            with pytest.raises(ContractError, match="EXP1_OFFICIAL_VARIANTS_INVALID"):
                validate_exp1(ROOT, legacy_root)
        finally:
            shutil.rmtree(legacy_root, ignore_errors=True)


def test_rows_from_global_metrics_adapter():
    payload = {
        "schema_version": "EXP2_FULL_DEVELOPMENT_METRICS_V1",
        "metrics": {
            "EXP2A_POINT": {
                "tail_aware_brier": 0.25,
                "supported_episode_count": 127,
                "state_crps": {
                    "value": None, "support_status": "NOT_RUN",
                    "reason": "OVERFLOW_CLASS_HAS_NO_SCALAR_MAGNITUDE",
                },
            },
            "EXP2B_SCALAR": {"support_status": "NOT_RUN", "reason": "SEVEN_COMPONENT_AGGREGATE_UNRESOLVED"},
        },
    }
    rows = rows_from_global_metrics(payload)
    assert any(
        row["metric_id"] == "BRIER" and row["value"] == 0.25
        and row["n_episodes"] == 127
        for row in rows
    )
    assert any(row["metric_id"] == "CRPS" and row["support"] == "NOT_RUN" for row in rows)
    assert any(row["metric_id"] == "TOP1_ACTION_DISAGREEMENT" and row["support"] == "NOT_RUN" for row in rows)


def test_main_table_placeholders_and_episodes(tmp_path):
    rows = (
        {
            "experiment": "EXP1", "variant": "EXP1A_FULL", "metric_id": "CRPS_PRIMITIVE_TARGET",
            "value": 21.3, "support": "SUPPORTED", "estimate": 21.3,
            "ci_lower": None, "ci_upper": None, "n_episodes": 127,
        },
        {
            "experiment": "EXP1", "variant": "EXP1A_NO_DIRECT_REUSE",
            "metric_id": "CRPS_PRIMITIVE_TARGET", "value": 22.0, "support": "SUPPORTED",
            "estimate": 22.0, "ci_lower": 20.8, "ci_upper": 23.2, "n_episodes": 128,
        },
    )
    output = tmp_path / "placeholders"
    write_experiment_artifacts(
        experiment_id="EXP1", output_root=output, metric_rows=rows,
        cohort=_cohort(), variants=VARIANTS, variant_definitions=_definitions(),
        frozen_hashes={"model_hash": "sha256:" + "1" * 64},
        config_hash="sha256:" + "2" * 64,
        interpretation="Development-only Exp1 evidence.",
        claim_scope="INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        limitations=("Decision metrics stay NOT_RUN at the M4 gate.",),
        omega_insight="Operational action value requires a frozen mapping.",
        condition_of={variant: variant for variant in VARIANTS},
        split_rows=(), leakage_rows=(), root=ROOT,
    )
    lines = (output / "exp1_main_table.csv").read_text(encoding="utf-8").splitlines()
    first = lines[1].split(",")
    assert first[4] == CI_UNAVAILABLE
    assert first[5] == "127"
    second = lines[2].split(",")
    assert second[4] == "20.8 - 23.2"
    assert second[5] == "128"
    assert validate_artifacts("EXP1", output)["status"] == "OUTPUT_CONTRACT_ARTIFACTS_VALIDATED"


def test_main_table_empty_reason_guard(tmp_path):
    rows = (
        {
            "experiment": "EXP1", "variant": "EXP1A_FULL", "metric_id": "CRPS_PRIMITIVE_TARGET",
            "value": None, "support": "NOT_RUN",
            "reason": "NO_SUPPORTED_PRIMITIVE_SAMPLES_OR_LABELS",
        },
    )
    output = tmp_path / "empty"
    write_experiment_artifacts(
        experiment_id="EXP1", output_root=output, metric_rows=rows,
        cohort=_cohort(), variants=VARIANTS, variant_definitions=_definitions(),
        frozen_hashes={"model_hash": "sha256:" + "1" * 64},
        config_hash="sha256:" + "2" * 64,
        interpretation="Development-only Exp1 evidence.",
        claim_scope="INFORMATION_ROLE_NECESSITY_AND_HISTORY_DEPENDENCE_ONLY",
        limitations=("Decision metrics stay NOT_RUN at the M4 gate.",),
        omega_insight="Operational action value requires a frozen mapping.",
        condition_of={variant: variant for variant in VARIANTS},
        split_rows=(), leakage_rows=(), root=ROOT,
    )
    summary_path = output / "exp1_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["empty_reason"] == "MAIN_TABLE_EMPTY_ALL_METRIC_VALUES_NOT_RUN_OR_BLOCKED"
    assert validate_artifacts("EXP1", output)["status"] == "OUTPUT_CONTRACT_ARTIFACTS_VALIDATED"
    # An empty table whose summary drops the reason must fail validation.
    summary.pop("empty_reason")
    summary.pop("artifact_hash", None)
    summary["artifact_hash"] = content_id(summary)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="OUTPUT_CONTRACT_MAIN_TABLE_EMPTY_WITHOUT_REASON"):
        validate_artifacts("EXP1", output)


def test_exp1_cohort_rows_validate():
    rows = _cohort_metric_rows(
        {"episode_count": 128, "node_count": 1769},
        {"scenario_count_per_node": 250, "row_count": 442250},
    )
    by_id = {row["metric_id"]: row for row in rows}
    assert by_id["COHORT_EPISODES"]["value"] == 128
    assert by_id["COHORT_NODES"]["value"] == 1769
    assert by_id["SCENARIOS_PER_NODE"]["value"] == 250
    assert by_id["SCENARIO_COVERAGE_RATE"]["value"] == 1.0
    for row in rows:
        validate_metric_row(row)


def test_exp3_metric_rows_builder(tmp_path):
    table = pa.table({
        "conditional_residual_risk": pa.array([10.0, 20.0, 30.0], type=pa.float64()),
    })
    parquet_path = tmp_path / "risk.parquet"
    pq.write_table(table, parquet_path)
    payload = {
        "episode_count": 128,
        "finite_support_rate_mean": 0.9,
        "conditional_top1_response_sensitivity_agreement": {"LOW": 1, "HIGH": 1},
        "global_constructed_eur_scale_sensitivity": {
            "ranking_invariance": "MATHEMATICALLY_INVARIANT_UNDER_COMMON_POSITIVE_SCALE",
            "scales": ["LOW", "BASE", "HIGH"],
        },
        "formal_complete_chain": {"support_status": "NOT_RUN", "reason": "GATED"},
    }
    rows = _metric_rows_from_exp3_metrics(payload, parquet_path)
    by_key = {(row["metric_id"], row.get("condition")): row for row in rows}
    assert by_key[("FINITE_SUPPORT_RATE", "DEVELOPMENT")]["value"] == 0.9
    assert by_key[("CONDITIONAL_TOP1_RESPONSE_AGREEMENT", "LOW")]["value"] == 1
    assert by_key[("CONDITIONAL_TOP1_RESPONSE_AGREEMENT", "HIGH")]["value"] == 1
    assert by_key[("GLOBAL_CONSTRUCTED_EUR_SCALE_INVARIANCE", "SCALES=3")]["value"] == 1.0
    assert by_key[("PER_ACTION_CONDITIONAL_RISK_MEAN", "FINITE_SUPPORT_ROWS")]["value"] == 20.0
    assert by_key[("FORMAL_COMPLETE_CHAIN", "DEVELOPMENT")]["value"] is None
    assert by_key[("ONE_SHOT_ANCHOR", "DEVELOPMENT")]["reason"].startswith("EXP3_VARIANTS_DEFERRED_OPTIONAL")
    for row in rows:
        validate_metric_row(row)


def _exp4_metrics_payload() -> dict:
    return {
        "schema_version": "EXP4_FULL_DEVELOPMENT_METRICS_V1",
        "data2": {
            "episode_count": 128, "node_count": 1769, "split": "DEVELOPMENT",
            "role": "MAIN_DEVELOPMENT_EVALUATION",
            "baselines": {
                "HISTORICAL": {
                    "mae_minutes": 8.68, "crps_minutes": 33.21,
                    "crps_scope": "T_IB_FINITE_SUPPORT_COMPARISON_SCOPE",
                    "support_status": "SUPPORTED",
                },
                "STATE_AWARE_H32": {
                    "mae_minutes": 7.13, "crps_minutes": 21.12,
                    "support_status": "SUPPORTED",
                },
            },
        },
        "data1": {
            "role": "BOUNDED_EXTERNAL_APPLICABILITY_SMOKE_ONLY",
            "pooling_with_data2": False,
            "predictive_metrics": {
                "support_status": "NOT_RUN",
                "reason": "DATA1_M1_PREDICTIVE_LABEL_PATH_UNAVAILABLE_BY_CONTRACT",
            },
        },
        "safety": {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False},
        "status": "DATA2_BASELINES_COMPLETE_DATA1_BOUNDED_PASS",
        "artifact_hash": "sha256:" + "3" * 64,
    }


def test_exp4_global_metrics_adapter_and_artifact_set(tmp_path):
    payload = _exp4_metrics_payload()
    rows = rows_from_global_metrics(payload)
    by_key = {(row["variant"], row["metric_id"]): row for row in rows}
    assert by_key[("HISTORICAL", "MAE_MINUTES")]["value"] == 8.68
    assert by_key[("HISTORICAL", "CRPS")]["value"] == 33.21
    assert by_key[("STATE_AWARE_H32", "CRPS")]["reason"] is None
    assert by_key[("HISTORICAL", "LEAD_TIME_CONTRACT")]["value"] is True
    assert by_key[("HISTORICAL", "FORMAL_RECOMMENDATION_AVAILABILITY")]["support"] == "NOT_RUN"
    assert by_key[("HISTORICAL", "E2E_P95_SECONDS")]["reason"] == "FAST_CONTRACT_RUN_NO_PIPELINE_TIMINGS"
    assert by_key[("DATA1_BOUNDED_SMOKE", "DATA1_DATA2_SEMANTIC_GATE")]["support"] == "NOT_RUN"
    for row in rows:
        validate_metric_row(row)

    output = tmp_path / "exp4"
    metrics_path = output / "EXP4_FULL_DEVELOPMENT_METRICS.json"
    metrics_path.parent.mkdir(parents=True)
    metrics_path.write_text(json.dumps(payload), encoding="utf-8")
    write_from_global_metrics(
        experiment_id="EXP4", output_root=output, metrics_path=metrics_path,
        frozen_hashes={"model_hash": "sha256:" + "1" * 64},
        root=ROOT, scenario_count=250,
    )
    result = validate_artifacts("EXP4", output)
    assert result["status"] == "OUTPUT_CONTRACT_ARTIFACTS_VALIDATED"
    summary = json.loads((output / "exp4_summary.json").read_text(encoding="utf-8"))
    headline_ids = {(item["variant_id"], item["metric_id"]) for item in summary["headline"]}
    assert ("HISTORICAL", "MAE_MINUTES") in headline_ids
    assert ("HISTORICAL", "FORMAL_RECOMMENDATION_AVAILABILITY") in headline_ids
    main = (output / "exp4_main_table.csv").read_text(encoding="utf-8")
    assert "HISTORICAL,MAE_MINUTES" in main
    assert "DATA1_BOUNDED_SMOKE" not in main
