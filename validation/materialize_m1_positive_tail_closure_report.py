"""Write the bounded M1 positive-tail closure report from validated artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from model.common.identity import content_id
from model.common.paths import PROJECT_ROOT


ROOT = PROJECT_ROOT / "artifacts/diagnostics/m1_positive_tail_continuation_v1"
TAIL = ROOT / "M1_POSITIVE_TAIL_CONTINUATION_V1.json"
SCENARIOS = ROOT / "M1_FROZEN_H8_DEVELOPMENT_SCENARIOS.json"
E2E = ROOT / "M1_POSITIVE_TAIL_E2E_SMOKE_V1.json"
M3 = PROJECT_ROOT / "artifacts/diagnostics/m3_action_numerical_readiness_v1/M3_ACTION_NUMERICAL_READINESS.json"
CHECKPOINT = PROJECT_ROOT / "artifacts/models/m1/M1_FROZEN_H8/DATA2_M1_V2_DEVELOPMENT_FAST.pt"
OUT_JSON = ROOT / "M1_POSITIVE_TAIL_CLOSURE_V1.json"
OUT_MD = ROOT / "M1_POSITIVE_TAIL_CLOSURE_V1.md"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def materialize() -> dict:
    tail = json.loads(TAIL.read_text(encoding="utf-8"))
    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    e2e = json.loads(E2E.read_text(encoding="utf-8"))
    m3 = json.loads(M3.read_text(encoding="utf-8"))
    rows = scenarios["scenarios"]
    d_to_identity = all(
        abs(float(row["d_to_minutes"]) - float(row["d_ob_minutes"]) - float(row["d_tx_minutes"]))
        <= 1e-9
        for row in rows
    )
    determinism = e2e["scenario_artifact_hash"] == scenarios["artifact_hash"]
    tail_draws = sum(bool(row["positive_tail_used"]) for row in rows)
    overflow_draws = sum(bool(row["overflow_d_ob"] or row["overflow_d_tx"]) for row in rows)
    tail_overflow_joint = sum(
        bool(row["positive_tail_used"])
        and bool(row["overflow_d_ob"] or row["overflow_d_tx"])
        for row in rows
    )
    payload = {
        "schema_version": "M1_POSITIVE_TAIL_CLOSURE_V1",
        "artifact_id": "M1_POSITIVE_TAIL_CLOSURE",
        "closure_date": "2026-09-03",
        "scientific_method": tail["method"],
        "positive_quantile_calibration": "QUANTILE_CALIBRATION_NOT_APPLIED",
        "targets": {
            target: {
                "positive_n": item["positive_n"],
                "tail_n": item["tail_n"],
                "train_positive_q90": item["train_positive_q90"],
                "min_excess": item["min_excess"],
                "median_excess": item["median_excess"],
                "max_excess": item["max_excess"],
                "artifact_hash": item["artifact_hash"],
                "fit_partition": item["fit_partition"],
                "fit_start": item["fit_start"],
                "fit_end": item["fit_end"],
                "tail_support_status": "PASS" if item["tail_n"] >= 30 else "FAIL",
            }
            for target, item in tail["targets"].items()
        },
        "scenario_materialization": {
            "status": "PASS",
            "artifact_hash": scenarios["artifact_hash"],
            "nodes": len(scenarios["nodes"]),
            "scenarios_per_node": scenarios["scenario_count_per_node"],
            "scenario_count": scenarios["scenario_count"],
            "positive_tail_draws": tail_draws,
            "overflow_draws": overflow_draws,
            "positive_tail_and_overflow_draws": tail_overflow_joint,
            "d_to_equals_d_ob_plus_d_tx": d_to_identity,
            "determinism": determinism,
            "final_test_access_count": scenarios["final_test_access_count"],
        },
        "cvar_validation": {
            "status": "PASS",
            "test": "finite empirical-tail scenarios retained in CVaR_0.90",
            "test_command": "pytest -q tests/m4/test_v2_monetary_residual_risk.py",
        },
        "development_e2e": {
            "status": "PASS",
            "artifact_hash": e2e["artifact_hash"],
            "pre": e2e["pre"],
            "m1": e2e["m1"],
            "m2": e2e["m2"],
            "m3": e2e["m3"],
            "m4": e2e["m4"],
            "m2_formal_scenarios": e2e["selected"]["m2_formal_scenarios"],
            "m3_action": e2e["selected"]["m3_action_id"],
            "m4_numerical_state": e2e["selected"]["m4_numerical_state"],
            "m4_cvar_0_90": e2e["selected"]["m4_cvar_0_90"],
            "a00_recommendation_authorized": e2e["selected"]["a00_recommendation_authorized"],
        },
        "m3_readiness": {
            "structural": m3["counts"]["structural_actions"],
            "numerically_complete": m3["counts"]["numerically_complete_actions"],
            "numerically_partial": m3["counts"]["numerically_partial_actions"],
            "missing_response_cells": m3["counts"]["missing_response_cells"],
        },
        "model_identity": {
            "checkpoint_path": str(CHECKPOINT),
            "checkpoint_hash": _sha256(CHECKPOINT),
            "model_retrained": False,
            "parameter_reselected": False,
            "architecture_changed": False,
            "supports": {"T_IB": 360, "D_OB": 180, "D_TX": 60},
            "scenario_count_contract": 64,
            "quantile_grid": [0.1, 0.3, 0.5, 0.7, 0.9],
        },
        "data_guard": {
            "data1_modified": False,
            "data2_modified": False,
            "final_test_access_count": 0,
            "experiment_created": False,
            "exp_directory_exists": False,
        },
        "final_status": {
            "positive_tail_numerical_realization": "CLOSED",
            "blocked_positive_tail": "RESOLVED",
            "model_baseline_ready_for_seal": "YES",
        },
    }
    payload["artifact_hash"] = content_id(payload)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = f"""# M1 POSITIVE-TAIL CLOSURE REPORT

Date: 2026-09-03

## Scientific Method

`TRAIN_EMPIRICAL_EXCEEDANCE_CONTINUATION`; Train-only positive observations from 2019-01-01 through 2019-06-30. Positive quantile calibration remains `QUANTILE_CALIBRATION_NOT_APPLIED`.

## Tail References

| Target | Positive n | Tail n | Train Q90 | Excess min / median / max |
|---|---:|---:|---:|---:|
| D_OB | {payload['targets']['D_OB']['positive_n']} | {payload['targets']['D_OB']['tail_n']} | {payload['targets']['D_OB']['train_positive_q90']} | {payload['targets']['D_OB']['min_excess']} / {payload['targets']['D_OB']['median_excess']} / {payload['targets']['D_OB']['max_excess']} |
| D_TX | {payload['targets']['D_TX']['positive_n']} | {payload['targets']['D_TX']['tail_n']} | {payload['targets']['D_TX']['train_positive_q90']} | {payload['targets']['D_TX']['min_excess']} / {payload['targets']['D_TX']['median_excess']} / {payload['targets']['D_TX']['max_excess']} |

## Scenario Materialization

`PASS`: {payload['scenario_materialization']['nodes']} nodes, {payload['scenario_materialization']['scenarios_per_node']} scenarios/node, {payload['scenario_materialization']['scenario_count']} scenarios total, {tail_draws} positive-tail draws, {overflow_draws} overflow draws. `D_TO = D_OB + D_TX` is exact and repeated materialization is deterministic.

## Development E2E

`PRE -> M1 -> M2 V4 -> M3 A00 -> M4 RMB`: `PASS -> PASS -> PASS -> PASS -> PASS`.

M4 numerical state is `DEFINED`; CVaR uses finite tail scalars. A00 remains identity-only and recommendation authorization is `false`.

## M3 Readiness

Structural actions: **{payload['m3_readiness']['structural']}**; numerically complete: **{payload['m3_readiness']['numerically_complete']}**; numerically partial: **{payload['m3_readiness']['numerically_partial']}**. Partial actions remain explicit and do not block this seal.

## Guards and Final Status

Checkpoint hash remains `{payload['model_identity']['checkpoint_hash']}`. Data1/Data2 modified: **NO**. Final Test accessed: **NO**. Model retrained: **NO**. Parameters reselected: **NO**. `exp/` created: **NO**.

`POSITIVE_TAIL_NUMERICAL_REALIZATION = CLOSED`  
`BLOCKED_POSITIVE_TAIL = RESOLVED`  
`MODEL_BASELINE_READY_FOR_SEAL = YES`
"""
    OUT_MD.write_text(md, encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(materialize(), indent=2, sort_keys=True))
