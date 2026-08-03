from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .shared_contracts import RANKING_CONTRACT_VERSION, RANKING_DEPTHS

from .pipeline_analysis import (
    _benchmark,
    _bootstrap,
    _decisions,
    _load,
    _metrics,
    _ranking_decisions,
    _upstream,
)
from .pipeline_checkpoint import (
    _checkpoint_identity,
    _load_policy_checkpoint,
    _policy_paths,
    _write_policy_checkpoint,
)
from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    HEARTBEAT_SECONDS,
    ParallelPlan,
    _Heartbeat,
    _log,
    _overall_adv_figure,
    _write_df,
    _write_json,
    parallel_metadata,
    resolve_parallel_plan,
    sha256_file,
    task_seed_hash,
    thread_limit_environment,
)
from .pipeline_publication import _registry, report, validate


def run(mode: str, progress: str = "normal", override: Path | None = None, *, requested_n_jobs: int = 1, resume: bool = False) -> dict[str, Any]:
    cfg = _load(mode, override)
    plan = resolve_parallel_plan(requested_n_jobs, task_count=10_000, prefer_outer_parallelism=True)
    cfg.update(parallel_metadata(
        plan,
        task_seed_digest=task_seed_hash(
            int(cfg.get("base_seed", 20260714)), "overall_adv", mode, "benchmark_bootstrap",
            ["BENCHMARK_ROWS", "BOOTSTRAP_REPLICATES"],
        ),
    ))
    cohort, upstream = _upstream(cfg)
    output = cfg["output"]
    output.mkdir(parents=True, exist_ok=True)
    log = output / "logs" / "run.log"
    started = pd.Timestamp.now(tz="UTC")
    identity = _checkpoint_identity(cfg, upstream)
    state_path = output / "run_state.json"
    existing_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    if existing_state:
        if not resume:
            raise ValueError("INCOMPLETE_OUTPUT_REQUIRES_EXPLICIT_RESUME")
        if existing_state.get("status") == "PASS":
            raise ValueError("MIXED_OUTPUT_COMPLETE_RUN_REQUIRES_CLEAN")
        mismatched = [key for key, value in identity.items() if existing_state.get(key) != value]
        if mismatched:
            raise ValueError("MIXED_OUTPUT_RUN_IDENTITY:" + ",".join(mismatched))
        run_id = existing_state["run_id"]
        started = pd.Timestamp(existing_state["started_at"])
    else:
        unexpected = [path for path in output.iterdir() if path.name != "logs"]
        if unexpected:
            raise ValueError("MIXED_OUTPUT_WITHOUT_RUN_STATE:" + ",".join(path.name for path in unexpected))
        run_id = f"overall-adv-{cfg['mode']}-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    _write_json(
        
        {"run_id": run_id, "status": "RUNNING", "started_at": started, **identity, **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"])},
        state_path,
    )
    os.environ["AIR_SLOT_MODULE"] = "overall_adv"
    os.environ["AIR_SLOT_MODE"] = str(cfg["mode"])
    os.environ["AIR_SLOT_RUN_ID"] = str(run_id)
    heartbeat = _Heartbeat(mode, progress, log, plan)
    heartbeat.tick("initializing", "NONE", 0, force=True)

    try:
        with thread_limit_environment(plan):
            return _run_active(cfg, cohort, upstream, output, log, started, run_id, identity, heartbeat, progress, plan)
    except BaseException as exc:
        _write_json(
            {
                "run_id": run_id,
                "mode": mode,
                "status": "INCOMPLETE",
                "started_at": started,
                "updated_at": pd.Timestamp.now(tz="UTC"),
                "error_type": type(exc).__name__,
                "error": str(exc),
                **identity,
                **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
            },
            state_path,
        )
        raise


def _run_active(
    cfg: dict[str, Any],
    cohort: pd.DataFrame,
    upstream: dict[str, Any],
    output: Path,
    log: Path,
    started: pd.Timestamp,
    run_id: str,
    identity: dict[str, str],
    heartbeat: _Heartbeat,
    progress: str,
    plan: ParallelPlan,
) -> dict[str, Any]:

    _log("[1/6] load unified overall_run artifacts and freeze common passenger cohort", progress, log)
    _write_df(cohort, output / "m4_common_support_cohort.parquet")
    _write_json(upstream, output / "common_support_cohort.json")
    scores = pd.read_parquet(cfg["upstream"] / "m4_action_scores.parquet")
    recommendations = pd.read_parquet(cfg["upstream"] / "m4_recommendations.parquet")
    global_full_ranking = pd.read_parquet(cfg["upstream"] / "m4_rankings.parquet")
    global_prefixes = pd.read_parquet(
        cfg["upstream"] / "m4_ranking_all_k.parquet"
    )

    _log("[2/6] rank LOCAL_F and load frozen GLOBAL_FPR decisions", progress, log)
    score_path = output / "local_f_scores.parquet"
    local = _load_policy_checkpoint(output, "LOCAL_F", identity, [score_path])
    global_policy = _load_policy_checkpoint(output, "GLOBAL_FPR", identity, [])
    if local is None or global_policy is None:
        scores, computed = _decisions(scores, recommendations, cohort)
        if local is None:
            _write_df(scores, score_path)
            local = computed[computed["policy_id"].eq("LOCAL_F")].copy()
            checkpoint = _write_policy_checkpoint(output, "LOCAL_F", local, identity, [score_path])
            heartbeat.checkpointed(checkpoint)
        if global_policy is None:
            global_policy = computed[computed["policy_id"].eq("GLOBAL_FPR")].copy()
            checkpoint = _write_policy_checkpoint(output, "GLOBAL_FPR", global_policy, identity, [])
            heartbeat.checkpointed(checkpoint)
    else:
        scores = pd.read_parquet(score_path)
        _log("[2/6] reuse hash-validated LOCAL_F and GLOBAL_FPR checkpoints", progress, log)
    decisions = pd.concat([local, global_policy], ignore_index=True)
    _write_df(decisions, output / "policy_decisions.parquet")
    ranking_policies, ranking_comparison = _ranking_decisions(
        scores, global_full_ranking, global_prefixes, cohort
    )
    _write_df(ranking_policies, output / "ranking_policy_prefixes.parquet")
    _write_df(
        ranking_comparison,
        output / "ranking_comparison_1235.parquet",
    )
    ranking_summary = ranking_comparison.groupby(
        "ranking_k", as_index=False, observed=True
    ).agg(
        exact_order_match_rate=("exact_order_match", "mean"),
        ordered_disagreement_rate=("ordered_disagreement", "mean"),
        set_disagreement_rate=("set_disagreement", "mean"),
        order_only_disagreement_rate=("order_only_disagreement", "mean"),
        overlap_rate=("overlap_rate", "mean"),
        position_match_rate=("position_match_rate", "mean"),
        full_k_support_rate=("full_k_support", "mean"),
    )
    _write_df(ranking_summary, output / "ranking_summary_1235.parquet")

    _log("[3/6] run deterministic independent benchmark draws", progress, log)
    benchmark_path = output / "benchmark_action_outcomes" / "part.parquet"
    if benchmark_path.exists():
        benchmark = pd.read_parquet(benchmark_path)
        expected_rows = len(scores) * int(cfg["draws"])
        observed_pairs = benchmark[["snapshot_id", "action_id"]].drop_duplicates().shape[0]
        if len(benchmark) != expected_rows or observed_pairs != len(scores):
            raise ValueError("INCOMPLETE_BENCHMARK_RESUME_ARTIFACT")
        _log("[3/6] reuse complete deterministic benchmark artifact", progress, log)
    else:
        benchmark = _benchmark(scores, cohort, cfg, heartbeat, plan.outer_workers)
        _write_df(benchmark, benchmark_path)

    _log("[4/6] compute paired recovery-case metrics", progress, log)
    metrics, paired, summary = _metrics(decisions, benchmark)
    _write_df(metrics, output / "recovery_case_metrics.parquet")
    _write_df(paired, output / "paired_metrics.parquet")
    summary.to_csv(output / "summary.csv", index=False)

    _log("[5/6] bootstrap and report action distributions", progress, log)
    bootstrap = _bootstrap(metrics, cfg["bootstrap"], cfg["base_seed"], heartbeat, plan.outer_workers)
    _write_df(bootstrap, output / "bootstrap_results.parquet")
    action_distribution = decisions.groupby(["policy_id", "selected_action"], as_index=False, observed=True).size()
    action_distribution["rate"] = action_distribution["size"] / action_distribution.groupby("policy_id", observed=True)["size"].transform("sum")
    _write_df(action_distribution, output / "m4_selected_action_distribution.parquet")

    _log("[6/6] audit and publish registry", progress, log)
    nondegenerate = int(
        benchmark.groupby("recovery_case_id", observed=True).apply(
            lambda group: group.groupby("action_id", observed=True)["total_loss"].mean().nunique() > 1,
            include_groups=False,
        ).sum()
    )
    checks = [
        ("common_support_nonempty", int(len(cohort) == 0)),
        ("common_support_hash_present", int(not upstream["common_support_cohort_hash"])),
        ("future_data_used", int(upstream["future_data_used_count"])),
        ("policy_cohort_mismatch", int(decisions.groupby("policy_id", observed=True)["recovery_case_id"].nunique().nunique() != 1)),
        ("duplicate_policy_case", int(decisions.duplicated(["policy_id", "recovery_case_id"]).sum())),
        ("a00_comparator_missing", int(cohort["snapshot_id"].nunique() - scores.loc[scores["action_id"].eq("A00"), "snapshot_id"].nunique())),
        ("minimum_nondegenerate_cases", max(0, 8 - nondegenerate)),
        ("ranking_depth_count", abs(ranking_comparison["ranking_k"].nunique() - 4)),
        ("ranking_padding_action_nonnull", int(ranking_policies.loc[ranking_policies["is_padding"], "action_id"].notna().sum())),
    ]
    audit = pd.DataFrame(
        [{"check": name, "value": value, "expected": 0, "status": "PASS" if value == 0 else "FAIL"} for name, value in checks]
    )
    _write_df(audit, output / "audit.parquet")
    if audit["status"].ne("PASS").any():
        raise ValueError("OVERALL_ADV_AUDIT_FAILED:" + ",".join(audit.loc[audit["status"].ne("PASS"), "check"]))

    (output / "figures").mkdir(exist_ok=True)
    _overall_adv_figure(
        metrics,
        paired,
        summary,
        bootstrap,
        output / "figures" / "fig01_local_global_comparison",
    )

    completed = pd.Timestamp.now(tz="UTC")
    global_actions = decisions[decisions["policy_id"].eq("GLOBAL_FPR")]
    summary_json = {
        "run_id": run_id,
        "mode": cfg["mode"],
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
        "selected_action_distribution": global_actions["selected_action"].value_counts().sort_index().to_dict(),
        "a00_rate": float(global_actions["selected_action"].eq("A00").mean()),
        "excluded_by_passenger_count": upstream["excluded_by_passenger_count"],
        "benchmark_draws": cfg["draws"],
        "bootstrap_replicates": cfg["bootstrap"],
        "worker_count": plan.outer_workers,
        **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
        "heartbeat_interval_seconds": HEARTBEAT_SECONDS,
        "stale_artifacts": 0,
        "future_data_used": 0,
        "run_purpose": cfg.get("run_purpose"),
        "upstream_run_id": upstream["overall_run_id"],
        "upstream_registry_hash": upstream["overall_run_registry_hash"],
        "upstream_formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        "m1_feature_contract_version": upstream["m1_feature_contract_version"],
        "m3_action_library_version": upstream["m3_action_library_version"],
        "m3_formal_action_count": upstream["m3_formal_action_count"],
        "ranking_depths": list(RANKING_DEPTHS),
        "ranking_contract_version": RANKING_CONTRACT_VERSION,
        "ranking_comparison_rows": int(len(ranking_comparison)),
        "publication_allowed": False,
        "formal_baseline_replaced": False,
    }
    _write_json(summary_json, output / "run_summary.json")
    _write_json(_registry(output, cfg, upstream["overall_run_registry_hash"]), output / "artifact_registry.json")
    _write_json(
        {
            "run_id": run_id,
            "mode": cfg["mode"],
            "profile_id": cfg["profile_id"],
            "run_profile": cfg["run_profile"],
            "acceptance_profile": cfg["acceptance_profile"],
            "smoke_subset": cfg["smoke_subset"],
            "status": "PASS",
            "input_hashes": {"overall_run_registry": upstream["overall_run_registry_hash"]},
            "common_support_cohort_hash": upstream["common_support_cohort_hash"],
            "config_hash": cfg["config_hash"],
            "implementation_hash": sha256_file(Path(__file__)),
            "updated_at": completed,
            **parallel_metadata(plan, task_seed_digest=cfg["task_seed_hash"]),
        },
        output / "run_state.json",
    )
    return summary_json


__all__ = ["_policy_paths", "report", "run", "validate"]
