from __future__ import annotations

import pandas as pd

from .input import object_hash, write_json
from .pipeline_config import _package_versions
from .predecessor_matcher import PREDECESSOR_FEATURE_COLUMNS
from .stages.context import PreBuildContext


def build_manifest(ctx: PreBuildContext, output_hashes: dict[str, str]) -> dict:
    cfg = ctx.cfg
    manifest = {
        "project_version": cfg["project_version"],
        "schema_version": cfg["schema_version"],
        "created_at": pd.Timestamp.now(tz="UTC"),
        "config_hash": cfg["config_hash"],
        "run_mode": cfg["mode"],
        "run_purpose": cfg.get("runtime", {}).get("run_purpose"),
        "splits": cfg["splits"],
        "complete_state_dates": sorted(
            str(pd.Timestamp(date).date()) for date in ctx.complete_dates
        ),
        "adapt_manifest_path": str(cfg.get("adapt_manifest_path", "")),
        "adapt_manifest_sha256": cfg.get("adapt_manifest_sha256"),
        **cfg.get("profile_contract", {}),
        "raw_file_count": len(ctx.raw_inventory),
        "raw_inventory_hash": object_hash(
            ctx.raw_inventory.drop(columns=["absolute_path"], errors="ignore").to_dict(
                "records"
            )
        ),
        "package_versions": _package_versions(),
        "formal_eligible": True,
        "m1_feature_contract_version": cfg["predecessor_matching"][
            "feature_contract_version"
        ],
        "predecessor_matching_contract_id": cfg["predecessor_matching"][
            "contract_id"
        ],
        "predecessor_feature_list": PREDECESSOR_FEATURE_COLUMNS,
        "predecessor_feature_hash": object_hash(PREDECESSOR_FEATURE_COLUMNS),
        "matching_parameter_hash": object_hash(cfg["predecessor_matching"]),
        "supported_predecessor_rate": float(
            ctx.bundle.episodes["has_supported_predecessor"].fillna(False).mean()
        ),
        "evidence_tier_counts": ctx.bundle.episodes["predecessor_evidence_tier"]
        .fillna("UNSUPPORTED")
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict(),
        "scientific_approved": bool(
            cfg["predecessor_matching"]["scientific_approved"]
        ),
        "publication_allowed": bool(
            cfg["predecessor_matching"]["publication_allowed"]
        ),
        "formal_baseline_replaced": bool(
            cfg.get("runtime", {}).get("formal_baseline_replaced", False)
        ),
        "validation": ctx.validation,
        "readiness": ctx.readiness_summary,
    }
    write_json(manifest, ctx.paths["manifests"] / "pre_manifest.json")
    manifest["output_hashes"] = output_hashes
    write_json(manifest, ctx.paths["manifests"] / "pre_manifest.json")
    return manifest


def build_summary(ctx: PreBuildContext, finished: pd.Timestamp) -> dict:
    cfg = ctx.cfg
    passenger = ctx.passenger_month_summary
    validation = ctx.validation
    return {
        **ctx._target_metadata(),
        "formal_target_contract": "PASS",
        **{
            field: validation["formal_target_contract"][field]
            for field in [
                "rows_total",
                "raw_non_null",
                "model_non_null",
                "raw_model_difference_rows",
                "raw_model_max_abs_difference",
                "raw_model_mean_abs_difference",
                "label_identity_mismatch_count",
            ]
        },
        "run_id": ctx.current_run_id,
        "mode": cfg["mode"],
        "status": "PASS",
        "run_purpose": cfg.get("runtime", {}).get("run_purpose"),
        **cfg.get("profile_contract", {}),
        "started_at": str(ctx.run_started),
        "finished_at": str(finished),
        "elapsed_seconds": float((finished - ctx.run_started).total_seconds()),
        "input_anchor_days": int(ctx.subset_manifest["anchor_date"].nunique()),
        "episode_count": len(ctx.bundle.episodes),
        "snapshot_count": len(ctx.bundle.snapshots),
        "formal_result": cfg["mode"] != "fast",
        "debug_only": cfg["mode"] == "fast",
        "downstream_fast_ready": cfg["mode"] == "fast",
        "formal_ready": False,
        "part_adv_ready": False,
        "accepted_full": False,
        "accepted_precision": False,
        "failed_stages": 0,
        "silent_fallbacks": 0,
        "state_worker_count": max(
            1, int(cfg.get("runtime", {}).get("state_workers", 1))
        ),
        **ctx.parallel_fields,
        "heartbeat_interval_seconds": 300,
        "passenger_status": passenger["passenger_status"],
        "passenger_support_policy": "PARTIAL_SUPPORT_ALLOWED",
        "passenger_support_rate": passenger["passenger_support_rate_overall"],
        "supported_recovery_cases": passenger["supported_recovery_cases"],
        "m4_supported_cohort_nonempty": passenger[
            "m4_supported_cohort_nonempty"
        ],
        "m1_feature_contract_version": cfg["predecessor_matching"][
            "feature_contract_version"
        ],
        "predecessor_matching_contract_id": cfg["predecessor_matching"][
            "contract_id"
        ],
        "matching_parameter_hash": object_hash(cfg["predecessor_matching"]),
        "supported_predecessor_rate": float(
            ctx.bundle.episodes["has_supported_predecessor"].fillna(False).mean()
        ),
        "scientific_approved": bool(
            cfg["predecessor_matching"]["scientific_approved"]
        ),
        "publication_allowed": bool(
            cfg["predecessor_matching"]["publication_allowed"]
        ),
        "formal_baseline_replaced": bool(
            cfg.get("runtime", {}).get("formal_baseline_replaced", False)
        ),
    }
