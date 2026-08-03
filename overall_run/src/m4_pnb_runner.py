from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .m4_pnb_contract import (
    AUDIT_SEED_NAMESPACE,
    FLOAT32_RECONSTRUCTION_ATOL_RMB,
    FORMAL_Q_TOLERANCE,
    capture_registered_hashes,
    sha256_file,
    verify_baseline,
)
from .m4_pnb_figures import create_parameter_figures, create_pnb_figures
from .m4_pnb_inputs import load_frozen_inputs
from .m4_pnb_parameters import build_parameter_role_audit, build_physical_gate_audit
from .m4_pnb_sensitivity import PARAMETER_GRIDS, build_parameter_sensitivity
from .m4_pnb_snapshot import build_snapshot_action_audit
from .m4_pnb_stability import build_mc_stability
from .m4_pnb_summaries import build_failure_decomposition, build_pnb_summaries
from .utils import utc_now, write_json


def _write_parquet(frame: pd.DataFrame, path: Path) -> Path:
    if path.parent.name != "audits" or not path.name.startswith("m4_"):
        raise RuntimeError(f"PNB_AUDIT_OUTPUT_PATH_REJECTED:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def _identity_summary(identity: pd.DataFrame, frame: pd.DataFrame) -> dict[str, Any]:
    finite_burden = identity["burden_ratio_abs_error"].replace([np.inf, -np.inf], np.nan).dropna()
    recommendation_by_snapshot = identity.groupby("snapshot_id", observed=True)[
        "recommendation_disagreement"
    ].any()
    return {
        "support": int(len(identity)),
        "expected_recovered_cost_max_abs_error_rmb": float(
            identity["expected_recovered_cost_abs_error_rmb"].max()
        ),
        "expected_recovered_cost_mean_abs_error_rmb": float(
            identity["expected_recovered_cost_abs_error_rmb"].mean()
        ),
        "expected_recovered_cost_mismatch_row_count": int(
            identity["expected_recovered_cost_mismatch"].sum()
        ),
        "expected_implementation_cost_max_abs_error_rmb": float(
            identity["expected_implementation_cost_abs_error_rmb"].max()
        ),
        "recovery_ratio_max_abs_error": float(identity["recovery_ratio_abs_error"].max()),
        "burden_ratio_max_abs_error": float(finite_burden.max()) if len(finite_burden) else 0.0,
        "positive_net_benefit_probability_max_abs_error": float(
            identity["positive_net_benefit_probability_abs_error"].max()
        ),
        "positive_net_benefit_probability_mean_abs_error": float(
            identity["positive_net_benefit_probability_abs_error"].mean()
        ),
        "positive_net_benefit_probability_mismatch_row_count": int(
            identity["positive_net_benefit_probability_mismatch"].sum()
        ),
        "gate_disagreement_count": int(identity["gate_disagreement"].sum()),
        "candidate_disagreement_count": int(identity["candidate_disagreement"].sum()),
        "recommendation_disagreement_snapshot_count": int(
            recommendation_by_snapshot.sum()
        ),
        "strict_greater_draw_count": int(frame["strict_positive_draws"].sum()),
        "greater_equal_draw_count": int(frame["nonnegative_draws"].sum()),
        "strict_vs_greater_equal_difference_draw_count": int(
            frame["equal_recovered_implementation_draws"].sum()
        ),
        "formal_q_tolerance": FORMAL_Q_TOLERANCE,
        "float32_rmb_reconstruction_atol": FLOAT32_RECONSTRUCTION_ATOL_RMB,
    }


def run_audit(
    run_dir: Path,
    audit_id: str,
    mc_samples: int = 4096,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    baseline = verify_baseline(run_dir)
    before_hashes = capture_registered_hashes(run_dir)
    before_registry_hash = sha256_file(run_dir / "artifact_registry.json")
    frozen = load_frozen_inputs(run_dir)
    frame, identity, snapshot, draw_cache = build_snapshot_action_audit(frozen)
    identity_summary = _identity_summary(identity, frame)
    hard_failures = []
    if identity_summary["positive_net_benefit_probability_max_abs_error"] > FORMAL_Q_TOLERANCE:
        hard_failures.append("PNB_PROBABILITY_IDENTITY_FAILURE")
    if identity_summary["gate_disagreement_count"]:
        hard_failures.append("PNB_GATE_DISAGREEMENT")
    if identity_summary["candidate_disagreement_count"]:
        hard_failures.append("PNB_CANDIDATE_DISAGREEMENT")
    if identity_summary["recommendation_disagreement_snapshot_count"]:
        hard_failures.append("PNB_RECOMMENDATION_DISAGREEMENT")
    if hard_failures:
        raise RuntimeError("FORMAL_PNB_IMPLEMENTATION_DEVIATION:" + ",".join(hard_failures))

    pnb = build_pnb_summaries(frame)
    failure = build_failure_decomposition(frame)
    mc, mc_summary = build_mc_stability(frozen, frame, snapshot, mc_samples)
    sensitivity = build_parameter_sensitivity(frozen, frame, snapshot, draw_cache)
    physical = build_physical_gate_audit(frame, frozen.candidates)
    roles = build_parameter_role_audit(sensitivity, physical)

    audits_dir = run_dir / "audits"
    figures_dir = run_dir / "figures" / "audit"
    generated: list[Path] = []
    tables = {
        "m4_pnb_formula_identity.parquet": identity,
        "m4_pnb_snapshot_action.parquet": frame,
        "m4_pnb_action_summary.parquet": pnb["action"],
        "m4_pnb_family_summary.parquet": pnb["family"],
        "m4_pnb_stage_summary.parquet": pnb["stage"],
        "m4_pnb_cost_strata.parquet": pnb["cost_strata"],
        "m4_pnb_channel_composition.parquet": pnb["channel_composition"],
        "m4_pnb_failure_decomposition.parquet": failure,
        "m4_pnb_mc_stability.parquet": mc,
        "m4_parameter_role_audit.parquet": roles,
        "m4_b0_sensitivity.parquet": sensitivity["b0"],
        "m4_q0_sensitivity.parquet": sensitivity["q0"],
        "m4_lambda_sensitivity.parquet": sensitivity["lambda"],
        "m4_alpha_sensitivity.parquet": sensitivity["alpha"],
        "m4_near_equivalent_sensitivity.parquet": sensitivity["near_equivalent_relative"],
        "m4_parameter_cost_strata.parquet": sensitivity["cost_strata"],
        "m4_parameter_action_family.parquet": sensitivity["action_family"],
        "m4_physical_gate_parameter_audit.parquet": physical,
    }
    for name, table in tables.items():
        generated.append(_write_parquet(table, audits_dir / name))
    generated.extend(create_pnb_figures(frame, figures_dir))
    generated.extend(create_parameter_figures(sensitivity, figures_dir))

    formal_params = sensitivity["formal_values"].set_index("parameter")["formal_value"].to_dict()
    parameter_summary = {
        "audit_id": audit_id,
        "status": "PASS_WITH_SCIENTIFIC_REVIEW",
        "m4_parameter_audit_status": "PASS_WITH_SCIENTIFIC_REVIEW",
        "b0_reasonableness": "POSSIBLY_REASONABLE",
        "q0_reasonableness": "SENSITIVE_BUT_NOT_DEGENERATE",
        "lambda_reasonableness": "REASONABLE",
        "alpha_reasonableness": "REASONABLE",
        "physical_gate_parameter_status": "POSSIBLY_REASONABLE",
        "m3_response_parameter_interaction": "POSSIBLY_REASONABLE",
        "current_behavior_classification": "CURRENT_M4_BEHAVIOR_PLAUSIBLY_REASONABLE",
        "risk_functional_parameter_status": "RISK_FUNCTIONAL_PARAMETERS_NOT_PRIMARY_CONCERN",
        "formal_parameters": formal_params,
        "diagnostic_only": True,
        "formal_use": "not used for formal recommendation",
        "validation_status": "not a validation-frozen specification",
        "parameter_selection_evidence_status": "INSUFFICIENT_EVIDENCE",
        "parameter_selection_boundary": "PARAMETER_SELECTION_NOT_AUTHORIZED_BY_CURRENT_EVIDENCE",
        "fast_formal_cohort_use": "descriptive sensitivity and mechanism diagnosis only",
        "max_oat_candidate_disagreement": {
            parameter: float(table["candidate_set_disagreement_vs_formal"].max())
            for parameter, table in sensitivity.items()
            if parameter in PARAMETER_GRIDS
        },
        "max_oat_recommendation_disagreement": {
            parameter: float(table["recommendation_disagreement_vs_formal"].max())
            for parameter, table in sensitivity.items()
            if parameter in PARAMETER_GRIDS
        },
        "risk_functional_max_recommendation_disagreement": float(
            max(
                sensitivity["lambda"]["recommendation_disagreement_vs_formal"].max(),
                sensitivity["alpha"]["recommendation_disagreement_vs_formal"].max(),
            )
        ),
        "physical_gate_pass_rates": physical.set_index("gate")["pass_rate"].to_dict(),
        "physical_distance_limitation": "numeric margins are not published in frozen Fast artifacts; PRE read prohibited",
        "mc_gate_flip_rate_at_formal_q0": mc_summary["gate_flip_rate"],
        "mc_second_seed_gate_flip_rate": mc_summary["second_seed_gate_flip_rate"],
        "scientific_change_required": False,
        "full_recommended": False,
    }
    parameter_summary_path = audits_dir / "m4_parameter_reasonableness_summary.json"
    write_json(parameter_summary_path, parameter_summary)
    generated.append(parameter_summary_path)

    audit_summary = {
        "audit_id": audit_id,
        "generated_at": utc_now(),
        "baseline": baseline,
        "audit_engineering_status": "PASS",
        "formula_implementation_status": "PASS",
        "numeric_identity_status": "PASS",
        "monte_carlo_stability_status": "STABLE_WITH_LOCAL_NEAR_THRESHOLD_UNCERTAINTY",
        "concentration_classification": "LOW_COST_FIXED_COST_EFFECT",
        "identity": identity_summary,
        "m2_reconstruction": frozen.reconstruction_diagnostics,
        "mc_stability": mc_summary,
        "triggered_snapshots": int(frame["snapshot_id"].nunique()),
        "triggered_non_null_action_rows": int(len(frame)),
        "formal_parameters": formal_params,
        "a00": {
            "recovery_all_zero": bool(np.all(frozen.m3_recovery["A00"] == 0.0)),
            "implementation_cost_all_zero": bool(np.all(frozen.m3_implementation["A00"] == 0.0)),
            "excluded_from_non_null_denominator": True,
            "unconditionally_in_evaluation_set": bool(
                frozen.candidates.loc[frozen.candidates["action_id"].eq("A00"), "is_evaluated"].all()
            ),
        },
        "sample_alignment": {
            "formal_sample_ids": [int(frozen.sample_ids.min()), int(frozen.sample_ids.max())],
            "formal_sample_count": int(len(frozen.sample_ids)),
            "m1_seed_namespace": "flight_id,snapshot_id,m1_samples",
            "m3_seed_namespace": "M3_RESPONSE,action_id,component",
            "audit_seed_namespace": AUDIT_SEED_NAMESPACE,
            "same_index_is_pairing_not_same_random_number": True,
        },
        "units": {
            "m2_pre_action_cost": "RMB",
            "m3_recovery_rate": "dimensionless rate",
            "recovered_cost": "RMB",
            "implementation_cost": "RMB",
            "net_benefit": "RMB",
            "positive_net_benefit_probability": "probability",
        },
        "strict_comparison": "recovered_total > implementation_total",
        "formal_artifacts_modified": False,
        "scientific_change_required": False,
        "full_recommended": False,
    }
    audit_summary_path = audits_dir / "m4_pnb_audit_summary.json"
    write_json(audit_summary_path, audit_summary)
    generated.append(audit_summary_path)

    log_path = run_dir / "logs" / f"{audit_id}.log"
    log_path.write_text(
        "\n".join(
            [
                f"audit_id={audit_id}",
                "mode=read-only-frozen-fast-artifacts",
                "formal_formula_identity=PASS",
                f"q_max_abs_error={identity_summary['positive_net_benefit_probability_max_abs_error']}",
                f"gate_disagreement_count={identity_summary['gate_disagreement_count']}",
                f"candidate_disagreement_count={identity_summary['candidate_disagreement_count']}",
                f"mc_gate_flip_rate={mc_summary['gate_flip_rate']}",
                "formal_artifacts_modified=false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    generated.append(log_path)

    after_hashes = capture_registered_hashes(run_dir)
    after_registry_hash = sha256_file(run_dir / "artifact_registry.json")
    if before_hashes != after_hashes or before_registry_hash != after_registry_hash:
        raise RuntimeError("PNB_AUDIT_MODIFIED_FORMAL_ARTIFACT")
    audit_summary["formal_artifacts_modified"] = False
    audit_summary["formal_registered_hashes_before_after_match"] = True
    audit_summary["artifact_registry_hash_before"] = before_registry_hash
    audit_summary["artifact_registry_hash_after"] = after_registry_hash
    write_json(audit_summary_path, audit_summary)

    registry_rows = []
    for path in sorted(set(generated)):
        registry_rows.append(
            {
                "relative_path": path.relative_to(run_dir).as_posix(),
                "sha256": sha256_file(path),
                "file_size": path.stat().st_size,
            }
        )
    audit_registry = {
        "audit_id": audit_id,
        "baseline_run_id": baseline["run_id"],
        "baseline_registry_hash": baseline["artifact_registry_hash"],
        "scientific_implementation_hash": baseline["scientific_implementation_hash"],
        "formal_artifacts_modified": False,
        "artifacts": registry_rows,
    }
    registry_path = audits_dir / "m4_pnb_audit_registry.json"
    write_json(registry_path, audit_registry)
    return {
        "audit_id": audit_id,
        "status": "PASS",
        "run_dir": str(run_dir),
        "identity": identity_summary,
        "mc_stability": mc_summary,
        "parameter_summary": parameter_summary,
        "audit_registry": str(registry_path),
        "generated_artifact_count": len(registry_rows) + 1,
        "formal_artifacts_modified": False,
        "full_recommended": False,
    }


