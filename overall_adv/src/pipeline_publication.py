from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .pipeline_analysis import _load, _upstream
from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    ROOT,
    _write_json,
    pq,
    sha256_file,
)


def _registry(output: Path, cfg: dict[str, Any], input_hash: str) -> dict[str, Any]:
    entries = []
    for path in sorted(output.rglob("*")):
        relative = path.relative_to(output)
        if (
            path.is_file()
            and relative.parts[0] != "logs"
            and path.name not in {"artifact_registry.json", "run_state.json"}
        ):
            entries.append(
                {
                    "artifact_name": path.stem,
                    "relative_path": relative.as_posix(),
                    "sha256": sha256_file(path),
                    "row_count": (int(pq.ParquetFile(path).metadata.num_rows) if pq is not None else None) if path.suffix == ".parquet" else None,
                    "schema_version": "air-slot-unified-v3",
                    "contract_version": cfg["contract_version"],
                    "parameter_version": cfg["parameter_version"],
                    "input_hash": input_hash,
                    "config_hash": cfg["config_hash"],
                    "implementation_hash": sha256_file(Path(__file__)),
                    "mode": cfg["mode"],
                    "created_by_stage": "overall_adv",
                }
            )
    upstream = json.loads((cfg["upstream"] / "run_summary.json").read_text(encoding="utf-8"))
    return {
        "artifacts": entries,
        "profile_id": cfg["profile_id"],
        "run_profile": cfg["run_profile"],
        "acceptance_profile": cfg["acceptance_profile"],
        "smoke_subset": cfg["smoke_subset"],
        "stale_artifacts": 0,
        "upstream_formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        "m1_feature_contract_version": upstream["m1_feature_contract_version"],
        "m3_action_library_version": upstream["m3_action_library_version"],
        "m3_formal_action_count": upstream["m3_formal_action_count"],
        "ranking_contract_version": upstream["ranking_contract_version"],
        "ranking_depths": upstream["ranking_depths"],
        "run_purpose": cfg.get("run_purpose"),
        "publication_allowed": bool(cfg.get("publication_allowed", False)),
        "formal_baseline_replaced": bool(cfg.get("formal_baseline_replaced", False)),
    }


def validate(mode: str = "fast", override: Path | None = None) -> dict[str, Any]:
    cfg = _load(mode, override)
    cohort, upstream = _upstream(cfg)
    output = cfg["output"]
    if (output / "audit.parquet").exists():
        audit = pd.read_parquet(output / "audit.parquet")
        if audit["status"].ne("PASS").any():
            raise ValueError("OVERALL_ADV_AUDIT_FAILED")
        registry = json.loads((output / "artifact_registry.json").read_text(encoding="utf-8"))
        if registry.get("upstream_formal_target_column") != FORMAL_TARGET_COLUMN:
            raise ValueError("OVERALL_ADV_UPSTREAM_FORMAL_TARGET_INVALID")
        if registry.get("formal_target_definition_hash") != upstream["formal_target_definition_hash"]:
            raise ValueError("OVERALL_ADV_UPSTREAM_TARGET_DEFINITION_HASH_MISMATCH")
        for key in (
            "m1_feature_contract_version", "m3_action_library_version",
            "m3_formal_action_count", "ranking_contract_version", "ranking_depths",
        ):
            if registry.get(key) != upstream[key]:
                raise ValueError(f"OVERALL_ADV_{key.upper()}_LINEAGE_MISMATCH")
        input_hashes = {entry.get("input_hash") for entry in registry.get("artifacts", [])}
        if input_hashes and input_hashes != {upstream["overall_run_registry_hash"]}:
            raise ValueError("STALE_UNIFIED_UPSTREAM")
        stale = [
            entry["relative_path"]
            for entry in registry.get("artifacts", [])
            if not (output / entry["relative_path"]).exists()
            or sha256_file(output / entry["relative_path"]) != entry["sha256"]
        ]
        if stale:
            raise ValueError("STALE_ARTIFACT:" + ",".join(stale[:10]))
        saved = json.loads((output / "common_support_cohort.json").read_text(encoding="utf-8"))
        if saved["common_support_cohort_hash"] != upstream["common_support_cohort_hash"]:
            raise ValueError("COMMON_SUPPORT_COHORT_STALE")
    return {
        "status": "PASS",
        "upstream_run_id": upstream["overall_run_id"],
        "common_support_rows": len(cohort),
        "common_support_cohort_hash": upstream["common_support_cohort_hash"],
        "stale_artifacts": 0,
        "upstream_formal_target_column": FORMAL_TARGET_COLUMN,
        "m1_feature_contract_version": upstream["m1_feature_contract_version"],
        "m3_action_library_version": upstream["m3_action_library_version"],
        "m3_formal_action_count": upstream["m3_formal_action_count"],
        "ranking_contract_version": upstream["ranking_contract_version"],
        "ranking_depths": upstream["ranking_depths"],
    }


def report(mode: str = "fast") -> dict[str, Any]:
    output = ROOT / "output" / mode
    summary_path = output / "run_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)

    # ------------------------------------------------------------------
    # Regenerate publication figures from existing frozen parquet tables.
    # This does not re-train, re-predict, or re-score any model.
    # ------------------------------------------------------------------
    required = {
        "metrics": output / "recovery_case_metrics.parquet",
        "paired": output / "paired_metrics.parquet",
        "summary": output / "summary.csv",
        "bootstrap": output / "bootstrap_results.parquet",
    }
    missing = [label for label, path in required.items() if not path.exists()]
    figures_regenerated = False
    if not missing:
        from .pipeline_common import _overall_adv_figure
        (output / "figures").mkdir(exist_ok=True)
        _overall_adv_figure(
            pd.read_parquet(required["metrics"]),
            pd.read_parquet(required["paired"]),
            pd.read_csv(required["summary"]),
            pd.read_parquet(required["bootstrap"]),
            output / "figures" / "fig01_local_global_comparison",
        )
        figures_regenerated = True

    result = json.loads(summary_path.read_text(encoding="utf-8"))
    result["figures_regenerated"] = figures_regenerated
    if missing:
        result["figure_missing_inputs"] = missing
    cfg = _load(mode)
    upstream_registry_hash = sha256_file(cfg["upstream"] / "artifact_registry.json")
    _write_json(result, summary_path)
    _write_json(
        _registry(output, cfg, upstream_registry_hash),
        output / "artifact_registry.json",
    )
    return result


