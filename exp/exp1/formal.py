"""Formal Development Exp1 closure over frozen H16 artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from model.M1.cache import M1DevelopmentBaseCache
from model.M1.development_diagnostics import evaluate_lifecycle
from model.M1.lifecycle import M1Lifecycle

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "artifacts/models/m1"
PRE_AUDIT = ROOT / "artifacts/models/pre/PRE_FORMAL_DEVELOPMENT_V1/PRE_FORMAL_DEVELOPMENT_AUDIT.json"
CACHE_MANIFEST = MODEL / "M1_FROZEN_H16/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3_MANIFEST.json"
CACHE = MODEL / "M1_FROZEN_H16/DATA2_M1_V2_DEVELOPMENT_FAST_CACHE_V3.npz"
OUT = ROOT / "artifacts/experiment/exp1/development"


def _summary(result: dict, mode: str) -> dict:
    errors = []
    for node in result.get("nodes", []):
        for name in ("T_IB_REMAINING_HAZARD", "D_OB", "D_TX"):
            target = node.get("targets", {}).get(name)
            point = node.get("predictions", {}).get(
                "T_IB_A00_remaining_minutes_finite_support"
                if name == "T_IB_REMAINING_HAZARD"
                else f"{name}_point_minutes"
            )
            if target is not None and point is not None:
                errors.append(abs(float(point) - float(target)))
        node["history_mode"] = mode
    return {
        "mode": mode,
        "n_nodes": len(result.get("nodes", [])),
        "n_episodes": len({n["episode_id"] for n in result.get("nodes", [])}),
        "mae_minutes": None if not errors else sum(errors) / len(errors),
        "p90_absolute_error_minutes": None if not errors else float(pd.Series(errors).quantile(.90)),
        "crps_minutes": result.get("crps_minutes"),
        "crps_scope": result.get("crps_scope"),
    }


def run(mode: str = "development") -> dict:
    pre = json.loads(PRE_AUDIT.read_text(encoding="utf-8"))
    if pre.get("status") != "PASS" or pre.get("cache_nodes_missing_prestate") != 0:
        return {"status": "BLOCKED", "reason": "EXP1_FORMAL_PRE_AUDIT_NOT_PASS", "final_test_access_count": 0, "paper_result": False}
    manifest = json.loads(CACHE_MANIFEST.read_text(encoding="utf-8"))
    cache = M1DevelopmentBaseCache.load(CACHE, CACHE_MANIFEST, expected_cache_key=manifest["cache_key"])
    history = M1Lifecycle.load(MODEL / "M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY.pt", device="cpu")
    current = M1Lifecycle.load(MODEL / "M1_H16_CURRENT_COMPARATOR/M1_H16_CURRENT_COMPARATOR.pt", device="cpu")
    history_result = evaluate_lifecycle(history, tuple(cache.partition("development", representation="ADAPTIVE_HISTORY")), batch_size=64)
    current_result = evaluate_lifecycle(current, tuple(cache.partition("development", representation="CURRENT")), batch_size=64)
    rows = [_summary(history_result, "H16_HISTORY"), _summary(current_result, "H16_CURRENT")]
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT / "EXP1_HISTORY_CURRENT_SUMMARY.csv", index=False)
    result = {
        "status": "PASS",
        "experiment_id": "EXP1",
        "mode": mode,
        "matched_node_count": int(pre["matched_node_count"]),
        "history_current": rows,
        "evaluation_lead_minutes": [0, 30, 60, 120, 180, 240, 300, 360, 420, 480],
        "lead_time_slice_status": "NOT_RUN_TARGET_ARTIFACT_HAS_NO_LEAD_TIME_AXIS",
        "representation_status": "NOT_RUN_M2_SCENARIO_INTERFACE_NOT_EXPOSED_IN_FROZEN_ARTIFACT",
        "downstream_native_distortion_status": "NOT_RUN_M2_SCENARIO_INTERFACE_NOT_EXPOSED_IN_FROZEN_ARTIFACT",
        "bootstrap_replicates": 2000,
        "bootstrap_seed": 20260906,
        "final_test_access_count": 0,
        "paper_result": False,
        "model_retrained": False,
        "calibration_refit": False,
        "parameter_reselected": False,
    }
    (OUT / "EXP1_OUTPUT_MANIFEST.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
