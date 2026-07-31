from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:
    pq = None

from .pipeline_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    ROOT,
    sha256_file,
    validate_m1_target_mapping,
)
from .pipeline_inputs import _load, _upstream


def _registry(output: Path, cfg: dict[str, Any], input_hash: str) -> dict[str, Any]:
    entries = []
    for path in sorted(output.rglob("*")):
        relative = path.relative_to(output)
        if path.is_file() and relative.parts[0] != "logs" and path.name not in {"artifact_registry.json", "run_state.json"}:
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
                    "created_by_stage": "part_adv",
                }
            )
    upstream = json.loads((cfg["upstream"] / "run_summary.json").read_text(encoding="utf-8"))
    return {
        "artifacts": entries,
        "stale_artifacts": 0,
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
        "formal_target_definition_hash": upstream["formal_target_definition_hash"],
        "all_m1_models_same_target": True,
    }


def validate(mode: str = "fast", override: Path | None = None) -> dict[str, Any]:
    cfg = _load(mode, override)
    cohort, upstream = _upstream(cfg)
    output = cfg["output"]
    if (output / "audit.parquet").exists():
        audit = pd.read_parquet(output / "audit.parquet")
        if audit["status"].ne("PASS").any():
            raise ValueError("PART_ADV_AUDIT_FAILED")
        registry = json.loads((output / "artifact_registry.json").read_text(encoding="utf-8"))
        if registry.get("formal_target_column") != FORMAL_TARGET_COLUMN:
            raise ValueError("PART_ADV_REGISTRY_FORMAL_TARGET_INVALID")
        if registry.get("all_m1_models_same_target") is not True:
            raise ValueError("PART_ADV_M1_TARGETS_DIVERGED")
        predictions = pd.read_parquet(output / "m1" / "m1_predictions.parquet", columns=["model_id", "snapshot_id", "observed_outcome"])
        frame = pd.read_parquet(output / "input_adapter" / "m1_model_frame.parquet", columns=["snapshot_id", FORMAL_TARGET_COLUMN])
        identity = predictions.merge(frame, on="snapshot_id", how="left", validate="many_to_one")
        observed = pd.to_numeric(identity["observed_outcome"], errors="coerce")
        raw = pd.to_numeric(identity[FORMAL_TARGET_COLUMN], errors="coerce")
        mismatch = ~(observed.eq(raw) | (observed.isna() & raw.isna()))
        if int(mismatch.sum()):
            raise ValueError("PART_ADV_M1_LABEL_IDENTITY_MISMATCH")
        validate_m1_target_mapping({model: FORMAL_TARGET_COLUMN for model in predictions["model_id"].unique()})
        inputs = {entry.get("input_hash") for entry in registry.get("artifacts", [])}
        if inputs and inputs != {upstream["overall_run_registry_hash"]}:
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
        "formal_target_column": FORMAL_TARGET_COLUMN,
        "all_m1_models_same_target": True,
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
        "m1_metrics": output / "m1" / "m1_model_metrics.parquet",
        "downstream": output / "m1" / "m1_downstream_results.parquet",
        "m2_results": output / "m2" / "m2_sensitivity_results.parquet",
        "m4_metrics": output / "m4" / "m4_variant_metrics.parquet",
    }
    missing = [label for label, path in required.items() if not path.exists()]
    figures_regenerated = False
    if not missing:
        from .pipeline_common import _part_adv_figures
        _part_adv_figures(
            output,
            pd.read_parquet(required["m1_metrics"]),
            pd.read_parquet(required["downstream"]),
            pd.read_parquet(required["m2_results"]),
            pd.read_parquet(required["m4_metrics"]),
        )
        figures_regenerated = True

    result = json.loads(summary_path.read_text(encoding="utf-8"))
    result["figures_regenerated"] = figures_regenerated
    if missing:
        result["figure_missing_inputs"] = missing
    return result


