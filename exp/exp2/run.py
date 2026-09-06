"""Exp2 contract and Development execution entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pandas as pd

from .bootstrap import percentile_interval, run_bootstrap
from .figures import component_figure, priority_figure
from .informativeness import informativeness_table
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
    COMPONENTS,
    FAST_BOOTSTRAP_REPLICATES,
    FINAL_TEST_ACCESS_COUNT,
    INHERITED_SUPPORT_BLOCK,
    INHERITED_SUPPORT_EXACT_SEMANTICS,
    INHERITED_SUPPORT_RULE_ID,
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
        "status": "CONTRACT_READY_DEVELOPMENT_INPUT_BLOCKED",
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
        "inherited_support": {
            "rule_id": INHERITED_SUPPORT_RULE_ID,
            "source_path": "HISTORICAL_GIT_BLOB:35e5258^:exp/exp1/closure.py",
            "source_blob": "755569e43b381d3151b5679e539bc4a72bf611e4",
            "exact_semantics": INHERITED_SUPPORT_EXACT_SEMANTICS,
            "current_executable_artifact": None,
            "status": INHERITED_SUPPORT_BLOCK,
        },
        "final_test_access_count": FINAL_TEST_ACCESS_COUNT,
        "paper_result": False,
    }


def write_contract_artifacts() -> dict[str, object]:
    frozen, _, _ = active_model_contract()
    contract = contract_payload()
    contract_dir = OUTPUT / "contract"
    write_json(contract_dir / "EXP2_ANALYSIS_CONTRACT.json", contract)
    write_json(
        contract_dir / "EXP2_MODEL_REUSE_AUDIT.json",
        {
            "head": _head(),
            "active_m1_primary": "artifacts/models/m1/M1_H16_HISTORY_PRIMARY/M1_H16_HISTORY_PRIMARY_MANIFEST.json",
            "active_m2_registry": frozen.registry_id,
            "active_seven_component_scope": list(frozen.formal_scope),
            "development_input_sources": [],
            "status": INHERITED_SUPPORT_BLOCK,
            "final_test_access_count": 0,
            "model_retrained": False,
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
    sample = rank_base_sample(base_sample(rows))
    if fast:
        episode_ids = tuple(sorted(sample["episode_id"].astype(str).unique()))[:8]
        sample = sample.loc[sample["episode_id"].astype(str).isin(episode_ids)].copy()
        sample = rank_base_sample(sample.reset_index(drop=True))
    if len(sample) < 2:
        raise RuntimeError("BLOCK_EXP2_BASE_SAMPLE_INSUFFICIENT")

    priority = summarize_priority(sample)
    information = informativeness_table(sample)
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
    write_frame(results_dir / "EXP2_ROBUSTNESS.csv", pd.DataFrame([robustness]))
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
        "model_scientific_definition_changed": False,
        "parameter_reselected": False,
        "paper_result": False,
    }
    write_json(OUTPUT / "EXP2_MANIFEST.json", manifest)
    return {"manifest": manifest, "support_audit": audit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("contract", "fast", "development"), required=True
    )
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    contract = write_contract_artifacts()
    if args.mode == "contract":
        print(json.dumps(contract, sort_keys=True))
        return 0
    if args.input is None:
        raise RuntimeError(INHERITED_SUPPORT_BLOCK)
    source = load_explicit_node_inputs(args.input)
    result = execute_node_materialization(source, fast=args.mode == "fast")
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
