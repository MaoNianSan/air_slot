"""Figure 5 (Exp1) Development figures from the frozen Exp1 closure records.

Reads only the frozen Exp1 closure summary
(``artifacts/experiment/exp1_full_development/exp1_closure_20260825/``) and
never reruns Exp1.  Claim scopes: Exp1A
``DEVELOPMENT_CONDITIONAL_DIAGNOSTIC``; Exp1B ``DEVELOPMENT_COMPARATOR_ONLY``.
Bootstrap follows the frozen spec: episode-cluster, 2000 replicates, seed
20260825, percentile 95.  Caption wording follows the Section 4<->5
correction agreement: HISTORY and CURRENT-only use the same architecture,
training budget, and calibration path with *separate checkpoints*; the phrase
"same checkpoint" is never used.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from exp.common.official_execution import file_sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
EXP1_CLOSURE_ROOT = Path(
    "artifacts/experiment/exp1_full_development/exp1_closure_20260825"
)
EXP1_SUMMARY = EXP1_CLOSURE_ROOT / "EXP1_DEVELOPMENT_CLOSURE_SUMMARY_DEVELOPMENT_ONLY.json"
DEFAULT_OUTPUT_ROOT = Path("outputs/manuscript_values/section5_secondary_analysis")
FIGURE_BASENAME = "figure_5_exp1_direct_information"
CAPTION = (
    "Figure 5. (A) Exp1A sorting diagnostic: state-driven quantity versus "
    "context-conditioned consequence across the frozen shared-supported "
    "decision nodes (Spearman rho, top-10%/20% rank overlap, and "
    "decile-divergence rate for the main, sensitivity, and p90-D_TO "
    "specifications). (B) Operational-stage strata of the same diagnostic "
    "(PRE_IB, POST_IB_PRE_OB, POST_OB_PRE_TO). (C) Exp1B paired comparison of "
    "the history-conditioned and current-only estimators: delta MAE and delta "
    "CRPS by target, and delta MAE by lead-time bin where supported. HISTORY "
    "and CURRENT-only share the same architecture, training budget, and "
    "calibration path, with separate checkpoints; all statistics are computed "
    "on common supported observations; error bars are 95% episode-cluster "
    "bootstrap confidence intervals (2,000 replicates, seed 20260825). "
    "DEVELOPMENT_ONLY: Exp1A is a conditional diagnostic, Exp1B is a "
    "development comparator; neither is an authoritative ranking or a "
    "causal/empirical effect."
)

PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "neutral": "#CFCECE",
}
STAGE_ORDER = ("PRE_IB", "POST_IB_PRE_OB", "POST_OB_PRE_TO")
TARGET_LABELS = {
    "T_IB_A00": "Predecessor\navailability",
    "D_OB": "Successor\noff-block delay",
    "D_TX": "Excess\ntaxi delay",
}


def _apply_publication_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 13,
            "axes.linewidth": 1.6,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "legend.frameon": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def _save_figure(figure: plt.Figure, output_base: Path) -> None:
    output_base.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "svg", "png"):
        figure.savefig(
            output_base.with_suffix(f".{extension}"), dpi=600, bbox_inches="tight",
            pad_inches=0.04,
        )
    plt.close(figure)


def _ci(value: dict | None) -> tuple[float, float] | None:
    if not value or value.get("ci_95") is None:
        return None
    lower, upper = value["ci_95"]
    if lower is None or upper is None:
        return None
    return float(lower), float(upper)


def load_summary(root: Path = ROOT) -> dict:
    summary = json.loads((root / EXP1_SUMMARY).read_text(encoding="utf-8"))
    return summary


def sorting_summary_frame(summary: dict) -> pd.DataFrame:
    diag = summary["exp1a"]["sorting_diagnostic"]
    rows = []
    for key, label in (
        ("main", "Main (support>=0.90)"),
        ("sensitivity", "Sensitivity (support>=0.50)"),
    ):
        block = diag[key]
        rows.append({
            "specification": label,
            "n_nodes": block["n_nodes"],
            "spearman_rho": block["spearman_rho"],
            "spearman_ci_lower": _ci(block.get("spearman_rho_bootstrap"))[0]
            if _ci(block.get("spearman_rho_bootstrap")) else None,
            "spearman_ci_upper": _ci(block.get("spearman_rho_bootstrap"))[1]
            if _ci(block.get("spearman_rho_bootstrap")) else None,
            "kendall_tau": block["kendall_tau"],
            "top10_overlap_rate": block["top10_overlap_rate"],
            "top20_overlap_rate": block["top20_overlap_rate"],
            "decile_divergence_rate": block["decile_divergence_rate"],
            "decile_divergence_ci_lower": _ci(block.get("decile_divergence_bootstrap"))[0]
            if _ci(block.get("decile_divergence_bootstrap")) else None,
            "decile_divergence_ci_upper": _ci(block.get("decile_divergence_bootstrap"))[1]
            if _ci(block.get("decile_divergence_bootstrap")) else None,
        })
    p90 = diag["secondary"]["p90_d_to_sensitivity"]
    rows.append({
        "specification": "p90 D_TO sensitivity",
        "n_nodes": p90["n_nodes"],
        "spearman_rho": p90["spearman_rho"],
        "spearman_ci_lower": None,
        "spearman_ci_upper": None,
        "kendall_tau": p90["kendall_tau"],
        "top10_overlap_rate": p90["top10_overlap_rate"],
        "top20_overlap_rate": p90["top20_overlap_rate"],
        "decile_divergence_rate": p90["decile_divergence_rate"],
        "decile_divergence_ci_lower": None,
        "decile_divergence_ci_upper": None,
    })
    return pd.DataFrame(rows)


def stage_strata_frame(summary: dict) -> pd.DataFrame:
    strata = summary["exp1a"]["sorting_diagnostic"]["secondary"]["operational_stage_strata"]
    rows = []
    for stage in STAGE_ORDER:
        block = strata[stage]
        rows.append({
            "operational_stage": stage,
            "n_nodes": block["n_nodes"],
            "spearman_rho": block["spearman_rho"],
            "kendall_tau": block["kendall_tau"],
            "top10_overlap_rate": block["top10_overlap_rate"],
            "top20_overlap_rate": block["top20_overlap_rate"],
            "decile_divergence_rate": block["decile_divergence_rate"],
        })
    return pd.DataFrame(rows)


def history_current_deltas_frame(summary: dict) -> pd.DataFrame:
    targets = summary["exp1b"]["paired"]["targets"]
    rows = []
    for target in ("T_IB_A00", "D_OB", "D_TX"):
        block = targets[target]
        dmae = block["delta_mae_minutes"]
        dcrps = block["delta_crps_minutes"]
        rows.append({
            "target": target,
            "delta_mae_minutes": dmae["estimate"],
            "delta_mae_ci_lower": dmae["ci_95"][0],
            "delta_mae_ci_upper": dmae["ci_95"][1],
            "delta_mae_n_episodes": dmae["n_episodes"],
            "delta_crps_minutes": dcrps["estimate"],
            "delta_crps_ci_lower": dcrps["ci_95"][0],
            "delta_crps_ci_upper": dcrps["ci_95"][1],
            "delta_crps_n_episodes": dcrps["n_episodes"],
            "common_nodes_with_absolute_error": block["common_nodes_with_absolute_error"],
            "common_nodes_with_crps": block["common_nodes_with_crps"],
        })
    return pd.DataFrame(rows)


def lead_time_delta_frame(summary: dict) -> pd.DataFrame:
    targets = summary["exp1b"]["paired"]["targets"]
    rows = []
    for target in ("T_IB_A00", "D_OB"):
        bins = targets[target].get("delta_mae_by_bin_minutes") or {}
        for bin_key, value in bins.items():
            if not value:
                continue
            rows.append({
                "target": target,
                "lead_time_bin_minutes": int(bin_key),
                "delta_mae_minutes": value["estimate"],
                "ci_lower": value["ci_95"][0],
                "ci_upper": value["ci_95"][1],
                "n_episodes": value["n_episodes"],
            })
    return pd.DataFrame(rows)


def figure_5_exp1(summary: dict, output_base: Path) -> None:
    _apply_publication_style()
    sorting = sorting_summary_frame(summary)
    strata = stage_strata_frame(summary)
    deltas = history_current_deltas_frame(summary)
    lead = lead_time_delta_frame(summary)

    figure, axes = plt.subplots(3, 3, figsize=(15.5, 13.5))
    letters = iter("ABCDEFGHI")
    specs = list(sorting["specification"])

    # Row A: Exp1A sorting diagnostic
    axis = axes[0][0]
    values = sorting["spearman_rho"].to_numpy(dtype=float)
    axis.bar(specs, values, color=PALETTE["blue_main"], edgecolor="black", linewidth=1.2)
    for index, (lower, upper) in enumerate(
        zip(sorting["spearman_ci_lower"], sorting["spearman_ci_upper"], strict=True)
    ):
        if lower is None or upper is None:
            continue
        axis.errorbar(
            index, values[index],
            yerr=[[values[index] - lower], [upper - values[index]]],
            fmt="none", color="black", capsize=4, linewidth=1.3,
        )
    axis.set_ylabel("Spearman rho")
    axis.tick_params(axis="x", labelrotation=15)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[0][1]
    width = 0.38
    positions = np.arange(len(specs))
    axis.bar(positions - width / 2, sorting["top10_overlap_rate"], width,
             label="Top-10% overlap", color=PALETTE["blue_secondary"], edgecolor="black", linewidth=1.0)
    axis.bar(positions + width / 2, sorting["top20_overlap_rate"], width,
             label="Top-20% overlap", color=PALETTE["neutral"], edgecolor="black", linewidth=1.0)
    axis.set_xticks(positions, specs, rotation=15)
    axis.set_ylabel("Rank overlap rate")
    axis.legend(fontsize=10)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[0][2]
    values = sorting["decile_divergence_rate"].to_numpy(dtype=float)
    axis.bar(specs, values, color=PALETTE["blue_main"], edgecolor="black", linewidth=1.2)
    for index, (lower, upper) in enumerate(
        zip(sorting["decile_divergence_ci_lower"], sorting["decile_divergence_ci_upper"], strict=True)
    ):
        if lower is None or upper is None:
            continue
        axis.errorbar(
            index, values[index],
            yerr=[[values[index] - lower], [upper - values[index]]],
            fmt="none", color="black", capsize=4, linewidth=1.3,
        )
    axis.set_ylabel("Decile-divergence rate")
    axis.tick_params(axis="x", labelrotation=15)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    # Row B: operational-stage strata
    stages = list(strata["operational_stage"])
    axis = axes[1][0]
    positions = np.arange(len(stages))
    axis.bar(positions - width / 2, strata["spearman_rho"], width,
             label="Spearman rho", color=PALETTE["blue_main"], edgecolor="black", linewidth=1.0)
    axis.bar(positions + width / 2, strata["kendall_tau"], width,
             label="Kendall tau", color=PALETTE["blue_secondary"], edgecolor="black", linewidth=1.0)
    axis.set_xticks(positions, stages, rotation=15)
    axis.set_ylabel("Rank correlation")
    axis.legend(fontsize=10)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[1][1]
    axis.bar(positions - width, strata["top10_overlap_rate"], width,
             label="Top-10% overlap", color=PALETTE["blue_secondary"], edgecolor="black", linewidth=1.0)
    axis.bar(positions, strata["top20_overlap_rate"], width,
             label="Top-20% overlap", color=PALETTE["neutral"], edgecolor="black", linewidth=1.0)
    axis.bar(positions + width, strata["decile_divergence_rate"], width,
             label="Decile divergence", color=PALETTE["blue_main"], edgecolor="black", linewidth=1.0)
    axis.set_xticks(positions, stages, rotation=15)
    axis.set_ylabel("Rate")
    axis.legend(fontsize=9)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[1][2]
    axis.axis("off")
    note = (
        "Exp1A: 1,769 nodes; main 1,420 (support>=0.90), "
        "sensitivity 1,765 (support>=0.50); exclusions: "
        "EXCLUDED_M2_NOT_AVAILABLE 4, EXCLUDED_SUPPORT_BELOW_THRESHOLD 345.\n"
        "Claim scope: DEVELOPMENT_CONDITIONAL_DIAGNOSTIC (non-causal, "
        "non-optimal, non-authoritative).\n"
        "Top-1 / ex-post endpoints NOT_RUN "
        "(NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE)."
    )
    axis.text(0.02, 0.98, note, transform=axis.transAxes, va="top", fontsize=10,
              family="monospace")
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    # Row C: Exp1B HISTORY vs CURRENT-only paired deltas
    targets = list(deltas["target"])
    axis = axes[2][0]
    values = deltas["delta_mae_minutes"].to_numpy(dtype=float)
    axis.bar(targets, values, color=PALETTE["blue_secondary"], edgecolor="black", linewidth=1.2)
    for index, row in deltas.iterrows():
        axis.errorbar(
            index, values[index],
            yerr=[[values[index] - row["delta_mae_ci_lower"]],
                  [row["delta_mae_ci_upper"] - values[index]]],
            fmt="none", color="black", capsize=4, linewidth=1.3,
        )
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.set_xticks(range(len(targets)), [TARGET_LABELS[t] for t in targets])
    axis.set_ylabel("Delta MAE (min)\nHISTORY - CURRENT-only")
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[2][1]
    values = deltas["delta_crps_minutes"].to_numpy(dtype=float)
    axis.bar(targets, values, color=PALETTE["blue_main"], edgecolor="black", linewidth=1.2)
    for index, row in deltas.iterrows():
        axis.errorbar(
            index, values[index],
            yerr=[[values[index] - row["delta_crps_ci_lower"]],
                  [row["delta_crps_ci_upper"] - values[index]]],
            fmt="none", color="black", capsize=4, linewidth=1.3,
        )
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.set_xticks(range(len(targets)), [TARGET_LABELS[t] for t in targets])
    axis.set_ylabel("Delta CRPS (min)\nHISTORY - CURRENT-only")
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    axis = axes[2][2]
    for target, color in (("T_IB_A00", PALETTE["blue_main"]), ("D_OB", PALETTE["blue_secondary"])):
        cell = lead.loc[lead["target"] == target].sort_values("lead_time_bin_minutes")
        if cell.empty:
            continue
        x = cell["lead_time_bin_minutes"].to_numpy(dtype=int)
        y = cell["delta_mae_minutes"].to_numpy(dtype=float)
        axis.plot(x, y, marker="o", markersize=4, linewidth=1.6, color=color, label=target)
        axis.fill_between(
            x, cell["ci_lower"], cell["ci_upper"], color=color, alpha=0.14,
        )
    axis.axhline(0.0, color="black", linewidth=1.0)
    axis.set_xlabel("Lead time (min)")
    axis.set_ylabel("Delta MAE (min)\nHISTORY - CURRENT-only")
    axis.legend(fontsize=10)
    axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=15)

    figure.tight_layout(pad=1.2)
    _save_figure(figure, output_base)


def run(*, root: Path = ROOT, output_root: Path | None = None) -> dict[str, Path]:
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT_ROOT).resolve()
    summary = load_summary(root)

    data_root = output_root / "data"
    figures_root = output_root / "figures"
    data_root.mkdir(parents=True, exist_ok=True)
    figures_root.mkdir(parents=True, exist_ok=True)

    sorting = sorting_summary_frame(summary)
    strata = stage_strata_frame(summary)
    deltas = history_current_deltas_frame(summary)
    lead = lead_time_delta_frame(summary)

    sorting_path = data_root / "figure_5a_sorting_summary.csv"
    strata_path = data_root / "figure_5b_stage_strata.csv"
    deltas_path = data_root / "figure_5c_history_current_deltas.csv"
    lead_path = data_root / "figure_5c_lead_time_delta_mae.csv"
    sorting.to_csv(sorting_path, index=False)
    strata.to_csv(strata_path, index=False)
    deltas.to_csv(deltas_path, index=False)
    lead.to_csv(lead_path, index=False)

    figure_base = figures_root / FIGURE_BASENAME
    figure_5_exp1(summary, figure_base)

    caption_path = output_root / "figure_5_caption.txt"
    caption_path.write_text(CAPTION + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "AIR_SLOT_EXP1_FIGURES_MANIFEST_V1",
        "scope": "DEVELOPMENT_ONLY",
        "paper_result": False,
        "final_test_access_count": 0,
        "git": "NO_COMMIT",
        "claim_scopes": {
            "exp1a": "DEVELOPMENT_CONDITIONAL_DIAGNOSTIC",
            "exp1b": "DEVELOPMENT_COMPARATOR_ONLY",
        },
        "bootstrap": {
            "resampling_unit": "EPISODE",
            "replicates": 2000,
            "seed": 20260825,
            "ci_method": "PERCENTILE_95",
        },
        "caption_wording": (
            "same architecture, training budget, and calibration path; "
            "separate checkpoints (never 'same checkpoint')"
        ),
        "input_summary_hash": file_sha256(root / EXP1_SUMMARY),
        "closure_artifact_hash": summary.get("artifact_hash"),
        "inputs": {
            "exp1a_paper_facing_records": "EXP1A_PAPER_FACING_RECORDS_DEVELOPMENT_ONLY.csv (3538 rows)",
            "exp1a_sorting_diagnostic": "EXP1A_FROZEN_SORTING_DIAGNOSTIC_DEVELOPMENT_ONLY.csv (1769 rows)",
            "exp1b_prediction_records": "EXP1B_PREDICTION_RECORDS_DEVELOPMENT_ONLY.csv (10614 rows)",
        },
        "outputs": [
            str(figure_base.with_suffix(ext).relative_to(output_root)) for ext in (".pdf", ".svg", ".png")
        ]
        + [
            str(path.relative_to(output_root)) for path in (
                sorting_path, strata_path, deltas_path, lead_path, caption_path,
            )
        ],
        "safety": {
            "EXP1_RERUNS": 0,
            "FINAL_TEST_ACCESS_COUNT": 0,
            "PAPER_FULL_RUN": False,
        },
    }
    manifest_path = output_root / "EXP1_FIGURES_MANIFEST_DEVELOPMENT_ONLY.json"
    write_json(manifest_path, manifest)
    return {
        "manifest": manifest_path, "figure": figure_base,
        "sorting": sorting_path, "strata": strata_path, "deltas": deltas_path,
        "caption": caption_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args(argv)
    run(root=ROOT, output_root=args.output_root)
    print("EXP1_FIGURES_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
