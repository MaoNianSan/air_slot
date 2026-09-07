"""Fixed-capacity Exp4 Development execution."""

import argparse
import json
import numpy as np
import pandas as pd
from exp.shared.analytical import scores, validate_development
from exp.shared.resampling import bootstrap_plan, episode_ids
from exp.shared.output import ROOT, GUARDS, digest, manifest, write_json, with_intervals
from .triage import (
    prepare_canonical_events,
    evaluate_screening,
    bootstrap_screening,
    robust_sets,
    robust_missed_nodes,
)

SHARED_INPUT = ROOT / "artifacts/experiment/shared/development/SHARED_DEVELOPMENT_INPUTS.parquet"


def run(mode, input_path=SHARED_INPUT):
    frame = pd.read_parquet(input_path)
    validate_development(frame)
    if mode == "fast":
        frame = frame[frame.original_episode_id.isin(episode_ids(frame)[:8])]
    frame = scores(frame)
    output = ROOT / "artifacts/experiment/exp4" / ("development" if mode == "development" else "fast")
    output.mkdir(parents=True, exist_ok=True)
    reps = 2000 if mode == "development" else 20
    write_json(output / "EXP4_OUTPUT_MANIFEST.json", {
        "status": "RUNNING", "bootstrap_replicates_required": reps,
        "bootstrap_replicates_completed": 0, **GUARDS})
    plan = bootstrap_plan(episode_ids(frame), reps)
    np.save(output / "EXP4_BOOTSTRAP_DRAWS.npy", plan)
    events, _ = prepare_canonical_events(frame)
    events.to_parquet(output / "EXP4_CANONICAL_EVENTS.parquet", index=False)
    result, evidence = evaluate_screening(events, evidence=True)
    evidence.to_csv(output / "EXP4_PARETO_EVIDENCE.csv", index=False)
    membership = pd.concat(
        [robust_sets(events, threshold) for threshold in (3, 4, 5)],
        ignore_index=True,
    )
    membership.to_csv(output / "EXP4_ROBUST_MEMBERSHIP.csv", index=False)
    membership[membership.m.eq(4)].to_csv(
        output / "EXP4_ROBUST_HIGH_CONSEQUENCE.csv", index=False
    )
    robust_missed_nodes(events, threshold=4).to_csv(
        output / "EXP4_ROBUST_MISSED_NODES.csv", index=False
    )
    boot = bootstrap_screening(frame, plan=plan)
    boot.to_csv(output / "EXP4_BOOTSTRAP.csv", index=False)
    result = with_intervals(result, boot, ["stage", "q"])
    result.to_csv(output / "EXP4_SCREENING_RESULTS.csv", index=False)
    keys = ["stage", "q", "status", "n", "k"]
    result[keys].to_csv(output / "EXP4_BUDGET_COHORTS.csv", index=False)
    result[
        [c for c in result if c in keys or "Capture" in c]
    ].to_csv(output / "EXP4_CAPTURE.csv", index=False)
    result[
        [c for c in result if c in keys or "Pareto" in c]
    ].to_csv(output / "EXP4_PARETO_RESULTS.csv", index=False)
    families = {
        "ROBUSTNESS_SUMMARY": [c for c in result if "robust" in c or "Miss" in c],
        "DOMAIN_CAPTURE": [c for c in result if any(
            c.startswith(p) for p in ("Capture_D_F", "Capture_C_F", "Delta_Capture_F_pp",
                                      "Capture_D_P", "Capture_C_P", "Delta_Capture_P_pp",
                                      "Capture_D_R", "Capture_C_R", "Delta_Capture_R_pp"))
                          and not any(x in c for x in ("continuity", "execution", "propagation",
                                                       "time", "itinerary", "service", "operating"))],
        "NATIVE_COMPONENT_CAPTURE": [c for c in result if "Capture" in c and any(
            x in c for x in ("continuity", "execution", "propagation", "time", "itinerary", "service", "operating"))],
        "DELTA_CAPTURE": [c for c in result if "Delta_Capture" in c],
        "PARETO_SUMMARY": [c for c in result if "Pareto" in c],
        "TIE_AUDIT": [c for c in result if "boundary_tie" in c],
    }
    for name, columns in families.items():
        result[keys + columns].to_csv(output / f"EXP4_{name}.csv", index=False)
    write_json(output / "EXP4_ANALYSIS_CONTRACT.json", {
        "schema_version": "EXP4_DEVELOPMENT_CONTRACT_V1",
        "experiment_id": "EXP4",
        "canonical_rule": "first_chronological_node_then_primary_support_evaluation",
        "unsupported_canonical_policy": "typed_exclusion_without_later_replacement",
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "budget_cohort": "stage_stratified_supported_canonical_events",
        "capacities_q": [0.05, 0.10, 0.20, 0.30],
        "rounding": "ceil(q*N)",
        "robust_views": 8,
        "consensus_m_primary": 4,
        "consensus_m_sensitivity": [3, 5],
        "no_f_execution_authority": "exp.shared.recovery_priority.compute_no_f_execution_priority",
        "bootstrap": {
            "cluster": "original_episode_id",
            "replicates": reps,
            "seed": 20260906,
            "confidence_interval": "percentile_95",
            "replicate_rebuild": [
                "canonical_cohort",
                "support_eligibility",
                "K",
                "ranking",
                "selection_statistics",
            ],
        },
        **GUARDS,
    })
    write_json(output / "EXP4_INPUT_MANIFEST.json", {
        "schema_version": "EXP4_DEVELOPMENT_INPUT_MANIFEST_V1",
        "input_path": str(input_path),
        "input_hash": digest(input_path),
        "rows": int(len(frame)),
        "episodes": int(frame.original_episode_id.nunique()),
        "canonical_events": int(len(events)),
        "supported_canonical_events": int(
            (events.canonical_event_status == "SUPPORTED").sum()
        ),
        "excluded_canonical_events": int(
            (events.canonical_event_status != "SUPPORTED").sum()
        ),
        **GUARDS,
    })
    manifest_payload = manifest(output, "EXP4", mode, input_path, reps, boot.replicate.nunique(),
                                canonical_event_count=len(events),
                                excluded_canonical_event_count=int((events.canonical_event_status != "SUPPORTED").sum()))
    return manifest_payload


def materialize_existing(input_path=SHARED_INPUT):
    """Publish required Development files from an already completed run."""
    output = ROOT / "artifacts/experiment/exp4/development"
    existing = json.loads((output / "EXP4_OUTPUT_MANIFEST.json").read_text(encoding="utf-8"))
    if existing.get("status") != "DEVELOPMENT_COMPLETE" or existing.get("bootstrap_replicates_completed") != 2000:
        raise RuntimeError("EXP4_EXISTING_DEVELOPMENT_NOT_COMPLETE")
    events = pd.read_parquet(output / "EXP4_CANONICAL_EVENTS.parquet")
    result = pd.read_csv(output / "EXP4_SCREENING_RESULTS.csv")
    membership = pd.concat(
        [robust_sets(events, threshold) for threshold in (3, 4, 5)],
        ignore_index=True,
    )
    membership.to_csv(output / "EXP4_ROBUST_MEMBERSHIP.csv", index=False)
    membership[membership.m.eq(4)].to_csv(output / "EXP4_ROBUST_HIGH_CONSEQUENCE.csv", index=False)
    robust_missed_nodes(events, threshold=4).to_csv(output / "EXP4_ROBUST_MISSED_NODES.csv", index=False)
    keys = ["stage", "q", "status", "n", "k"]
    result[keys].to_csv(output / "EXP4_BUDGET_COHORTS.csv", index=False)
    result[[c for c in result if c in keys or "Capture" in c]].to_csv(output / "EXP4_CAPTURE.csv", index=False)
    result[[c for c in result if c in keys or "Pareto" in c]].to_csv(output / "EXP4_PARETO_RESULTS.csv", index=False)
    write_json(output / "EXP4_ANALYSIS_CONTRACT.json", {
        "schema_version": "EXP4_DEVELOPMENT_CONTRACT_V1",
        "experiment_id": "EXP4",
        "canonical_rule": "first_chronological_node_then_primary_support_evaluation",
        "unsupported_canonical_policy": "typed_exclusion_without_later_replacement",
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "budget_cohort": "stage_stratified_supported_canonical_events",
        "capacities_q": [0.05, 0.10, 0.20, 0.30], "rounding": "ceil(q*N)",
        "robust_views": 8, "consensus_m_primary": 4, "consensus_m_sensitivity": [3, 5],
        "no_f_execution_authority": "exp.shared.recovery_priority.compute_no_f_execution_priority",
        "bootstrap": {"cluster": "original_episode_id", "replicates": 2000,
                       "seed": 20260906, "confidence_interval": "percentile_95",
                       "replicate_rebuild": ["canonical_cohort", "support_eligibility", "K", "ranking", "selection_statistics"]},
        **GUARDS,
    })
    frame = pd.read_parquet(input_path)
    write_json(output / "EXP4_INPUT_MANIFEST.json", {
        "schema_version": "EXP4_DEVELOPMENT_INPUT_MANIFEST_V1",
        "input_path": str(input_path), "input_hash": digest(input_path),
        "rows": int(len(frame)), "episodes": int(frame.original_episode_id.nunique()),
        "canonical_events": int(len(events)),
        "supported_canonical_events": int((events.canonical_event_status == "SUPPORTED").sum()),
        "excluded_canonical_events": int((events.canonical_event_status != "SUPPORTED").sum()), **GUARDS,
    })
    return manifest(output, "EXP4", "development", input_path, 2000, 2000,
                    canonical_event_count=len(events),
                    excluded_canonical_event_count=int((events.canonical_event_status != "SUPPORTED").sum()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("contract", "fast", "development", "materialize"), required=True)
    args = parser.parse_args()
    if args.mode == "materialize":
        result = materialize_existing()
    else:
        result = {"status": "CONTRACT_ONLY", **GUARDS} if args.mode == "contract" else run(args.mode)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
