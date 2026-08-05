from __future__ import annotations

import contextlib
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd
from pre_contract_gate import require_downstream_v2_migration
from ranking_contract import RANKING_CONTRACT_VERSION, RANKING_DEPTHS

FORMAL_TARGET_COLUMN = "M1_JOINT_SAMPLE_CONTRACT"
SENSITIVITY_TARGET_COLUMN = "M1_CAPACITY_SENSITIVITY_CONTRACT"
FORMAL_TARGET_CONTRACT_VERSION = "M1_CHAIN_DYNAMIC_DISTRIBUTION_V1"
THREAD_ENVIRONMENT_VARIABLES = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)
T = TypeVar("T")


@dataclass(frozen=True)
class ParallelPlan:
    requested_n_jobs: int
    resolved_n_jobs: int
    outer_workers: int
    inner_model_threads: int
    parallel_backend: str


def resolve_requested_n_jobs(
    cli_value: int | None,
    config_value: int | None = None,
    environment: dict[str, str] | None = None,
) -> int:
    env = os.environ if environment is None else environment
    raw: Any
    if cli_value is not None:
        raw = cli_value
    elif str(env.get("AIR_SLOT_N_JOBS", "")).strip():
        raw = env["AIR_SLOT_N_JOBS"]
    elif config_value is not None:
        raw = config_value
    else:
        raw = 1
    try:
        requested = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_N_JOBS:{raw}") from exc
    if requested == 0 or requested < -1:
        raise ValueError(f"INVALID_N_JOBS:{requested}")
    return requested


def resolve_parallel_plan(
    requested_n_jobs: int,
    task_count: int,
    prefer_outer_parallelism: bool = True,
) -> ParallelPlan:
    if requested_n_jobs == 0 or requested_n_jobs < -1:
        raise ValueError(f"INVALID_N_JOBS:{requested_n_jobs}")
    available = max(1, int(os.cpu_count() or 1))
    resolved = max(1, available - 1) if requested_n_jobs == -1 else min(requested_n_jobs, available)
    tasks = max(1, int(task_count))
    if prefer_outer_parallelism and tasks > 1 and resolved > 1:
        outer = min(tasks, resolved)
        inner = 1
        backend = "thread"
    else:
        outer = 1
        inner = resolved
        backend = "native"
    if outer * inner > resolved:
        raise RuntimeError("PARALLEL_BUDGET_OVERSUBSCRIBED")
    return ParallelPlan(requested_n_jobs, resolved, outer, inner, backend)


def stable_task_seed(
    base_seed: int,
    module: str,
    mode: str,
    stage: str,
    stable_task_id: str,
    replicate_id: int | str = 0,
) -> int:
    payload = "|".join(map(str, (base_seed, module, mode, stage, stable_task_id, replicate_id)))
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16) % (2**32 - 1)


def task_seed_hash(
    base_seed: int,
    module: str,
    mode: str,
    stage: str,
    task_ids: list[str],
) -> str:
    mapping = {
        task_id: stable_task_seed(base_seed, module, mode, stage, task_id)
        for task_id in task_ids
    }
    return stable_hash(mapping)


def parallel_metadata(plan: ParallelPlan, *, task_seed_digest: str) -> dict[str, Any]:
    return {
        **asdict(plan),
        "task_partition_version": "AIR_SLOT_PARALLEL_TASKS_V1_20260726",
        "task_seed_strategy": "SHA256_BASE_SEED_MODULE_MODE_STAGE_STABLE_TASK_ID_REPLICATE_ID",
        "task_seed_hash": task_seed_digest,
    }


@contextlib.contextmanager
def thread_limit_environment(plan: ParallelPlan):
    previous = {name: os.environ.get(name) for name in THREAD_ENVIRONMENT_VARIABLES}
    thread_limit = str(plan.inner_model_threads)
    for name in THREAD_ENVIRONMENT_VARIABLES:
        os.environ[name] = thread_limit
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_ordered_thread_tasks(
    task_ids: list[str],
    worker: Callable[[str], T],
    max_workers: int,
) -> list[T]:
    ordered = list(task_ids)
    if max_workers <= 1 or len(ordered) <= 1:
        return [worker(task_id) for task_id in ordered]
    results: dict[str, T] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(ordered))) as executor:
        futures = {executor.submit(worker, task_id): task_id for task_id in ordered}
        try:
            for future in as_completed(futures):
                task_id = futures[future]
                results[task_id] = future.result()
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return [results[task_id] for task_id in ordered]


def spawn_probe(value: str) -> str:
    """Top-level pickle-safe fixture for Windows spawn compatibility tests."""
    return value


def require_formal_target_metadata(metadata: dict[str, Any], source: str) -> str:
    require_downstream_v2_migration()
    if metadata.get("formal_target_column") != FORMAL_TARGET_COLUMN:
        raise ValueError(f"{source}_FORMAL_TARGET_INVALID")
    if metadata.get("formal_target_contract_version") != FORMAL_TARGET_CONTRACT_VERSION:
        raise ValueError(f"{source}_FORMAL_TARGET_CONTRACT_VERSION_INVALID")
    definition_hash = metadata.get("formal_target_definition_hash")
    if not definition_hash:
        raise ValueError(f"{source}_FORMAL_TARGET_DEFINITION_HASH_MISSING")
    return str(definition_hash)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def model_change_lineage(summary: dict[str, Any]) -> dict[str, Any]:
    lineage = {
        "m1_feature_contract_version": summary.get("m1_feature_contract_version"),
        "m3_action_library_version": summary.get("m3_action_library_version"),
        "m3_formal_action_count": summary.get("m3_formal_action_count"),
        "ranking_contract_version": summary.get("ranking_contract_version"),
        "ranking_depths": summary.get("ranking_depths"),
    }
    if lineage["ranking_contract_version"] == RANKING_CONTRACT_VERSION:
        missing = [key for key, value in lineage.items() if value is None]
        if missing:
            raise ValueError("MODEL_CHANGE_LINEAGE_INCOMPLETE:" + ",".join(missing))
        if lineage["m1_feature_contract_version"] != "M1_PREVIOUS_LEG_V1":
            raise ValueError("M1_FEATURE_CONTRACT_VERSION_INVALID")
        if lineage["m3_action_library_version"] != "M3_RESPONSE_V3_EXPANDED_PROVISIONAL":
            raise ValueError("M3_ACTION_LIBRARY_VERSION_INVALID")
        if int(lineage["m3_formal_action_count"]) != 26:
            raise ValueError("M3_FORMAL_ACTION_COUNT_INVALID")
        if tuple(int(value) for value in lineage["ranking_depths"]) != RANKING_DEPTHS:
            raise ValueError("RANKING_DEPTH_LINEAGE_INVALID")
    return lineage


def load_common_passenger_cohort(
    project_root: Path,
    mode: str = "fast",
    *,
    pre_mode: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the unified overall_run evaluation rows supported by passenger input.

    Both advantage projects call this function, so their M4 comparison cohort is
    frozen by exactly the same keys and support predicate.
    """

    require_downstream_v2_migration()
    resolved_pre_mode = pre_mode or mode
    overall_root = project_root / "overall_run" / "output" / mode
    pre_root = project_root / "pre" / "output" / resolved_pre_mode
    summary_path = overall_root / "run_summary.json"
    registry_path = overall_root / "artifact_registry.json"
    required = [
        summary_path,
        registry_path,
        overall_root / "metrics" / "m1_predictions_evaluation.parquet",
        overall_root / "metrics" / "m2_summary.parquet",
        overall_root / "m4_recommendations.parquet",
        pre_root / "snapshots.parquet",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("UNIFIED_UPSTREAM_ARTIFACT_MISSING:" + ",".join(missing))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    change_lineage = model_change_lineage(summary)
    summary_definition_hash = require_formal_target_metadata(summary, "OVERALL_RUN_SUMMARY")
    registry_definition_hash = require_formal_target_metadata(registry, "OVERALL_RUN_REGISTRY")
    if summary_definition_hash != registry_definition_hash:
        raise ValueError("OVERALL_RUN_FORMAL_TARGET_DEFINITION_HASH_MISMATCH")
    if summary.get("engineering_status") != "PASS":
        raise ValueError("UNIFIED_UPSTREAM_ENGINEERING_NOT_PASS")
    if not summary.get("m4_available", False):
        raise ValueError("UNIFIED_UPSTREAM_M4_UNAVAILABLE")

    predictions = pd.read_parquet(overall_root / "metrics" / "m1_predictions_evaluation.parquet")
    m2 = pd.read_parquet(overall_root / "metrics" / "m2_summary.parquet")
    recommendations = pd.read_parquet(overall_root / "m4_recommendations.parquet")
    snapshot_columns = [
        "snapshot_id",
        "episode_id",
        "flight_id",
        "split",
        "anchor_date",
        "airport",
        "snapshot_stage",
        "trigger_event_group_id",
        "estimated_passenger_load",
        "connection_pressure_proxy",
        "rebooking_scarcity_proxy",
        "passenger_proxy_support",
        "passenger_evidence_status",
        "passenger_future_data_used",
        "m4_passenger_input_supported",
        "m4_eligible",
        "m4_ineligibility_reason",
    ]
    snapshots = pd.read_parquet(pre_root / "snapshots.parquet", columns=snapshot_columns)
    evaluation_ids = set(predictions["snapshot_id"].astype(str))
    snapshots = snapshots[snapshots["snapshot_id"].astype(str).isin(evaluation_ids)].copy()
    support = (
        snapshots[
            [
                "estimated_passenger_load",
                "connection_pressure_proxy",
                "rebooking_scarcity_proxy",
            ]
        ].notna().all(axis=1)
        & pd.to_numeric(snapshots["passenger_proxy_support"], errors="coerce").gt(0)
        & snapshots["passenger_evidence_status"].astype("string").isin(
            ["SUPPORTED_PROXY", "FALLBACK_PROXY", "OBSERVED"]
        )
        & ~snapshots["passenger_future_data_used"].fillna(False).astype(bool)
        & snapshots["m4_passenger_input_supported"].fillna(False).astype(bool)
        & snapshots["m4_eligible"].fillna(False).astype(bool)
    )
    supported = snapshots[support].copy()
    supported_ids = set(supported["snapshot_id"].astype(str))
    m2_supported = set(
        m2.loc[m2["passenger_proxy_used"].fillna(False).astype(bool), "snapshot_id"].astype(str)
    )
    recommendation_ids = set(recommendations["snapshot_id"].astype(str))
    common_ids = supported_ids & m2_supported & recommendation_ids
    cohort = supported[supported["snapshot_id"].astype(str).isin(common_ids)].copy()
    cohort["airport_id"] = cohort["airport"].astype(str)
    cohort["recovery_case_id"] = cohort["snapshot_id"].astype(str)
    fallback_event = (
        cohort["anchor_date"].astype(str)
        + "|"
        + cohort["airport_id"].astype(str)
    ).map(lambda value: stable_hash(["AIRPORT_DAY", value])[:24])
    event = cohort["trigger_event_group_id"].astype("string")
    cohort["recovery_event_id"] = event.where(event.notna() & event.ne(""), fallback_event).astype(str)
    cohort = cohort.sort_values("snapshot_id", kind="mergesort").reset_index(drop=True)
    cohort_hash = stable_hash(cohort["snapshot_id"].astype(str).tolist())
    audit = {
        "mode": mode,
        "pre_mode": resolved_pre_mode,
        "overall_run_id": summary["run_id"],
        "overall_run_registry_hash": sha256_file(registry_path),
        "overall_run_engineering_status": summary["engineering_status"],
        "overall_run_scientific_status": summary["scientific_status"],
        "overall_run_passenger_support_rate": summary["passenger_proxy_support_rate"],
        "m4_available": summary["m4_available"],
        "total_evaluation_rows": int(len(predictions)),
        "pre_passenger_supported_rows": int(len(supported_ids)),
        "m2_passenger_supported_rows": int(len(m2_supported & evaluation_ids)),
        "m4_recommendation_rows": int(len(recommendation_ids & evaluation_ids)),
        "common_support_rows": int(len(cohort)),
        "excluded_by_passenger_count": int(len(predictions) - len(cohort)),
        "m4_supported_cohort_rate": float(len(cohort) / len(predictions)) if len(predictions) else 0.0,
        "common_support_cohort_hash": cohort_hash,
        "future_data_used_count": int(
            snapshots["passenger_future_data_used"].fillna(False).astype(bool).sum()
        ),
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": summary_definition_hash,
        **change_lineage,
    }
    if cohort.empty:
        raise ValueError("M4_COMMON_PASSENGER_SUPPORT_COHORT_EMPTY")
    if audit["future_data_used_count"] != 0:
        raise ValueError("PASSENGER_FUTURE_DATA_USED")
    return cohort, audit
