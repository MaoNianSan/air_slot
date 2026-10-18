"""Build the paper_formal-compatible data backfill tree and its provenance manifest.

Every file is prefixed CLOUD20261013_ so that copying the tree into
data2/reports/paper_formal/{year}/ cannot overwrite the frozen M5-b baseline
files (EVAL_SUMMARY.json, EVAL_METRICS_*.json, PAPER_FORMAL_*).
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path("D:/Local_Projects/airslot/backfill_20261014")
EXT = ROOT / "extracted"
OUT = ROOT / "data_backfill"
SNAP = Path(
    "D:/research/air_slot/airslot_full_execution_snapshot_20261014/artifacts/experiment/jatm_s34/full_20261013"
)
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
STAGES = ("PRE", "TURN")
VIEWS = ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM", "CONSEQUENCE")
CONTRASTS = (
    ("ROLLING_HISTORY", "CJ-HJ"),
    ("DISTRIBUTIONAL_INFORMATION", "HP-HJ"),
    ("CROSS_STATE_DEPENDENCE", "HM-HJ"),
    ("MARGINAL_UNCERTAINTY", "HP-MINUS-HM"),
)
SOURCE_TEMPLATE = {
    "E1_SUMMARY.json": "e1/{year}/E1_SUMMARY.json",
    "E2_E3_SUMMARY.json": "e2e3/{year}/E2_E3_SUMMARY.json",
    "E3_OBJECTIVE_ROWS.json": "e2e3/{year}/E3_OBJECTIVE_ROWS.json",
    "E3_MECHANISM_DIAGNOSTICS.json": "e2e3/{year}/E3_MECHANISM_DIAGNOSTICS.json",
    "EXACT_MARGINAL_AUDIT.json": "e2e3/{year}/EXACT_MARGINAL_AUDIT.json",
    "E4_EVAL_SUMMARY.json": "e4/{year}/EVAL_SUMMARY.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv(path: Path, header, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def main() -> int:
    e1 = json.loads((EXT / "e1_six_year.json").read_text(encoding="utf-8"))
    e2 = json.loads((EXT / "e2_six_year.json").read_text(encoding="utf-8"))
    e3 = json.loads((EXT / "e3_six_year.json").read_text(encoding="utf-8"))
    derived = json.loads((EXT / "derived_and_checks.json").read_text(encoding="utf-8"))
    sources = {}
    for year in YEARS:
        target = OUT / f"year_{year}"
        target.mkdir(parents=True, exist_ok=True)
        sources[year] = {}
        for name, template in SOURCE_TEMPLATE.items():
            source = SNAP / template.format(year=year)
            sources[year][name] = {"path": str(source), "sha256": sha256(source), "bytes": source.stat().st_size}

        # E1: nominal budget + full q grid
        rows = []
        for stage in STAGES:
            for view in VIEWS:
                cell = e1[str(year)]["nominal_q010"][stage][view]
                rows.append([
                    year, stage, view, cell["n"], cell["k"], cell["overlap"], cell["replacement"],
                    cell["retained_consequence"], cell["absolute_consequence_gap"], cell["attention_loss"],
                    (cell["attention_loss_ci"] or {}).get("low"), (cell["attention_loss_ci"] or {}).get("high"),
                    (cell["replacement_ci"] or {}).get("low"), (cell["replacement_ci"] or {}).get("high"),
                ])
        write_csv(target / "CLOUD20261013_E1_SCREENING_Q010.csv",
                  ["year", "stage", "priority", "N", "K", "overlap", "replaced", "retained_consequence",
                   "absolute_consequence_gap_CU", "L_att", "L_att_ci_low", "L_att_ci_high",
                   "replaced_ci_low", "replaced_ci_high"], rows)

        grid = [[row["year"] if "year" in row else year, row["stage"], row["q"], row["view"], row["n"], row["k"],
                 row["overlap"], row["replacement"], row["retained_consequence"], row["attention_loss"],
                 row["ci_low"], row["ci_high"]]
                for row in e1[str(year)]["q_grid"]]
        write_csv(target / "CLOUD20261013_E1_Q_SENSITIVITY.csv",
                  ["year", "stage", "q", "priority", "N", "K", "overlap", "replaced", "retained_consequence",
                   "L_att", "L_att_ci_low", "L_att_ci_high"], grid)

        # E2: paired contrast value table + activation events
        info = e2[str(year)]["e2"]["information_value"]
        rows = []
        for component, label in CONTRASTS:
            row = info[component]
            rows.append([year, label, component, row["comparator"], e2[str(year)]["e2"]["reference_cohort_size"],
                         row["stage1_reassigned_share"], row["L_att"], row["L_att_ci_low"], row["L_att_ci_high"],
                         row["A0"], row["A5"], row["L_rec"], row["L_rec_ci_low"], row["L_rec_ci_high"],
                         row["delta_J"], row["reference_V"], row["missed_activation"], row["false_activation"],
                         row["under_recovery"], row["over_recovery"]])
        write_csv(target / "CLOUD20261013_E2_INFORMATION_VALUE.csv",
                  ["year", "contrast", "component", "comparator", "paired_cohort",
                   "stage1_displaced_share", "L_att", "L_att_ci_low", "L_att_ci_high",
                   "A0_exact_agreement", "A5_within5_agreement", "L_rec", "L_rec_ci_low", "L_rec_ci_high",
                   "delta_J_CU", "reference_V_CU", "missed_activation", "false_activation",
                   "under_recovery", "over_recovery"], rows)

        # E2: per-stage reference detail (delay-vs-consequence comparator pair stored in stage1_rows)
        rows = [[year, row["stage"], row["N"], row["K"], row["overlap"], row["displaced"], row["L_att"]]
                for row in e2[str(year)]["e2"]["stage1_rows_HM_vs_HJ"]]
        write_csv(target / "CLOUD20261013_E2_STAGE1_ROWS_AS_STORED.csv",
                  ["year", "stage", "N", "K", "overlap", "displaced", "L_att"], rows)

        # E3: objective summary
        rows = []
        for profile, summary in e3[str(year)]["profile_summary"].items():
            rows.append([year, profile, summary["aggregation_view"], summary["N"],
                         summary["exact_target_agreement_share"], summary["dependence_sensitive_share"],
                         summary["mean_abs_target_change_min"], summary["median_abs_target_change_min"],
                         summary["max_abs_target_change_min"], summary["activation_share_joint"],
                         summary["zero_recoverable_value_share_joint"], summary["median_V_joint"],
                         summary["mean_V_joint"], summary["p90_V_joint"], summary["median_decision_margin_joint"]])
        write_csv(target / "CLOUD20261013_E3_OBJECTIVE_SUMMARY.csv",
                  ["year", "objective", "aggregation_view", "cohort", "exact_target_agreement",
                   "dependence_sensitive_share", "mean_abs_target_change_min", "median_abs_target_change_min",
                   "max_abs_target_change_min", "activation_share_joint", "zero_value_share_joint",
                   "median_V_joint_CU", "mean_V_joint_CU", "p90_V_joint_CU", "median_decision_margin_CU"], rows)

        # E3 per-stage (Balanced)
        rows = []
        for stage, summary in e3[str(year)]["profile_summary"]["BALANCED"]["per_stage"].items():
            rows.append([year, "BALANCED", stage, summary["N"], summary["activation_share_joint"],
                         summary["zero_recoverable_value_share_joint"], summary["median_V_joint"],
                         summary["agreement_joint_vs_marginal"]])
        write_csv(target / "CLOUD20261013_E3_BALANCED_BY_STAGE.csv",
                  ["year", "objective", "stage", "cohort", "activation_share_joint", "zero_value_share_joint",
                   "median_V_joint_CU", "HM_HJ_agreement"], rows)

        # E4 ladder record
        ladder = derived["e4_ladder"][str(year)]
        with (target / "CLOUD20261013_E4_LADDER_RECORD.json").open("w", encoding="utf-8") as handle:
            json.dump(ladder, handle, indent=2, sort_keys=True)

        # per-year combined extraction record
        payload = {
            "year": year,
            "derived_populations": derived["derived_populations"][str(year)],
            "headroom": derived["headroom"][str(year)]["turnaround_lower_bound_q"],
            "u_max": derived["headroom"][str(year)]["u_max"],
            "crosschecks": derived["crosschecks"][str(year)],
            "e1": e1[str(year)],
            "e2": e2[str(year)],
            "e3": e3[str(year)],
            "sources": sources[year],
        }
        with (target / "CLOUD20261013_EXTRACT.json").open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)

    # cross-year support matrix
    rows = []
    for year in YEARS:
        pre = e1[str(year)]["nominal_q010"]["PRE"]["DELAY"]
        turn = e1[str(year)]["nominal_q010"]["TURN"]["DELAY"]
        rows.append([year, pre["n"], turn["n"], pre["k"], turn["k"],
                     derived["derived_populations"][str(year)]["derived_full_stage2_eligible_total"],
                     e2[str(year)]["e2"]["reference_cohort_size"], e3[str(year)]["joint_marginal_pair_count"],
                     derived["headroom"][str(year)]["turnaround_lower_bound_q"],
                     derived["headroom"][str(year)]["u_max"]])
    write_csv(OUT / "SUPPORT_MATRIX_2017_2022.csv",
              ["year", "PRE_N", "TURN_N", "PRE_K", "TURN_K", "full_stage2_eligible", "annual_HJ_supported",
               "e3_paired_rows", "turnaround_lb_min", "u_max_min"], rows)

    manifest = {
        "schema": "CLOUD_BACKFILL_MANIFEST_V1",
        "created": "2026-10-14",
        "source_root": str(SNAP),
        "source_lineage": {
            "server": "ubuntu@134.175.205.112",
            "worktree": "snapshot 583f2c12 + patch chain d1c72a7 + ffa7487",
            "full_chain": {
                "finished_utc": "2026-10-14T09:31:02Z",
                "tasks_pass": "18/18",
                "validation": "FULL_EXECUTION_VALIDATION_REPORT.json all_pass=true",
            },
            "local_snapshot": "D:/research/air_slot/airslot_full_execution_snapshot_20261014 (12245/12245 verified)",
        },
        "conventions": [
            "All files are prefixed CLOUD20261013_ so that copying year_{year}/ into "
            "data2/reports/paper_formal/{year}/ cannot overwrite frozen baseline files.",
            "q0 = 0.10 nominal review share; K = ceil(q0*N) per stage and year.",
            "L_att = 1 - (retained reference consequence)/(reference shortlist consequence).",
            "L_rec = (sum of comparator reference-objective increments)/(sum of reference recoverable values).",
            "Intervals are episode-cluster percentile bootstrap intervals, B=2000.",
        ],
        "known_artifact_issues": {
            "E2_E3_SUMMARY.e2.stage1_rows": (
                "The stored rows are labelled comparator=HISTORY_MARGINAL_EXACT but are computed by the legacy "
                "delay-vs-consequence selector: exp.jatm_section5.attention_value.candidate() defaults to "
                "HISTORY_JOINT and select_and_evaluate() hardwires comparator=delay, reference=consequence. "
                "Their comparator_shortlist reproduces the E1 DELAY shortlist exactly in 12/12 year-stages. "
                "Do not report these rows as HM-HJ; the valid HM-HJ Stage-I numbers are in "
                "E2_E3_SUMMARY.e2.information_value.CROSS_STATE_DEPENDENCE."
            ),
            "E3_MECHANISM_DIAGNOSTICS": (
                "Degenerate on the audited cohort: threshold_ablation_status = UNCHANGED for 100% of cases and the "
                "headroom fields record only the annual global parameters, because the reference cohort is "
                "restricted to fully supported cases. The file is not usable as the threshold x headroom ablation."
            ),
        },
        "years": sources,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "CLOUD_BACKFILL_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("backfill tree written to", OUT)
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            print("  ", path.relative_to(OUT), f"{path.stat().st_size/1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
