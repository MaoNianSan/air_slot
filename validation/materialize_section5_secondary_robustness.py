"""Additive Section 5 uncertainty reporting from frozen Final Test artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from exp.exp2 import protocol
from exp.exp2.bootstrap import percentile_interval, run_bootstrap
from exp.exp2.priority import base_sample, rank_base_sample
from exp.exp2.similar_delay import (
    aggregate_episode_pairs,
    build_similar_delay_pairs,
    summarize_episode_pairs,
)
from exp.shared.resampling import bootstrap_plan, episode_ids


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = "860befd20e968ba702b1aad99e618830a3a6acfe"
FINAL = Path("artifacts/experiment/final_test")
OUTPUT = FINAL / "section5_secondary"
EXP2 = FINAL / "exp2"
EXP4 = FINAL / "exp4"
CALIPERS = (protocol.SIMILAR_DELAY_PRIMARY, *protocol.SIMILAR_DELAY_SENSITIVITY)
CAPACITIES = (0.05, 0.10, 0.20, 0.30)
POINT_KEYS = (
    "unique_episode_pairs",
    "median_priority_separation",
    "share_priority_separation_ge_030",
)
CI_KEYS = POINT_KEYS[1:]
CAPACITY_COLUMNS = (
    "stage", "q", "n", "k",
    "reassigned_rate", "reassigned_rate_ci_low", "reassigned_rate_ci_high",
    *(
        f"Delta_Capture_{domain}_pp{suffix}"
        for domain in ("F", "P", "R")
        for suffix in ("", "_ci_low", "_ci_high")
    ),
)
SOURCE_PATHS = {
    "nodes": EXP2 / "data/EXP2A_NODE_RECORDS.parquet",
    "similar": EXP2 / "results/EXP2_SIMILAR_DELAY_SUMMARY.csv",
    "robustness": EXP2 / "results/EXP2_ROBUSTNESS_SUMMARY.csv",
    "association": EXP2 / "results/EXP2B_COMPONENT_DOMAIN_SUMMARY.csv",
    "primary": EXP2 / "results/EXP2A_SUMMARY.csv",
    "primary_bootstrap": EXP2 / "results/EXP2C_BOOTSTRAP.csv",
    "exp2_manifest": EXP2 / "FINAL_TEST_EXP2_MANIFEST.json",
    "exp2_contract": EXP2 / "EXP2_ANALYSIS_CONTRACT.json",
    "exp2_input": EXP2 / "EXP2_INPUT_MANIFEST.json",
    "capacity": EXP4 / "EXP4_SCREENING_RESULTS.csv",
    "exp4_manifest": EXP4 / "FINAL_TEST_EXP4_MANIFEST.json",
}
OUTPUT_NAMES = (
    "SECTION5_EXP2_CALIPER_SENSITIVITY.csv",
    "SECTION5_EXP4_CAPACITY_SENSITIVITY.csv",
    "SECTION5_DELAY_LINKAGE_AUDIT.json",
    "SECTION5_SECONDARY_ROBUSTNESS_MANIFEST.json",
    "SECTION5_SECONDARY_ROBUSTNESS_REPORT.md",
    "SECTION5_EXP2_CALIPER_BOOTSTRAP.csv",
)
GUARDS = {
    "model_retrained": False,
    "calibration_refit": False,
    "parameter_reselected": False,
    "primary_scientific_object_changed": False,
    "new_primary_estimand": False,
    "final_test_secondary_derivation": True,
    "exp4_rerun": False,
    "final_test_cohort_rematerialized": False,
    "manuscript_modified": False,
    "raw_final_test_data_read": False,
}


def require(condition, reason):
    if not condition:
        raise RuntimeError(f"BLOCKED_SECTION5:{reason}")


def digest(path):
    with Path(path).open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args, root=ROOT):
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8"
    ).strip()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip")


def records(frame):
    return json.loads(frame.to_json(orient="records", double_precision=15))


def exact_records(frame):
    return [
        {key: None if pd.isna(value) else value for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def json_text(payload):
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def frozen_constants():
    return {
        key: getattr(protocol, key)
        for key in (
            "SIMILAR_DELAY_PRIMARY", "SIMILAR_DELAY_SENSITIVITY",
            "BOOTSTRAP_REPLICATES", "BOOTSTRAP_SEED",
            "PRIMARY_SUPPORT_THRESHOLD", "SENSITIVITY_SUPPORT_THRESHOLD",
            "FULL_SUPPORT_THRESHOLD", "MATERIAL_RANK_GAP",
        )
    }


def validate_constants():
    require(frozen_constants() == {
        "SIMILAR_DELAY_PRIMARY": 5.0,
        "SIMILAR_DELAY_SENSITIVITY": (10.0, 15.0),
        "BOOTSTRAP_REPLICATES": 2000,
        "BOOTSTRAP_SEED": 20260906,
        "PRIMARY_SUPPORT_THRESHOLD": 0.90,
        "SENSITIVITY_SUPPORT_THRESHOLD": 0.50,
        "FULL_SUPPORT_THRESHOLD": 1.0,
        "MATERIAL_RANK_GAP": 0.30,
    }, "FROZEN_CONSTANTS_CHANGED")


def protected_snapshot(root=ROOT):
    # Include ignored Final Test records and local model/calibration artifacts.
    paths = {
        root / name for name in git("ls-files", root=root).splitlines()
        if not name.startswith(OUTPUT.as_posix() + "/")
        and name not in (
            "validation/materialize_section5_secondary_robustness.py",
            "tests/validation/test_section5_secondary_robustness.py",
        )
    }
    for directory in (FINAL, Path("artifacts/models"), Path("artifacts/calibration")):
        paths.update(
            path for path in (root / directory).rglob("*")
            if path.is_file() and not path.is_relative_to(root / OUTPUT)
            and "__pycache__" not in path.parts
        )
    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(paths)
    }


def check_unchanged(before, root=ROOT):
    after = protected_snapshot(root)
    require(before == after, "PROTECTED_FILES_CHANGED")
    return after


def preflight(root=ROOT):
    validate_constants()
    head = git("rev-parse", "HEAD", root=root)
    require(not git("status", "--porcelain", "--untracked-files=no", root=root),
            "TRACKED_WORKTREE_DIRTY")
    for path in SOURCE_PATHS.values():
        require((root / path).is_file(), f"MISSING_FROZEN_SOURCE:{path}")
    if head != AUTHORITY:
        changed = git(
            "diff", "--name-only", AUTHORITY, head, "--", "exp", "model",
            "registries", "configs", "formal", FINAL.as_posix(), root=root,
        )
        require(not changed, f"AUTHORITY_CONTRACT_OR_ARTIFACT_CHANGED:{changed}")
    for key in ("exp2_manifest", "exp4_manifest"):
        manifest = read_json(root / SOURCE_PATHS[key])
        require(manifest["status"] == "FINAL_TEST_COMPLETE", key + ":STATUS")
        require(manifest["artifact_scope"] == "FINAL_TEST_ONLY", key + ":SCOPE")
        require(manifest["bootstrap_replicates"] == protocol.BOOTSTRAP_REPLICATES,
                key + ":REPLICATES")
        require(manifest["bootstrap_seed"] == protocol.BOOTSTRAP_SEED, key + ":SEED")
        require(manifest["final_test_access_count"] == 1, key + ":ACCESS_COUNT")
        for flag in ("model_retrained", "calibration_refit", "parameter_reselected"):
            require(manifest[flag] is False, key + ":" + flag)
    manifest = read_json(root / SOURCE_PATHS["exp2_manifest"])
    inner = manifest["scientific_result"]["manifest"]
    for relative, expected in inner["outputs"].items():
        path = (root / EXP2 / relative).resolve()
        require(path.is_relative_to((root / EXP2).resolve()), "SOURCE_PATH_ESCAPE")
        require(path.is_file() and digest(path) == expected,
                f"FROZEN_MANIFEST_HASH_MISMATCH:{relative}")
    contract = read_json(root / SOURCE_PATHS["exp2_contract"])
    require(contract["bootstrap"] == {
        "ci": "percentile_95", "cluster": "episode",
        "replicates": protocol.BOOTSTRAP_REPLICATES,
        "seed": protocol.BOOTSTRAP_SEED,
    }, "BOOTSTRAP_CONTRACT_CHANGED")
    require(tuple(contract["components"]) == protocol.COMPONENTS, "ONTOLOGY_CHANGED")
    require(contract["common_support"]["conditional_estimand"]
            == protocol.COMMON_SUPPORT_CONDITIONAL_ESTIMAND, "ESTIMAND_CHANGED")
    return head


def restore_ranked_sample(root=ROOT):
    stored = pd.read_parquet(root / SOURCE_PATHS["nodes"])
    sample = rank_base_sample(base_sample(stored))
    require(len(sample) == len(stored), "RANKED_POPULATION_CHANGED")
    require(not sample["decision_node_id"].duplicated().any(), "DUPLICATE_NODE_IDS")
    require(sample["decision_node_id"].equals(stored["decision_node_id"]),
            "NODE_ORDER_CHANGED")
    for key in ("delay_rank_pct", "consequence_rank_pct", "rank_displacement"):
        np.testing.assert_allclose(sample[key], stored[key], atol=1e-12, rtol=0)
    population = read_json(root / SOURCE_PATHS["exp2_input"])
    require(len(sample) == population["primary_sample_rows"], "NODE_COUNT_CHANGED")
    require(len(episode_ids(sample)) == population["primary_sample_episodes"],
            "EPISODE_COUNT_CHANGED")
    # Primary's bootstrap drew the union with Exp2B's independent population.
    # This frozen cohort has identical complete populations; never infer that
    # equivalence for a different source cohort.
    require(population["source_episodes"] == population["primary_sample_episodes"]
            and population["source_rows"] == population["exp2b_population_rows"]
            == population["primary_sample_rows"], "BOOTSTRAP_UNIVERSE_UNVERIFIED")
    return sample


def reconcile_points(points, frozen):
    require(len(points) == len(frozen) == 3, "CALIPER_ROW_COUNT")
    require(set(points.caliper_minutes) == set(frozen.caliper_minutes)
            == set(CALIPERS), "CALIPER_GRID")
    for caliper in CALIPERS:
        actual = points.loc[points.caliper_minutes.eq(caliper)].iloc[0]
        expected = frozen.loc[frozen.caliper_minutes.eq(caliper)].iloc[0]
        require(actual["support_status"] == expected["support_status"] == "SUPPORTED",
                f"CALIPER_SUPPORT:{caliper}")
        for key in POINT_KEYS:
            require(np.isfinite(actual[key]) and np.isfinite(expected[key])
                    and abs(actual[key] - expected[key]) <= 1e-12,
                    f"POINT_ESTIMATE_MISMATCH:{caliper}:{key}")


def rebuild_points(sample):
    summaries = []
    for caliper in CALIPERS:
        print(f"SECTION5 reference point reconstruction: {caliper:g} min", flush=True)
        pairs = build_similar_delay_pairs(sample, caliper=caliper)
        summary = summarize_episode_pairs(aggregate_episode_pairs(pairs))
        summaries.append({"caliper_minutes": caliper, **summary})
        print(f"SECTION5 point {caliper:g}: {summary}", flush=True)
        del pairs
    return pd.DataFrame(summaries)


def _bootstrap_chunk(args):
    frame, caliper, plan, offset = args
    # This is the frozen primary backend, not a bootstrap of stored pair gaps.
    # It rebuilds ranks, cross-original-episode occurrence pairs, within-pair
    # medians and pair-balanced summaries on every draw. Only immutable node
    # membership is cached by the existing Exp2 implementation.
    results = run_bootstrap(
        frame, replicates=len(plan), seed=protocol.BOOTSTRAP_SEED,
        caliper=caliper, plan=plan,
    )
    return [
        {"replicate": offset + index, "caliper_minutes": caliper,
         **result["similar_delay"]}
        for index, result in enumerate(results)
    ]


def bootstrap_calipers(sample, workers):
    plan = bootstrap_plan(
        episode_ids(sample), protocol.BOOTSTRAP_REPLICATES, protocol.BOOTSTRAP_SEED
    )
    chunk_size = 250
    jobs = [
        (sample, caliper, plan[offset:offset + chunk_size], offset)
        for caliper in CALIPERS
        for offset in range(0, len(plan), chunk_size)
    ]
    output = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(_bootstrap_chunk, jobs):
            output.extend(result)
            print(f"SECTION5 completed caliper-replicates: {len(output)}/6000",
                  flush=True)
    return pd.DataFrame(output).sort_values(
        ["caliper_minutes", "replicate"], kind="stable"
    ).reset_index(drop=True)


def attach_intervals(points, draws, frozen, primary_draws):
    require(len(draws) == 3 * protocol.BOOTSTRAP_REPLICATES, "DRAW_ROW_COUNT")
    require(set(draws.caliper_minutes) == set(CALIPERS), "DRAW_CALIPER_GRID")
    summary = points[["caliper_minutes", "support_status", *POINT_KEYS]].copy()
    for index, point in summary.iterrows():
        selected = draws.loc[draws.caliper_minutes.eq(point.caliper_minutes)]
        require(len(selected) == protocol.BOOTSTRAP_REPLICATES
                and set(selected.replicate) == set(range(protocol.BOOTSTRAP_REPLICATES)),
                "REPLICATE_IDS")
        require(selected.support_status.eq("SUPPORTED").all(),
                "ABSTAIN_BOOTSTRAP_REPLICATE")
        for key in CI_KEYS:
            require(np.isfinite(selected[key]).all(), "NONFINITE_BOOTSTRAP")
            low, high = percentile_interval(selected[key].tolist())
            summary.loc[index, key + "_ci_low"] = low
            summary.loc[index, key + "_ci_high"] = high
    rebuilt = draws.loc[draws.caliper_minutes.eq(CALIPERS[0])].sort_values("replicate")
    old = primary_draws.sort_values("replicate")
    require(len(old) == protocol.BOOTSTRAP_REPLICATES
            and old.replicate.tolist() == rebuilt.replicate.tolist(),
            "PRIMARY_DRAW_IDENTITIES_CHANGED")
    for key in POINT_KEYS:
        np.testing.assert_allclose(rebuilt[key], old[key], atol=1e-12, rtol=0)
    old_primary = frozen.loc[frozen.caliper_minutes.eq(CALIPERS[0])].iloc[0]
    for key in CI_KEYS:
        for suffix in ("_ci_low", "_ci_high"):
            require(abs(summary.iloc[0][key + suffix] - old_primary[key + suffix])
                    <= 1e-12, "PRIMARY_CI_MISMATCH:" + key + suffix)
    summary["bootstrap_replicates"] = protocol.BOOTSTRAP_REPLICATES
    summary["bootstrap_seed"] = protocol.BOOTSTRAP_SEED
    summary["bootstrap_cluster"] = "original_episode_id"
    summary["ci_method"] = "percentile_95"
    return summary


def capacity_projection(path):
    # Preserve the source CSV's field strings, including full precision and NA.
    with Path(path).open(newline="", encoding="utf-8") as stream:
        source = list(csv.DictReader(stream))
    require(bool(source), "EMPTY_CAPACITY_SOURCE")
    require(all(set(CAPACITY_COLUMNS) <= set(row) for row in source),
            "CAPACITY_COLUMNS_MISSING")
    stages = {row["stage"] for row in source}
    require(stages == set(protocol.ACTIVE_STAGES), "CAPACITY_STAGE_GRID")
    for stage in stages:
        rows = [row for row in source if row["stage"] == stage]
        require(len(rows) == 4 and {float(row["q"]) for row in rows}
                == set(CAPACITIES), "CAPACITY_GRID")
        require(len({row["n"] for row in rows}) == 1, "STAGE_COHORT_CHANGED")
        for row in rows:
            require(int(row["k"]) == math.ceil(float(row["q"]) * int(row["n"])),
                    "CAPACITY_K_CONTRACT")
    projected = [{key: row[key] for key in CAPACITY_COLUMNS} for row in source]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CAPACITY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(projected)
    return stream.getvalue()


def build_audit(summary, root=ROOT):
    robustness = read_csv(root / SOURCE_PATHS["robustness"])
    no_execution = robustness.loc[robustness.robustness_id.eq("NO_F_EXECUTION")]
    require(len(no_execution) == 1, "NO_F_EXECUTION_ROW_MISSING_OR_DUPLICATED")
    primary = read_csv(root / SOURCE_PATHS["primary"])
    require(len(primary) == 1, "PRIMARY_ROW_COUNT")
    association = read_csv(root / SOURCE_PATHS["association"])
    capacity = read_csv(root / SOURCE_PATHS["capacity"])
    abstentions = [
        {"stage": row["stage"], "q": row["q"], "field": column, "status": value}
        for row in exact_records(capacity)
        for column, value in row.items()
        if isinstance(value, str) and value.startswith(("ABSTAIN", "BLOCKED"))
    ]
    return {
        "schema_version": "SECTION5_DELAY_LINKAGE_AUDIT_V1",
        "status": "SECONDARY_REPORTING_COMPLETE_HUMAN_REVIEW_REQUIRED",
        "primary": {
            "source": SOURCE_PATHS["primary"].as_posix(),
            "source_note": "PRIMARY is absent from the robustness CSV; read the "
                           "manifest-tracked EXP2A_SUMMARY, not a support sensitivity.",
            "row": exact_records(primary)[0],
        },
        "no_f_execution": {
            "source": SOURCE_PATHS["robustness"].as_posix(),
            "selection": "robustness_id == NO_F_EXECUTION",
            "audit_row_recomputed": False,
            "new_definition": False,
            "row": exact_records(no_execution)[0],
        },
        "component_domain_association": {
            "source": SOURCE_PATHS["association"].as_posix(),
            "statistic": "Kendall tau-b",
            "rows": exact_records(association),
            "recomputed": False,
        },
        "similar_delay_heterogeneity": {
            "source": (OUTPUT / OUTPUT_NAMES[0]).as_posix(),
            "rows": exact_records(summary),
            "estimand": protocol.COMMON_SUPPORT_CONDITIONAL_ESTIMAND,
            "pair_rule": "same stage; different original episodes; episode-pair balanced",
        },
        "interpretation": {
            "observed": [
                "Strong delay association is present in several frozen consequence "
                "channels, especially F_propagation and F_execution.",
                "The existing NO_F_EXECUTION sensitivity retains substantial "
                "association and nonidentical priorities.",
                "Similar-delay comparisons retain consequence-priority separation "
                "under the unchanged primary consequence score.",
            ],
            "supported_reading": "These results are consistent with delay-linked "
                "consequence channels contributing to high overall association, "
                "while similar predicted delay severity need not imply identical "
                "consequence-based recovery priority. This evidence does not "
                "require removing delay from the primary consequence score.",
            "not_established": [
                "No causal decomposition or fraction of correlation attributable "
                "to any channel is identified.",
                "NO_F_EXECUTION is not a delay-free score: other channels retain "
                "their frozen delay dependence.",
                "A positive caliper permits residual delay differences; these "
                "comparisons do not prove exact-delay conditional independence.",
                "Wider calipers change the qualifying pair set; they are not "
                "new primary estimands or evidence of causal superiority.",
                "Screening capture describes allocation trade-offs, not uniformly "
                "improved capture in every domain or a causal recovery benefit.",
            ],
        },
        "delay_stripped_score_created": False,
        "remaining_blocked_items": [],
        "preserved_source_abstentions": abstentions,
        "human_gate": "Review secondary results before any manuscript edit.",
        **GUARDS,
    }


def cell(row, key, percent=False):
    scale = 100 if percent else 1
    return (
        f"{scale * row[key]:.4f} "
        f"[{scale * row[key + '_ci_low']:.4f}, "
        f"{scale * row[key + '_ci_high']:.4f}]"
    )


def report_text(summary, capacity, audit, manifest):
    lines = [
        "# Section 5 Secondary Robustness Report", "",
        "Status: SECONDARY_REPORTING_COMPLETE_HUMAN_REVIEW_REQUIRED", "",
        "Reporting-only derivation of the existing held-out Final Test. "
        "No model, calibration, weights, thresholds, primary estimand, canonical "
        "events, stage cohort, or manuscript was changed.", "",
        f"- HEAD_START: `{manifest['HEAD_START']}`",
        f"- HEAD_END: `{manifest['HEAD_END']}`",
        "- Frozen Final Test access count remains 1; no new raw-data opening.",
        "- All three point estimates reconcile at rtol=0, atol=1e-12.",
        "- All 2,000 primary 5-min bootstrap rows and headline CIs reconcile "
        "with their existing frozen counterparts.", "",
        "## Exp2 Similar-Delay Sensitivity", "",
        "| Caliper (min) | Episode pairs | Median separation [95% CI] | "
        "Share separation >= 0.30, % [95% CI] |",
        "|---:|---:|---:|---:|",
    ]
    for row in exact_records(summary):
        lines.append(
            f"| {row['caliper_minutes']:g} | {row['unique_episode_pairs']} | "
            f"{cell(row, CI_KEYS[0])} | {cell(row, CI_KEYS[1], True)} |"
        )
    lines += [
        "", "Bootstrap: original-episode clusters, 2,000 replicates, seed "
        "20260906, percentile 95% intervals. The complete ranked sample is "
        "restored from EXP2A_NODE_RECORDS; stored scores and common support are "
        "unchanged. Point reconstruction calls the existing pair builder, "
        "episode-pair aggregation, and summary functions.", "",
        "The existing primary optimized bootstrap backend caches only invariant "
        "qualifying node membership. Each draw rebuilds ranks and "
        "cross-original-episode bootstrap-occurrence pairs, recomputes node rank "
        "gaps and episode-pair medians, and then computes pair-balanced summaries. "
        "This is not resampling a frozen list of pair-level gaps. The original "
        "draw order is retained when execution is split into worker chunks. "
        "All calipers use the same frozen episode draw plan.", "",
        "## Exp4 Appendix Capacity Summary", "",
        "Exact source-field projection; Exp4 and its bootstrap were not rerun. "
        "Values below are display-rounded only. The CSV preserves every "
        "selected source field verbatim. Reassigned rate is shown as a fraction; "
        "capture differences are percentage points.", "",
        "| Stage | q | N | K | Reassigned rate [95% CI] | "
        "Delta Capture F (pp) [95% CI] | Delta Capture P (pp) [95% CI] | "
        "Delta Capture R (pp) [95% CI] |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in exact_records(capacity):
        lines.append(
            f"| {row['stage']} | {row['q']:.2f} | {row['n']} | {row['k']} | "
            + " | ".join(cell(row, key) for key in (
                "reassigned_rate", "Delta_Capture_F_pp", "Delta_Capture_P_pp",
                "Delta_Capture_R_pp",
            )) + " |"
        )
    lines += [
        "", "## Delay-Linkage Audit", "",
        "| Existing result | Kendall tau-b | Median rank displacement | "
        "Top-decile overlap |", "|---|---:|---:|---:|",
    ]
    for label, key in (("PRIMARY", "primary"), ("NO_F_EXECUTION", "no_f_execution")):
        row = audit[key]["row"]
        lines.append(f"| {label} | {row['kendall_tau_b']:.6f} | "
                     f"{row['median_rank_displacement']:.6f} | "
                     f"{row['top_overlap']:.6f} |")
    lines += [
        "", audit["primary"]["source_note"], "",
        "Component/domain associations below are the original frozen Kendall "
        "tau-b estimates, with their original uncertainty and population "
        "metadata retained in the audit JSON.", "",
        "| Component/domain | Kendall tau-b | 95% CI |",
        "|---|---:|---:|",
    ]
    for row in audit["component_domain_association"]["rows"]:
        lines.append(f"| {row['quantity_id']} | {row['estimate']:.6f} | "
                     f"[{row['ci_low']:.6f}, {row['ci_high']:.6f}] |")
    lines += [
        "", "### Reviewer-Facing Interpretation", "",
        audit["interpretation"]["supported_reading"], "",
        *["- " + text for text in audit["interpretation"]["not_established"]],
        "", "Delay dependence in F_execution, F_propagation, P_time, "
        "P_itinerary, P_service, and R_operating belongs to their consequence "
        "semantics. Mechanically deleting these components would change the "
        "scientific object. No such score, new weighting, or new threshold is "
        "introduced here. Eq. (7)-(8) remain unchanged.", "",
        "## Provenance and Boundaries", "",
        *[f"- `{key}={str(value).lower()}`" for key, value in GUARDS.items()],
        f"- Protected files verified unchanged: "
        f"{manifest['protected_file_count']}.",
        "- Remaining execution BLOCKED items: none.",
        f"- Source component-level ABSTAIN cells retained: "
        f"{len(audit['preserved_source_abstentions'])}; see audit JSON. "
        "Undefined/zero-denominator capture is not replaced with zero.",
        "- Manuscript integration: HUMAN_DECISION_REQUIRED. Stop here.", "",
        "## Output Hashes", "",
        *[f"- `{name}`: `{value}`"
          for name, value in manifest["output_artifact_hashes"].items()],
        "", "The manifest records the report hash. Its own hash is external "
        "to avoid a self-referential checksum.", "",
    ]
    return "\n".join(lines)


def materialize(root=ROOT, workers=4):
    require(1 <= workers <= 8, "WORKER_COUNT_OUT_OF_BOUNDS")
    head_start = preflight(root)
    output = root / OUTPUT
    require(not output.exists(), "SECONDARY_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
    before = protected_snapshot(root)
    sample = restore_ranked_sample(root)
    frozen = read_csv(root / SOURCE_PATHS["similar"])
    points = rebuild_points(sample)
    reconcile_points(points, frozen)
    print("SECTION5 all frozen point estimates reconciled; bootstrap authorized",
          flush=True)
    capacity_text = capacity_projection(root / SOURCE_PATHS["capacity"])
    draws = bootstrap_calipers(sample, workers)
    summary = attach_intervals(
        points, draws, frozen, read_csv(root / SOURCE_PATHS["primary_bootstrap"])
    )
    audit = build_audit(summary, root)
    check_unchanged(before, root)
    head_end = git("rev-parse", "HEAD", root=root)
    require(head_start == head_end, "HEAD_CHANGED_DURING_RUN")
    texts = {
        OUTPUT_NAMES[0]: summary.to_csv(index=False, lineterminator="\n"),
        OUTPUT_NAMES[1]: capacity_text,
        OUTPUT_NAMES[2]: json_text(audit),
        OUTPUT_NAMES[5]: draws.to_csv(index=False, lineterminator="\n"),
    }
    manifest = {
        "schema_version": "SECTION5_SECONDARY_ROBUSTNESS_MANIFEST_V1",
        "status": "SECONDARY_REPORTING_COMPLETE_HUMAN_REVIEW_REQUIRED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority_head": AUTHORITY, "HEAD_START": head_start, "HEAD_END": head_end,
        "source_artifact_hashes": {
            path.as_posix(): before[path.as_posix()] for path in SOURCE_PATHS.values()
        },
        "implementation_hashes": {
            name: digest(root / name) for name in (
                "validation/materialize_section5_secondary_robustness.py",
                "tests/validation/test_section5_secondary_robustness.py",
            )
        },
        "protected_file_hashes": before,
        "protected_file_count": len(before),
        "protected_files_unchanged": True,
        "frozen_constants": frozen_constants(),
        "bootstrap_seed": protocol.BOOTSTRAP_SEED,
        "bootstrap_replicates": protocol.BOOTSTRAP_REPLICATES,
        "bootstrap_replicates_completed_per_caliper": {
            str(caliper): int(len(draws.loc[draws.caliper_minutes.eq(caliper)]))
            for caliper in CALIPERS
        },
        "bootstrap_cluster": "original_episode_id",
        "bootstrap_ci": "percentile_95",
        "bootstrap_backend": "exp.exp2.bootstrap.run_bootstrap(reference=False)",
        "bootstrap_reconstruction": "Frozen invariant node membership; rebuild "
            "ranked sample, cross-original-episode occurrence pairs, within-pair "
            "rank-gap medians and pair-balanced summaries on every replicate.",
        "bootstrap_draw_plan_sha256": "sha256:" + hashlib.sha256(
            json_text(bootstrap_plan(
                episode_ids(sample), protocol.BOOTSTRAP_REPLICATES,
                protocol.BOOTSTRAP_SEED,
            ).tolist()).encode("utf-8")
        ).hexdigest(),
        "workers": workers,
        "caliper_grid": CALIPERS, "screening_q_grid": CAPACITIES,
        "point_estimates_reconciled": True,
        "reconciliation_atol": 1e-12, "reconciliation_rtol": 0,
        "primary_bootstrap_rows_and_ci_reconciled": True,
        "exp4_projection": "verbatim CSV fields; no numeric recomputation",
        "exp4_source_columns": CAPACITY_COLUMNS,
        "final_test_access_count_before": 1, "final_test_access_count_after": 1,
        "remaining_blocked_items": [],
        "preserved_source_abstention_count": len(audit["preserved_source_abstentions"]),
        "output_artifact_hashes": {
            name: "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
            for name, text in texts.items()
        },
        **GUARDS,
    }
    capacity = pd.read_csv(io.StringIO(capacity_text), float_precision="round_trip")
    report = report_text(summary, capacity, audit, manifest)
    texts[OUTPUT_NAMES[4]] = report
    manifest["output_artifact_hashes"][OUTPUT_NAMES[4]] = (
        "sha256:" + hashlib.sha256(report.encode("utf-8")).hexdigest()
    )
    texts[OUTPUT_NAMES[3]] = json_text(manifest)
    check_unchanged(before, root)
    require(git("rev-parse", "HEAD", root=root) == head_start, "HEAD_CHANGED_AT_WRITE")
    output.mkdir(parents=True, exist_ok=False)
    for name, text in texts.items():
        with (output / name).open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)
    check_unchanged(before, root)
    for name in OUTPUT_NAMES:
        print(f"{(output / name).as_posix()} {digest(output / name)}", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    materialize(workers=args.workers)


if __name__ == "__main__":
    main()
