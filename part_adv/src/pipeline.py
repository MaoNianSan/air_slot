from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .shared_contracts import RANKING_CONTRACT_VERSION, RANKING_DEPTHS

from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    M2_CONFIGS,
    MODELS,
    ParallelPlan,
    SENSITIVITY_TARGET_COLUMN,
    _RunTelemetry,
    _log,
    _part_adv_figures,
    _write_df,
    _write_json,
    parallel_metadata,
    resolve_parallel_plan,
    sha256_file,
    stable_hash,
    task_seed_hash,
    thread_limit_environment,
    validate_m1_target_mapping,
)
from .pipeline_inputs import _formal_quantiles, _load, _upstream
from .pipeline_m1 import _m1
from .pipeline_propagation import _benchmark, _m2_sensitivity, _m4_variants, _propagate
from .pipeline_publication import _registry, report, validate


def _run_pipeline(
    mode: str,
    progress: str,
    cfg: dict[str, Any],
    cohort: pd.DataFrame,
    upstream: dict[str, Any],
    run_id: str,
    telemetry: _RunTelemetry,
    started: pd.Timestamp,
    plan: ParallelPlan,
) -> dict[str, Any]:
    output = cfg["output"]
    log = output / "logs" / "run.log"
    _write_df(cohort, output / "m4_common_support_cohort.parquet")
    _write_json(upstream, output / "common_support_cohort.json")

    _log("[1/4] M1 HIST/QRF/NGB/PROP/POINT_OOF on unified evaluation index", progress, log)
    predictions, samples, m1_metrics, frame = _m1(cfg, cohort, telemetry)
    _write_df(frame, output / "input_adapter" / "m1_model_frame.parquet")
    _write_df(predictions, output / "m1" / "m1_predictions.parquet")
    _write_df(samples, output / "m1" / "m1_predictive_samples.parquet")
    _write_df(m1_metrics, output / "m1" / "m1_model_metrics.parquet")
    benchmark = _benchmark(cfg, cohort)
    _write_df(benchmark, output / "benchmark_action_scores.parquet")
    (
        downstream,
        propagation,
        selection_path,
        pairwise,
        propagated_costs,
        ranking_prefixes,
        ranking_agreement,
    ) = _propagate(
        cfg, predictions, samples, cohort, benchmark
    )
    _write_df(downstream, output / "m1" / "m1_downstream_results.parquet")
    _write_df(propagation, output / "m1" / "m1_downstream_propagation.parquet")
    _write_df(selection_path, output / "m1" / "m4_selection_path.parquet")
    _write_df(pairwise, output / "m1" / "m1_pairwise_decomposition.parquet")
    _write_df(propagated_costs, output / "m1" / "m1_propagated_cost_samples.parquet")
    _write_df(
        ranking_prefixes, output / "m1" / "ranking_prefixes_1235.parquet"
    )
    _write_df(
        ranking_agreement,
        output / "m1" / "recommendation_agreement_1235.parquet",
    )
    agreement_summary = ranking_agreement.groupby(
        ["model_id", "ranking_k"], as_index=False, observed=True
    ).agg(
        agreement_rate=("agreement", "mean"),
        set_disagreement_rate=("set_disagreement", "mean"),
        order_only_disagreement_rate=("order_only_disagreement", "mean"),
        overlap_rate=("overlap_rate", "mean"),
        full_k_support_rate=("full_k_support", "mean"),
    )
    _write_df(
        agreement_summary,
        output / "m1" / "recommendation_agreement_summary_1235.parquet",
    )

    telemetry.context("m2", "CONFIGURATIONS", len(cohort))
    _log("[2/4] M2 DAG/additive and one-at-a-time sensitivities", progress, log)
    m2_results = _m2_sensitivity(cfg, cohort, int(cfg.get("outer_workers", 1)))
    _write_df(
        m2_results[m2_results["configuration"].isin(["DAG_BASE", "ADD_BASE"])],
        output / "m2" / "m2_structure_comparison.parquet",
    )
    _write_df(m2_results, output / "m2" / "m2_sensitivity_results.parquet")
    base_actions = m2_results[m2_results["configuration"].eq("DAG_BASE")][
        ["recovery_case_id", "action_id"]
    ].rename(columns={"action_id": "base_action"})
    stability = m2_results.merge(base_actions, on="recovery_case_id")
    stability["recommendation_agreement"] = stability["action_id"].eq(stability["base_action"])
    _write_df(stability, output / "m2" / "m2_downstream_stability.parquet")

    telemetry.context("m4", "VARIANTS", len(cohort))
    _log("[3/4] M4 EV/Mean-CVaR/CVaR on frozen common-support keys", progress, log)
    m4_scores, m4_metrics = _m4_variants(cfg, cohort, benchmark, int(cfg.get("outer_workers", 1)))
    _write_df(m4_scores, output / "m4" / "m4_variant_scores.parquet")
    _write_df(m4_metrics, output / "m4" / "m4_variant_metrics.parquet")

    telemetry.context("audit", "NONE", len(cohort))
    _log("[4/4] audit propagation hashes and publish registry", progress, log)
    checks = [
        ("m1_model_count", len(set(predictions["model_id"]) ^ set(MODELS))),
        ("m1_common_evaluation_index", predictions.groupby("model_id", observed=True)["snapshot_id"].nunique().nunique() - 1),
        ("m1_prediction_hash_count", abs(propagation["prediction_hash"].nunique() - 5)),
        ("m1_scenario_hash_count", abs(propagation["scenario_hash"].nunique() - 5)),
        ("m1_m2_cost_hash_count", abs(propagation["m2_cost_hash"].nunique() - 5)),
        ("m1_propagation_model_count", abs(len(propagation) - 5)),
        ("m1_formal_model_count", abs(int(propagation["formal_ranking"].sum()) - 4)),
        ("point_diagnostic_only", int(propagation.loc[propagation["model_id"].eq("POINT_OOF"), "formal_ranking"].any())),
        ("m2_configuration_count", len(set(m2_results["configuration"]) ^ set(M2_CONFIGS))),
        ("m4_variant_count", len(set(m4_scores["variant"]) ^ set(cfg["m4"]["variants"]))),
        ("common_support_nonempty", int(cohort.empty)),
        ("future_data_used", int(upstream["future_data_used_count"])),
        ("ranking_depth_count", abs(ranking_prefixes["ranking_k"].nunique() - 4)),
        ("ranking_model_count", abs(ranking_prefixes["model_id"].nunique() - len(MODELS))),
        ("ranking_padding_action_nonnull", int(ranking_prefixes.loc[ranking_prefixes["is_padding"], "action_id"].notna().sum())),
    ]
    audit = pd.DataFrame(
        [{"check": name, "value": int(value), "expected": 0, "status": "PASS" if value == 0 else "FAIL"} for name, value in checks]
    )
    _write_df(audit, output / "audit.parquet")
    if audit["status"].ne("PASS").any():
        raise ValueError("PART_ADV_AUDIT_FAILED:" + ",".join(audit.loc[audit["status"].ne("PASS"), "check"]))

    _part_adv_figures(output, m1_metrics, downstream, m2_results, m4_metrics)

    completed = pd.Timestamp.now(tz="UTC")
    summary = {
        "run_id": run_id,
        "mode": mode,
        "profile_id": cfg["profile_id"],
        "run_profile": cfg["run_profile"],
        "acceptance_profile": cfg["acceptance_profile"],
        "smoke_subset": cfg["smoke_subset"],
        "status": "PASS",
        "started_at": started,
        "finished_at": completed,
        "elapsed_seconds": float((completed - started).total_seconds()),
        "input_anchor_days": int(cohort["anchor_date"].nunique()),
        "episode_count": int(cohort["episode_id"].nunique()),
        "recovery_event_count": int(cohort["recovery_event_id"].nunique()),
        "recovery_case_count": int(len(cohort)),
        "passenger_supported_cases": int(len(cohort)),
        "passenger_unsupported_cases": int(upstream["excluded_by_passenger_count"]),
        "m4_supported_cohort_rate": upstream["m4_supported_cohort_rate"],
        "common_support_cohort_hash": upstream["common_support_cohort_hash"],
        "m1_models": MODELS,
        "m1_prediction_hash_count": int(propagation["prediction_hash"].nunique()),
        "m1_scenario_hash_count": int(propagation["scenario_hash"].nunique()),
        "m1_m2_cost_hash_count": int(propagation["m2_cost_hash"].nunique()),
        "m2_configurations": M2_CONFIGS,
        "m4_variants": list(cfg["m4"]["variants"]),
        "excluded_by_passenger_count": upstream["excluded_by_passenger_count"],
        "future_leakage": 0,
        "stale_artifacts": 0,
        "run_purpose": cfg.get("run_purpose"),
        "upstream_run_id": upstream["overall_run_id"],
        "upstream_registry_hash": upstream["overall_run_registry_hash"],
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        "m1_feature_contract_version": upstream["m1_feature_contract_version"],
        "m3_action_library_version": upstream["m3_action_library_version"],
        "m3_formal_action_count": upstream["m3_formal_action_count"],
        "all_m1_models_same_target": True,
        "m1_model_target_columns": {model: FORMAL_TARGET_COLUMN for model in MODELS},
        "observed_outcome_source": FORMAL_TARGET_COLUMN,
        "model_n_jobs": int(cfg.get("inner_model_threads", 1)),
        "parallel_model_count": int(cfg.get("outer_workers", 1)),
        **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
        "heartbeat_interval_seconds": 300,
        "ranking_depths": list(RANKING_DEPTHS),
        "ranking_contract_version": RANKING_CONTRACT_VERSION,
        "agreement_1235_rows": int(len(ranking_agreement)),
        "publication_allowed": False,
        "formal_baseline_replaced": False,
    }
    _write_json(summary, output / "run_summary.json")
    _write_json(_registry(output, cfg, upstream["overall_run_registry_hash"]), output / "artifact_registry.json")
    _write_json(
        {
            "run_id": run_id,
            "mode": mode,
            "profile_id": cfg["profile_id"],
            "run_profile": cfg["run_profile"],
            "acceptance_profile": cfg["acceptance_profile"],
            "smoke_subset": cfg["smoke_subset"],
            "status": "PASS",
            "input_hashes": {"overall_run_registry": upstream["overall_run_registry_hash"]},
            "common_support_cohort_hash": upstream["common_support_cohort_hash"],
            "config_hash": cfg["config_hash"],
            "implementation_hash": sha256_file(Path(__file__)),
            "checkpoint_paths": [row["checkpoint_path"] for row in telemetry.records if row["status"] == "PASS"],
            "resume_reused": any(bool(row.get("resume_reused")) for row in telemetry.records),
            "updated_at": completed,
            **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
        },
        output / "run_state.json",
    )
    return summary


def run(mode: str, progress: str = "normal", override: Path | None = None, *, requested_n_jobs: int = 1, resume: bool = False) -> dict[str, Any]:
    if mode == "precision":
        raise ValueError("PRECISION_REQUIRES_ACCEPTED_FULL")
    cfg = _load(mode, override)
    task_ids = [f"M1:{model}" for model in MODELS] + [f"M2:{name}" for name in M2_CONFIGS] + [f"M4:{name}" for name in cfg["m4"]["variants"]]
    plan = resolve_parallel_plan(requested_n_jobs, len(task_ids), prefer_outer_parallelism=True)
    cfg.update(parallel_metadata(
        plan,
        task_seed_digest=task_seed_hash(int(cfg["base_seed"]), "part_adv", mode, "registered_tasks", task_ids),
    ))
    cohort, upstream = _upstream(cfg)
    output = cfg["output"]
    input_hash = stable_hash(
        {
            "overall_run_registry_hash": upstream["overall_run_registry_hash"],
            "common_support_cohort_hash": upstream["common_support_cohort_hash"],
        }
    )
    implementation_hash = sha256_file(Path(__file__))
    state_path = output / "run_state.json"
    started = pd.Timestamp.now(tz="UTC")
    run_id = f"part-adv-{cfg['mode']}-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    resumed = False

    if output.exists() and any(output.iterdir()):
        if not resume:
            raise ValueError("INCOMPLETE_OUTPUT_REQUIRES_EXPLICIT_RESUME")
        if not state_path.exists():
            raise ValueError(f"OUTPUT_MIXED_WITHOUT_RUN_STATE:{output}")
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") not in {"RUNNING", "INCOMPLETE"}:
            raise ValueError(f"OUTPUT_MODE_EXISTS_NOT_RESUMABLE:{output}")
        expected = {
            "mode": mode,
            "input_hash": input_hash,
            "config_hash": cfg["config_hash"],
            "implementation_hash": implementation_hash,
            "formal_target_column": FORMAL_TARGET_COLUMN,
            "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
            "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        }
        for key, value in expected.items():
            if state.get(key) != value:
                raise ValueError(f"OUTPUT_RESUME_HASH_MISMATCH:{key}")
        if (output / "run_summary.json").exists() or (output / "artifact_registry.json").exists():
            raise ValueError(f"OUTPUT_MIXED_WITH_COMPLETE_ARTIFACTS:{output}")
        run_id = str(state["run_id"])
        started = pd.Timestamp(state["started_at"])
        resumed = True
    else:
        output.mkdir(parents=True, exist_ok=True)

    state = {
        "run_id": run_id,
        "module": "part_adv",
        "mode": mode,
        "status": "RUNNING",
        "started_at": started,
        "updated_at": pd.Timestamp.now(tz="UTC"),
        "input_hash": input_hash,
        "config_hash": cfg["config_hash"],
        "implementation_hash": implementation_hash,
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        "resume_requested": resumed,
        **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
    }
    os.environ["AIR_SLOT_MODULE"] = "part_adv"
    os.environ["AIR_SLOT_MODE"] = str(cfg["mode"])
    os.environ["AIR_SLOT_RUN_ID"] = str(run_id)
    _write_json(state, state_path)
    telemetry = _RunTelemetry(
        cfg,
        progress,
        output / "logs" / "run.log",
        input_hash,
        implementation_hash,
        upstream["formal_target_definition_hash"],
    )
    telemetry.start()
    try:
        with thread_limit_environment(plan):
            return _run_pipeline(mode, progress, cfg, cohort, upstream, run_id, telemetry, started, plan)
    except BaseException as exc:
        for complete_artifact in (output / "run_summary.json", output / "artifact_registry.json"):
            if complete_artifact.exists():
                complete_artifact.unlink()
        state.update(
            {
                "status": "INCOMPLETE",
                "failed_stage": telemetry.stage,
                "failed_model": telemetry.model,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "checkpoint_paths": [
                    row["checkpoint_path"] for row in telemetry.records if row.get("status") == "PASS"
                ],
                "updated_at": pd.Timestamp.now(tz="UTC"),
            }
        )
        _write_json(state, state_path)
        raise
    finally:
        telemetry.close()


__all__ = [
    "MODELS",
    "_RunTelemetry",
    "_formal_quantiles",
    "report",
    "run",
    "validate",
    "validate_m1_target_mapping",
]
