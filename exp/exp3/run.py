"""Official Exp3 full-Development execution entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq

from exp.common.official_execution import (
    load_json,
    load_official_frozen_binding,
    repository_root,
    require_active_path,
    require_development_safety,
    require_files,
)
from exp.exp3.global_development import run as run_global_development
from exp.reporting.output_contract import (
    validate_artifacts,
    write_experiment_artifacts,
)
from model.common.errors import ContractError


EXP2_ROOT = Path("artifacts/experiments/exp2/full_development_v1")
INPUT_ROOT = Path("artifacts/experiment/full_development_inputs_v1")
OUTPUT_ROOT = Path("artifacts/experiments/exp3/full_development_v1")
DEFERRED_REASON = "EXP3_VARIANTS_DEFERRED_OPTIONAL_BY_USER_20260824_NOT_IN_PAPER"


def _metric_rows_from_exp3_metrics(
    metrics_payload: dict,
    action_risk_path: Path | None,
) -> list[dict]:
    episode_count = int(metrics_payload.get("episode_count", 0))

    def row(metric_id, value, support, reason=None, condition="DEVELOPMENT"):
        return {
            "experiment": "EXP3",
            "variant": "EXP3A",
            "metric_id": metric_id,
            "value": value,
            "support": support,
            "reason": reason,
            "condition": condition,
            "n_episodes": episode_count,
        }

    rows = []
    finite = metrics_payload.get("finite_support_rate_mean")
    rows.append(row(
        "FINITE_SUPPORT_RATE", finite,
        "PARTIAL" if finite is not None else "NOT_RUN",
        reason=None if finite is not None else "FINITE_SUPPORT_RATE_UNAVAILABLE",
    ))
    agreement = metrics_payload.get("conditional_top1_response_sensitivity_agreement") or {}
    for band in ("LOW", "HIGH"):
        band_value = agreement.get(band)
        rows.append(row(
            "CONDITIONAL_TOP1_RESPONSE_AGREEMENT", band_value,
            "SUPPORTED" if band_value is not None else "NOT_RUN",
            reason=None if band_value is not None else f"AGREEMENT_{band}_UNAVAILABLE",
            condition=band,
        ))
    scale = metrics_payload.get("global_constructed_eur_scale_sensitivity") or {}
    invariance = scale.get("ranking_invariance")
    n_scales = len(scale.get("scales") or ())
    rows.append(row(
        "GLOBAL_CONSTRUCTED_EUR_SCALE_INVARIANCE",
        1.0 if invariance == "MATHEMATICALLY_INVARIANT_UNDER_COMMON_POSITIVE_SCALE" else 0.0,
        "SUPPORTED",
        reason=invariance,
        condition=f"SCALES={n_scales}",
    ))
    if action_risk_path is not None and action_risk_path.is_file():
        table = pq.read_table(action_risk_path, columns=["conditional_residual_risk"])
        values = [
            value for value in table.column("conditional_residual_risk").to_pylist()
            if value is not None
        ]
        risk_mean = sum(values) / len(values) if values else None
        rows.append(row(
            "PER_ACTION_CONDITIONAL_RISK_MEAN", risk_mean,
            "PARTIAL" if risk_mean is not None else "NOT_RUN",
            reason=None if risk_mean is not None else "NO_CONDITIONAL_RISK_ROWS",
            condition="FINITE_SUPPORT_ROWS",
        ))
    else:
        rows.append(row(
            "PER_ACTION_CONDITIONAL_RISK_MEAN", None, "NOT_RUN",
            reason="ACTION_RISK_PARQUET_UNAVAILABLE",
            condition="FINITE_SUPPORT_ROWS",
        ))
    formal = metrics_payload.get("formal_complete_chain") or {}
    rows.append(row(
        "FORMAL_COMPLETE_CHAIN", None, "NOT_RUN",
        reason=formal.get("reason") or "FORMAL_COMPLETE_CHAIN_GATED",
    ))
    for metric_id in (
        "ONE_SHOT_ANCHOR", "RECOMMENDATION_EXECUTABLE_RATE",
        "TOP1_ACTION_AGREEMENT", "EXPOST_MODEL_IMPLIED_RESIDUAL_RISK",
    ):
        rows.append(row(metric_id, None, "NOT_RUN", reason=DEFERRED_REASON))
    return rows


def _write_output_contract(
    *,
    root: Path,
    output_root: Path,
    frozen,
    metrics_path: Path,
    action_risk_path: Path,
    scenario_count: int = 250,
) -> dict:
    payload = load_json(metrics_path)
    rows = _metric_rows_from_exp3_metrics(payload, action_risk_path)
    definitions = {
        "EXP3A": {
            "variant_id": "EXP3A",
            "subexperiment": "EXP3A",
            "changed_factor": "5-anchor conditional diagnostic",
            "fixed_factor": ("cohort", "scenario_seed", "registry_hash"),
            "claim_scope": "CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
        },
    }
    cohort = {
        "dataset_id": payload.get("dataset", "DATA2"),
        "split": payload.get("split", "DEVELOPMENT"),
        "episode_count": payload.get("episode_count", 0),
        "node_count": payload.get("node_count", 0),
        "scenario_count_per_node": scenario_count,
        "seed": 0,
    }
    write_experiment_artifacts(
        experiment_id="EXP3",
        output_root=output_root,
        metric_rows=rows,
        cohort=cohort,
        variants=("EXP3A",),
        variant_definitions=definitions,
        frozen_hashes=frozen.as_dict(),
        config_hash=payload.get("artifact_hash", ""),
        interpretation=(
            "Exp3 evaluates the conditional 5-anchor constructed-EUR diagnostic "
            "on the frozen Data2 Development cohort (128 episodes, 1769 nodes, "
            "23 actions, 250 scenarios per node). The main table reports "
            "finite-support coverage, top-1 response agreement across sensitivity "
            "bands, ranking invariance under a common positive scale, and the "
            "per-action conditional-risk mean. The complete seven-component "
            "monetary ranking and all ablation variants stay NOT_RUN/"
            "DEFERRED_OPTIONAL and occupy no main-table row; their reasons are "
            "preserved in the metrics CSV and summary."
        ),
        claim_scope="CONDITIONAL_DIAGNOSTIC_5_ANCHOR_SUBSET_NOT_PRINCIPAL",
        limitations=(
            "formal_authoritative_ranking stays NOT_RUN at the human monetary-anchor gate.",
            "Exp3 variants/ablations (MODULE_REMOVAL_*, ROLLING, ONE_SHOT, SYNC, "
            "LAG_*) are DEFERRED_OPTIONAL by user decision 2026-08-24 and are not "
            "in the paper.",
            "constructed monetary scale, not empirical cost; ranking is not "
            "optimal/not regret; P_itinerary/P_service are event counts only "
            "(monetary NOT_ANCHORED).",
            "Per-action conditional risk detail lives in EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet.",
        ),
        omega_insight=(
            "The conditional diagnostic is stable under a common positive scale "
            "with high finite-support coverage, but operational action value "
            "requires the frozen seven-component monetary anchors."
        ),
        condition_of={"EXP3A": "DEVELOPMENT"},
        root=root,
    )
    return validate_artifacts("EXP3", output_root)


def _validate_existing(root: Path, output_root: Path) -> dict:
    manifest_path = output_root / "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    required = (
        manifest_path,
        output_root / "EXP3_FULL_DEVELOPMENT_METRICS.json",
        output_root / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
        output_root / "EXP3_FULL_DEVELOPMENT_TABLE.csv",
        output_root / "EXP3_FULL_DEVELOPMENT_INTERPRETATION.md",
    )
    require_files(required, code="EXP3_OFFICIAL_OUTPUT_MISSING")
    manifest = load_json(manifest_path)
    require_development_safety(manifest, label="EXP3_OFFICIAL")
    if manifest.get("dataset") != "DATA2" or manifest.get("split") != "DEVELOPMENT":
        raise ContractError("EXP3_OFFICIAL_DATA_BOUNDARY_INVALID")
    if (manifest.get("episode_count"), manifest.get("node_count"), manifest.get("action_count")) != (128, 1769, 23):
        raise ContractError("EXP3_OFFICIAL_CARDINALITY_INVALID")
    if manifest.get("safety", {}).get("AUTHORITATIVE_RANKING") is not False:
        raise ContractError("EXP3_OFFICIAL_AUTHORITATIVE_RANKING_FORBIDDEN")
    return {
        "status": "EXP3_OFFICIAL_READY",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "episode_count": 128, "node_count": 1769, "action_count": 23,
        "formal_decision_status": "NOT_RUN",
        "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Exp3 on the frozen Data2 Development cohort.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--finalize-output", action="store_true")
    parser.add_argument("--response-scenario-limit", type=int)
    parser.add_argument("--exp2-root", type=Path)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    root = repository_root()
    frozen = load_official_frozen_binding(root)
    exp2_root = require_active_path((args.exp2_root or root / EXP2_ROOT), root)
    input_root = require_active_path((args.input_root or root / INPUT_ROOT), root)
    output_root = require_active_path((args.output_root or root / OUTPUT_ROOT), root)
    if args.check:
        if (output_root / "exp3_summary.json").is_file():
            output_contract_state = validate_artifacts("EXP3", output_root)
        else:
            output_contract_state = "NOT_RUN"
        print(json.dumps({
            "status": "EXP3_OFFICIAL_PREFLIGHT_PASS",
            "frozen_hashes": frozen.as_dict(),
            "formal_authoritative_ranking": "NOT_RUN",
            "output_contract": output_contract_state,
            "FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False,
        }, sort_keys=True))
        return 0
    if args.resume and (output_root / "EXP3_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json").is_file():
        print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
        return 0
    if args.finalize_output:
        state = _validate_existing(root, output_root)
        state["output_contract"] = _write_output_contract(
            root=root, output_root=output_root, frozen=frozen,
            metrics_path=output_root / "EXP3_FULL_DEVELOPMENT_METRICS.json",
            action_risk_path=output_root / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
            scenario_count=250,
        )
        print(json.dumps(state, sort_keys=True))
        return 0
    run_global_development(
        root=root, exp2_root=exp2_root, input_root=input_root,
        output_root=output_root,
        response_scenario_limit=args.response_scenario_limit,
    )
    _write_output_contract(
        root=root, output_root=output_root, frozen=frozen,
        metrics_path=output_root / "EXP3_FULL_DEVELOPMENT_METRICS.json",
        action_risk_path=output_root / "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet",
        scenario_count=250,
    )
    print(json.dumps(_validate_existing(root, output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
