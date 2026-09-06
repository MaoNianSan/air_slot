"""Exp2 contract and Development execution entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from .bootstrap import percentile_interval, run_bootstrap
from .development_inputs import materialize_h16_development_inputs
from .figures import component_figure, priority_figure
from .informativeness import informativeness_population, informativeness_table
from .model_inputs import active_model_contract, load_explicit_node_inputs
from .priority import (
    add_domain_scores,
    base_sample,
    rank_base_sample,
    summarize_priority,
)
from .protocol import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
    COMMON_SUPPORT_RULE_ID,
    COMMON_SUPPORT_SEMANTICS,
    COMPONENTS,
    FAST_BOOTSTRAP_REPLICATES,
    FINAL_TEST_ACCESS_COUNT,
    FULL_SUPPORT_THRESHOLD,
    PRIMARY_SUPPORT_THRESHOLD,
    SENSITIVITY_SUPPORT_THRESHOLD,
    SIMILAR_DELAY_PRIMARY,
    SIMILAR_DELAY_SENSITIVITY,
)
from .reporting import support_audit, write_frame, write_json
from .robustness import no_f_execution
from .similar_delay import (
    aggregate_episode_pairs,
    build_similar_delay_pairs,
    summarize_episode_pairs,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "artifacts" / "experiment" / "exp2" / "development"


def _head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def contract_payload() -> dict[str, object]:
    frozen, _, scope = active_model_contract()
    return {
        "schema_version": "EXP2_ANALYSIS_CONTRACT_V1",
        "status": "COMMON_SUPPORT_CONTRACT_PASS_DEVELOPMENT_INPUT_PENDING",
        "scientific_design": "AirSlot_EXP2_PRIORITY_DIVERGENCE_DESIGN_V1_20260906.md",
        "head": _head(),
        "repository_baseline_in_instruction": "9729354261de2a23c82b2e02350ba84aaba6dab7",
        "components": list(COMPONENTS),
        "m2_registry_id": frozen.registry_id,
        "m2_registry_hash": frozen.registry_hash,
        "m2_scope_hash": scope.scope_hash,
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "cluster": "episode",
            "ci": "percentile_95",
        },
        "common_support": {
            "rule_id": COMMON_SUPPORT_RULE_ID,
            "semantics": COMMON_SUPPORT_SEMANTICS,
            "conditional_estimand": COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
            "historical_semantic_source": (
                "Historical Exp1 closure diagnostic common-supported S_i with "
                "thresholds 0.90 and 0.50."
            ),
            "historical_implementation": (
                "Count fraction under 250 uniform frozen scenarios; superseded."
            ),
            "historical_source_blob": "755569e43b381d3151b5679e539bc4a72bf611e4",
            "current_migration": "Sum scenario weights over common support.",
            "analysis_level_conditional": True,
            "m2_formal_support_rule_unchanged": True,
        },
        "final_test_access_count": FINAL_TEST_ACCESS_COUNT,
        "paper_result": False,
    }


def write_contract_artifacts() -> dict[str, object]:
    frozen, _, _ = active_model_contract()
    contract = contract_payload()
    contract_dir = OUTPUT / "contract"
    write_json(contract_dir / "EXP2_ANALYSIS_CONTRACT.json", contract)
    common_contract = {
        "rule_id": COMMON_SUPPORT_RULE_ID,
        "rule_version": "V1",
        "historical_source_blob": "755569e43b381d3151b5679e539bc4a72bf611e4",
        "historical_rule": "count_fraction_on_uniform_250_scenarios",
        "migration_rule": "scenario_weight_support_mass",
        "primary_threshold": PRIMARY_SUPPORT_THRESHOLD,
        "sensitivity_threshold": SENSITIVITY_SUPPORT_THRESHOLD,
        "full_support_threshold": FULL_SUPPORT_THRESHOLD,
        "current_scenario_count_expected": 64,
        "scenario_count_is_not_part_of_formula": True,
        "current_m2_registry_id": frozen.registry_id,
        "current_m2_registry_hash": frozen.registry_hash,
        "current_m1_primary_lineage": {
            "model_version": "M1_STATE_ESTIMATOR_V2_H16",
            "manifest": "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY_MANIFEST.json",
            "checkpoint_hash": "sha256:061c3540c38ad8272982590de437d27064d50b1e023b55b672e77392d2c4ac3b",
            "development_cohort_hash": "sha256:79c3dd9d47e3ec6f15f228213f69bf84f40e8b8f5b6bb7fbea390fbe5613af79",
        },
        "analysis_level_conditional": True,
        "conditional_estimand": COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
        "m2_formal_support_rule_unchanged": True,
        "zero_fill": False,
        "model_retrained": False,
        "calibration_refit": False,
        "final_test_access_count": 0,
    }
    write_json(contract_dir / "EXP2_COMMON_SUPPORT_CONTRACT.json", common_contract)
    write_json(
        contract_dir / "EXP2_SUPPORT_MIGRATION_AUDIT.json",
        {
            "historical_scenario_count": 250,
            "historical_count_status": "SUPERSEDED_IMPLEMENTATION",
            "current_scenario_count": 64,
            "migrated_scientific_quantity": "SCENARIO_WEIGHT_SUPPORT_MASS",
            "thresholds_preserved": [0.90, 0.50],
            "model_support_rule_changed": False,
            "model_scientific_definition_changed": False,
            "final_test_access_count": 0,
            "status": "PASS",
        },
    )
    write_json(
        contract_dir / "EXP2_MODEL_REUSE_AUDIT.json",
        {
            "head": _head(),
            "active_m1_primary": "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY_MANIFEST.json",
            "active_m2_registry": frozen.registry_id,
            "active_seven_component_scope": list(frozen.formal_scope),
            "development_input_sources": [],
            "status": "COMMON_SUPPORT_CONTRACT_PASS_DEVELOPMENT_INPUT_PENDING",
            "final_test_access_count": 0,
            "model_retrained": False,
            "calibration_refit": False,
            "model_scientific_definition_changed": False,
            "parameter_reselected": False,
        },
    )
    write_json(
        contract_dir / "EXP2_COMPONENT_SCALES.json",
        {
            "registry_id": frozen.registry_id,
            "registry_hash": frozen.registry_hash,
            "scales": {component: frozen.scale(component) for component in COMPONENTS},
            "source": "TRAIN_2019_H1_FROZEN",
            "final_test_access_count": 0,
        },
    )
    return contract


def _ci(replicates: list[dict[str, object]], section: str, key: str):
    values = [item[section].get(key) for item in replicates]
    return percentile_interval(values)


def execute_node_materialization(
    source: pd.DataFrame, *, fast: bool
) -> dict[str, object]:
    rows = add_domain_scores(source)
    informativeness_source = informativeness_population(rows)
    sample = rank_base_sample(base_sample(rows))
    sensitivity_sample = rank_base_sample(
        base_sample(rows, support_column="support_sensitivity")
    )
    full_sample = rank_base_sample(
        base_sample(
            rows,
            support_column="support_full",
            completeness_column="formal_full_support",
        )
    )
    if fast:
        episode_ids = tuple(sorted(sample["episode_id"].astype(str).unique()))[:8]
        sample = sample.loc[sample["episode_id"].astype(str).isin(episode_ids)].copy()
        sample = rank_base_sample(sample.reset_index(drop=True))
    if len(sample) < 2:
        raise RuntimeError("BLOCK_EXP2_BASE_SAMPLE_INSUFFICIENT")

    priority = summarize_priority(sample)
    sensitivity = (
        summarize_priority(sensitivity_sample)
        if len(sensitivity_sample) >= 2
        else {"status": "ABSTAIN_INSUFFICIENT_SUPPORT", "n_nodes": len(sensitivity_sample)}
    )
    full_support = (
        summarize_priority(full_sample)
        if len(full_sample) >= 2
        else {"status": "ABSTAIN_INSUFFICIENT_SUPPORT", "n_nodes": len(full_sample)}
    )
    information = informativeness_table(informativeness_source)
    pair_frames = {
        caliper: build_similar_delay_pairs(sample, caliper=caliper)
        for caliper in (SIMILAR_DELAY_PRIMARY, *SIMILAR_DELAY_SENSITIVITY)
    }
    episode_pair_frames = {
        caliper: aggregate_episode_pairs(frame)
        for caliper, frame in pair_frames.items()
    }
    similar_summary = {
        str(int(caliper)): summarize_episode_pairs(frame)
        for caliper, frame in episode_pair_frames.items()
    }
    _, robustness = no_f_execution(sample)
    bootstrap_replicates = FAST_BOOTSTRAP_REPLICATES if fast else BOOTSTRAP_REPLICATES
    bootstrap = run_bootstrap(
        sample,
        replicates=bootstrap_replicates,
        seed=BOOTSTRAP_SEED,
        caliper=SIMILAR_DELAY_PRIMARY,
        informativeness_frame=informativeness_source,
    )

    for key in (
        "kendall_tau_b",
        "median_rank_displacement",
        "p90_rank_displacement",
        "share_rank_displacement_ge_030",
        "top_overlap",
    ):
        priority[f"{key}_ci_low"], priority[f"{key}_ci_high"] = _ci(
            bootstrap, "priority", key
        )
        robustness[f"{key}_ci_low"], robustness[f"{key}_ci_high"] = _ci(
            bootstrap, "robustness", key
        )
    for index, info_row in information.iterrows():
        low, high = percentile_interval(
            [item["informativeness"].get(info_row["quantity_id"]) for item in bootstrap]
        )
        information.loc[index, ["ci_low", "ci_high"]] = [low, high]

    primary_episode_pairs = episode_pair_frames[SIMILAR_DELAY_PRIMARY]
    primary_summary = similar_summary[str(int(SIMILAR_DELAY_PRIMARY))]
    for key in (
        "median_priority_separation",
        "share_priority_separation_ge_030",
        *(f"median_component_gap_{component}" for component in COMPONENTS),
    ):
        low, high = _ci(bootstrap, "similar_delay", key)
        primary_summary[f"{key}_ci_low"] = low
        primary_summary[f"{key}_ci_high"] = high

    component_gaps = pd.DataFrame(
        [
            {
                "component_id": component,
                "estimate": primary_summary.get(f"median_component_gap_{component}"),
                "ci_low": primary_summary.get(
                    f"median_component_gap_{component}_ci_low"
                ),
                "ci_high": primary_summary.get(
                    f"median_component_gap_{component}_ci_high"
                ),
            }
            for component in COMPONENTS
        ]
    )
    pair_counts = {
        "5_min_qualifying_node_pairs": int(len(pair_frames[5.0])),
        "5_min_unique_episode_pairs": int(len(episode_pair_frames[5.0])),
        "10_min_unique_episode_pairs": int(len(episode_pair_frames[10.0])),
        "15_min_unique_episode_pairs": int(len(episode_pair_frames[15.0])),
    }
    audit = support_audit(
        rows,
        sample,
        pair_counts,
        {
            "delay_boundary_tie_count": int(priority["delay_boundary_tie_count"]),
            "consequence_boundary_tie_count": int(
                priority["consequence_boundary_tie_count"]
            ),
        },
    )

    data_dir = OUTPUT / "data"
    results_dir = OUTPUT / "results"
    figures_dir = OUTPUT / "figures"
    write_frame(data_dir / "EXP2_PRIORITY_BASE.parquet", sample)
    write_frame(data_dir / "EXP2_COMMON_SUPPORT_NODE_SUMMARY.parquet", rows)
    write_frame(data_dir / "EXP2_SIMILAR_DELAY_PAIRS.parquet", pair_frames[5.0])
    write_frame(data_dir / "EXP2_EPISODE_PAIR_SUMMARY.parquet", primary_episode_pairs)
    write_frame(results_dir / "EXP2_OVERALL_PRIORITY.csv", pd.DataFrame([priority]))
    write_frame(results_dir / "EXP2_COMPONENT_INFORMATIVENESS.csv", information)
    write_frame(
        results_dir / "EXP2_SIMILAR_DELAY_SUMMARY.csv",
        pd.DataFrame(
            [
                {"caliper_minutes": key, **value}
                for key, value in similar_summary.items()
            ]
        ),
    )
    write_frame(
        results_dir / "EXP2_ROBUSTNESS.csv",
        pd.DataFrame(
            [
                {"robustness_id": "NO_F_EXECUTION", **robustness},
                {"robustness_id": "SUPPORT_50", **sensitivity},
                {"robustness_id": "FULL_SUPPORT_100", **full_support},
            ]
        ),
    )
    diagnostics = {
        "status": "NON_PAPER_FAST_DIAGNOSTIC" if fast else "DEVELOPMENT_ONLY",
        "bootstrap_replicates": bootstrap_replicates,
        "support_audit": audit,
        "final_test_access_count": 0,
        "paper_result": False,
    }
    write_json(results_dir / "EXP2_DIAGNOSTICS.json", diagnostics)
    write_json(
        results_dir / "EXP2_DEVELOPMENT_SUMMARY.json",
        {
            "exp2a": priority,
            "exp2b": information.to_dict(orient="records"),
            "exp2c": similar_summary,
            "no_f_execution": robustness,
            "support_50_sensitivity": sensitivity,
            "full_support_100": full_support,
            **diagnostics,
        },
    )
    if not fast:
        priority_figure(sample, figures_dir / "FIG2_PRIORITY_DIVERGENCE_DEV.pdf")
        component_figure(
            information,
            component_gaps,
            figures_dir / "FIG3_COMPONENT_EVIDENCE_DEV.pdf",
        )
    manifest = {
        "schema_version": "EXP2_DEVELOPMENT_MANIFEST_V1",
        "status": diagnostics["status"],
        "head": _head(),
        "bootstrap_replicates": bootstrap_replicates,
        "final_test_access_count": 0,
        "model_retrained": False,
        "calibration_refit": False,
        "model_scientific_definition_changed": False,
        "parameter_reselected": False,
        "paper_result": False,
    }
    write_json(OUTPUT / "EXP2_MANIFEST.json", manifest)
    return {"manifest": manifest, "support_audit": audit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("contract", "materialize", "fast", "development"),
        required=True,
    )
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    contract = write_contract_artifacts()
    if args.mode == "contract":
        print(json.dumps(contract, sort_keys=True))
        return 0
    if args.mode == "materialize":
        result = materialize_h16_development_inputs()
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    if args.input is None:
        raise RuntimeError("BLOCK_EXP2_DEVELOPMENT_INPUT_MISSING")
    source = load_explicit_node_inputs(args.input)
    result = execute_node_materialization(source, fast=args.mode == "fast")
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
    COMMON_SUPPORT_RULE_ID,
    COMMON_SUPPORT_SEMANTICS,
