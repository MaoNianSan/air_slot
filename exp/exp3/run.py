"""Stage-specific Development uncertainty and paired stage contrasts."""

import argparse
import json
import numpy as np
import pandas as pd
from exp.shared.analytical import scores, validate_development
from exp.shared.resampling import bootstrap_plan, episode_ids
from exp.shared.output import ROOT, GUARDS, digest, write_json, manifest, with_intervals
from .analysis import (
    SHARED_INPUT, METRICS, evaluate_stages, stage_contrasts,
    common_episode_cohort, bootstrap_stage_fast,
)


def run(mode, input_path=SHARED_INPUT):
    data = pd.read_parquet(input_path)
    validate_development(data)
    if mode == "fast":
        data = data[data.original_episode_id.isin(episode_ids(data)[:8])]
    data = scores(data)
    output = ROOT / "artifacts/experiment/exp3" / ("development" if mode == "development" else "fast")
    output.mkdir(parents=True, exist_ok=True)
    reps = 2000 if mode == "development" else 20
    write_json(output / "EXP3_OUTPUT_MANIFEST.json", {"status": "RUNNING", "bootstrap_replicates_required": reps,
                                                     "bootstrap_replicates_completed": 0, **GUARDS})
    plan = bootstrap_plan(episode_ids(data), reps)
    np.save(output / "EXP3_BOOTSTRAP_DRAWS.npy", plan)
    estimate = evaluate_stages(data)
    bootstrap = bootstrap_stage_fast(data, plan=plan)
    bootstrap.to_csv(output / "EXP3_BOOTSTRAP.csv", index=False)
    result = with_intervals(estimate, bootstrap, ["stage"], METRICS)
    result.to_csv(output / "EXP3_STAGE_AGREEMENT.csv", index=False)
    contrasts = stage_contrasts(estimate)
    contrast_draws = pd.concat([
        stage_contrasts(group).assign(replicate=replicate)
        for replicate, group in bootstrap.groupby("replicate")
    ], ignore_index=True)
    contrast_draws.to_csv(output / "EXP3_STAGE_CONTRAST_BOOTSTRAP.csv", index=False)
    with_intervals(contrasts, contrast_draws, ["stage_a", "stage_b"]).to_csv(
        output / "EXP3_STAGE_CONTRASTS.csv", index=False)
    pd.concat([evaluate_stages(data, c) for c in (5., 10., 15.)]).to_csv(
        output / "EXP3_STAGE_HETEROGENEITY.csv", index=False)
    common = common_episode_cohort(data)
    if not common.empty:
        cb = bootstrap_stage_fast(common, reps)
        cb.to_csv(output / "EXP3_COMMON_EPISODE_BOOTSTRAP.csv", index=False)
        with_intervals(evaluate_stages(common), cb, ["stage"], METRICS).to_csv(
            output / "EXP3_COMMON_EPISODE_ROBUSTNESS.csv", index=False)
    else:
        write_json(output / "EXP3_COMMON_EPISODE_ROBUSTNESS.json", {"status": "ABSTAIN_EMPTY_COMMON_COHORT"})
    estimate[[c for c in (
        "stage", "n_episodes", "n_nodes", "support_coverage", "status",
        "caliper_minutes", "heterogeneity_status",
    ) if c in estimate]].to_csv(output / "EXP3_STAGE_COHORT.csv", index=False)
    estimate[[c for c in (
        "stage", "candidate_pairs", "balanced_episode_pairs", "matched_episodes",
        "match_coverage", "heterogeneity_status", "caliper_minutes",
    ) if c in estimate]].to_csv(output / "EXP3_MATCH_COVERAGE.csv", index=False)
    write_json(output / "EXP3_ANALYSIS_CONTRACT.json", {
        "schema_version": "EXP3_DEVELOPMENT_CONTRACT_V1",
        "experiment_id": "EXP3",
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "primary_cohort_rule": [
            "support_primary == True",
            "conditional_aggregate_complete == True",
        ],
        "heterogeneity_estimand": "same_stage_abs_consequence_priority_percentile_gap",
        "secondary_heterogeneity_field": "score_C_gap",
        "active_stages": list(data.operational_stage.dropna().astype(str).unique()),
        "bootstrap": {
            "cluster": "original_episode_id",
            "replicates": reps,
            "seed": 20260906,
            "confidence_interval": "percentile_95",
            "replicate_rebuild": ["cohort", "stage_rank", "top10", "similar_delay_pairs"],
        },
        **GUARDS,
    })
    write_json(output / "EXP3_INPUT_MANIFEST.json", {
        "schema_version": "EXP3_DEVELOPMENT_INPUT_MANIFEST_V1",
        "input_path": str(input_path),
        "input_hash": digest(input_path),
        "rows": int(len(data)),
        "episodes": int(data.original_episode_id.nunique()),
        "stages": sorted(data.operational_stage.dropna().astype(str).unique()),
        **GUARDS,
    })
    return manifest(output, "EXP3", mode, input_path, reps, bootstrap.replicate.nunique(),
                    common_episode_count=common.original_episode_id.nunique())


def materialize_existing(input_path=SHARED_INPUT):
    """Publish required Development metadata from an already completed run."""
    output = ROOT / "artifacts/experiment/exp3/development"
    manifest_path = output / "EXP3_OUTPUT_MANIFEST.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    if existing.get("status") != "DEVELOPMENT_COMPLETE" or existing.get("bootstrap_replicates_completed") != 2000:
        raise RuntimeError("EXP3_EXISTING_DEVELOPMENT_NOT_COMPLETE")
    data = scores(pd.read_parquet(input_path))
    estimate = evaluate_stages(data)
    estimate[[c for c in (
        "stage", "n_episodes", "n_nodes", "support_coverage", "status",
        "caliper_minutes", "heterogeneity_status",
    ) if c in estimate]].to_csv(output / "EXP3_STAGE_COHORT.csv", index=False)
    estimate[[c for c in (
        "stage", "candidate_pairs", "balanced_episode_pairs", "matched_episodes",
        "match_coverage", "heterogeneity_status", "caliper_minutes",
    ) if c in estimate]].to_csv(output / "EXP3_MATCH_COVERAGE.csv", index=False)
    write_json(output / "EXP3_ANALYSIS_CONTRACT.json", {
        "schema_version": "EXP3_DEVELOPMENT_CONTRACT_V1",
        "experiment_id": "EXP3",
        "support_policy_id": "COMMON_SUPPORT_CONDITIONAL_090",
        "primary_cohort_rule": ["support_primary == True", "conditional_aggregate_complete == True"],
        "heterogeneity_estimand": "same_stage_abs_consequence_priority_percentile_gap",
        "bootstrap": {"cluster": "original_episode_id", "replicates": 2000,
                       "seed": 20260906, "confidence_interval": "percentile_95",
                       "replicate_rebuild": ["cohort", "stage_rank", "top10", "similar_delay_pairs"]},
        **GUARDS,
    })
    write_json(output / "EXP3_INPUT_MANIFEST.json", {
        "schema_version": "EXP3_DEVELOPMENT_INPUT_MANIFEST_V1",
        "input_path": str(input_path), "input_hash": digest(input_path),
        "rows": int(len(data)), "episodes": int(data.original_episode_id.nunique()),
        "stages": sorted(data.operational_stage.dropna().astype(str).unique()), **GUARDS,
    })
    return manifest(output, "EXP3", "development", input_path, 2000, 2000,
                    common_episode_count=common_episode_cohort(data).original_episode_id.nunique())


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
