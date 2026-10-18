"""Build paper-facing backfill tables, figures and a numbers digest.

Inputs: extracted/{e1,e2,e3,e4}_six_year.json + derived_and_checks.json
Outputs: tables/*.tex, figures/*.pdf|png, numbers.md
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path("D:/Local_Projects/airslot/backfill_20261014")
EXT = ROOT / "extracted"
TAB = ROOT / "tables"
FIG = ROOT / "figures"
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
STAGES = ("PRE", "TURN")
VIEW_LABEL = {
    "DELAY": "Delay",
    "DELAY_PASSENGER": "Delay+Passenger",
    "DELAY_DOWNSTREAM": "Delay+Downstream",
    "CONSEQUENCE": "Consequence",
}
PROFILE_LABEL = {
    "BALANCED": "Balanced",
    "FLIGHT": "Flight",
    "PASSENGER": "Passenger",
    "RESOURCE": "Resource",
}

plt.rcParams.update({
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "legend.fontsize": 8,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "figure.dpi": 300,
    "savefig.bbox": "tight",
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linewidth": 0.5,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

COLORS = {"DELAY": "#0072B2", "DELAY_PASSENGER": "#D55E00", "DELAY_DOWNSTREAM": "#666666",
          "CONSEQUENCE": "#009E73"}
CONTRAST_COLORS = {"HM--HJ": "#0072B2", "HP--HJ": "#D55E00", "HP--HM paired increment": "#009E73"}
OBJECTIVE_COLORS = {"BALANCED": "#0072B2", "FLIGHT": "#009E73",
                    "PASSENGER": "#D55E00", "RESOURCE": "#7A68A6"}
STAGE_HATCH = {"PRE": "", "TURN": "//"}
YEAR_LABELS = ("'17", "'18", "'19", "'20", "'21", "'22")


def _load(name: str):
    return json.loads((EXT / name).read_text(encoding="utf-8"))


def fmt(value, nd=4):
    if value is None:
        return "---"
    return f"{value:.{nd}f}"


def fmt_count(value):
    return "---" if value is None else f"{value:,}".replace(",", "\\,")


def ci(low, high, nd=4):
    if low is None or high is None:
        return "---"
    return f"[{low:.{nd}f}, {high:.{nd}f}]"


# ----------------------------------------------------------------------------- tables
def table_5_1(e2, e3) -> str:
    """Balanced-objective recovery profile within annual HJ reference cohorts."""
    lines = []
    for year in YEARS:
        e2_year = e2[str(year)]["e2"]
        balanced = e3[str(year)]["profile_summary"]["BALANCED"]
        reference_v = e2_year["information_value"]["CROSS_STATE_DEPENDENCE"]["reference_V"]
        lines.append(
            f"{year} & {e2_year['reference_cohort_size']} & "
            f"{fmt(balanced['activation_share_joint'], 3)} & "
            f"{fmt(balanced['median_V_joint'], 3)} & "
            f"{fmt(balanced['p90_V_joint'], 3)} & {fmt(reference_v, 1)} \\\\"
        )
    return "\n".join(lines)


def _range(values, nd=4):
    return f"{min(values):.{nd}f}--{max(values):.{nd}f}"


def table_5_2(e2) -> str:
    """Compact six-year range summary; annual rows remain in the supplement."""
    order = [
        ("CROSS_STATE_DEPENDENCE", "HM--HJ"),
        ("DISTRIBUTIONAL_INFORMATION", "HP--HJ"),
        ("MARGINAL_UNCERTAINTY", "HP--HM paired increment"),
    ]
    lines = []
    for component, label in order:
        rows = [e2[str(year)]["e2"]["information_value"][component] for year in YEARS]
        displacement = [
            row["stage1_reassigned_share"] for row in rows
            if row["stage1_reassigned_share"] is not None
        ]
        agreement = [row["A0"] for row in rows if row["A0"] is not None]
        displacement_text = (
            f"{100 * min(displacement):.1f}--{100 * max(displacement):.1f}\\%"
            if displacement else "--"
        )
        agreement_text = _range(agreement, 3) if agreement else "--"
        lines.append(
            f"{label} & {displacement_text} & "
            f"{_range([row['L_att'] for row in rows])} & "
            f"{agreement_text} & {_range([row['L_rec'] for row in rows])} \\\\"
        )
    return "\n".join(lines)


def table_sup_e2_annual(e2) -> str:
    """Full year-by-year contrasts for the supplementary material."""
    order = [("ROLLING_HISTORY", "CJ--HJ"), ("DISTRIBUTIONAL_INFORMATION", "HP--HJ"),
             ("CROSS_STATE_DEPENDENCE", "HM--HJ")]
    lines = []
    for year in YEARS:
        info = e2[str(year)]["e2"]["information_value"]
        cohort = e2[str(year)]["e2"]["reference_cohort_size"]
        for index, (component, label) in enumerate(order):
            row = info[component]
            head = f"{year}" if index == 0 else ""
            lines.append(
                f"{head} & {label} & {fmt(row['stage1_reassigned_share'], 4)} & "
                f"{fmt(row['L_att'])} {ci(row['L_att_ci_low'], row['L_att_ci_high'])} & "
                f"{fmt(row['A0'], 3)} & {fmt(row['L_rec'])} {ci(row['L_rec_ci_low'], row['L_rec_ci_high'])} \\\\"
                if index == 2 else
                f"{head} & {label} & {fmt(row['stage1_reassigned_share'], 4)} & "
                f"{fmt(row['L_att'])} {ci(row['L_att_ci_low'], row['L_att_ci_high'])} & "
                f"{fmt(row['A0'], 3)} & {fmt(row['L_rec'])} {ci(row['L_rec_ci_low'], row['L_rec_ci_high'])} \\\\"
            )
    return "\n".join(lines)


def table_5_2_support(e2) -> str:
    """Supplement: per-year paired cohort, reference V, Delta J, activation events."""
    lines = []
    for year in YEARS:
        info = e2[str(year)]["e2"]["information_value"]
        cohort = e2[str(year)]["e2"]["reference_cohort_size"]
        for component, label in (("ROLLING_HISTORY", "CJ--HJ"),
                                 ("DISTRIBUTIONAL_INFORMATION", "HP--HJ"),
                                 ("CROSS_STATE_DEPENDENCE", "HM--HJ")):
            row = info[component]
            lines.append(
                f"{year} & {label} & {cohort} & {fmt(row['reference_V'], 2)} & {fmt(row['delta_J'], 2)} & "
                f"{row['missed_activation']} & {row['false_activation']} & {row['under_recovery']} & "
                f"{row['over_recovery']} \\\\"
            )
    return "\n".join(lines)


def table_sup_support(e1, e2, derived, e3) -> str:
    lines = []
    for year in YEARS:
        pre = e1[str(year)]["nominal_q010"]["PRE"]["DELAY"]
        turn = e1[str(year)]["nominal_q010"]["TURN"]["DELAY"]
        paired = e2[str(year)]["e2"]["reference_cohort_size"]
        full = derived[str(year)]["derived_full_stage2_eligible_total"]
        pairs = e3[str(year)]["joint_marginal_pair_count"]
        lines.append(
            f"{year} & {fmt_count(pre['n'])} & {fmt_count(turn['n'])} & {pre['k']} & {turn['k']} & "
            f"{fmt_count(full)} & {paired} & {fmt_count(pairs)} \\\\"
        )
    return "\n".join(lines)


def table_sup_e1(e1) -> str:
    lines = []
    for year in YEARS:
        for stage in STAGES:
            row = e1[str(year)]["nominal_q010"][stage]
            for view in ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM"):
                cell = row[view]
                lines.append(
                    f"{year} & {stage} & {VIEW_LABEL[view]} & {fmt_count(cell['n'])} & {cell['k']} & "
                    f"{cell['overlap']} & {cell['replacement']} & {fmt(cell['retained_consequence'], 4)} & "
                    f"{fmt(cell['attention_loss'], 4)} {ci(cell['attention_loss_ci']['low'], cell['attention_loss_ci']['high'])} \\\\"
                    if cell.get("attention_loss_ci") else
                    f"{year} & {stage} & {VIEW_LABEL[view]} & {fmt_count(cell['n'])} & {cell['k']} & "
                    f"{cell['overlap']} & {cell['replacement']} & {fmt(cell['retained_consequence'], 4)} & "
                    f"{fmt(cell['attention_loss'], 4)} \\\\"
                )
    return "\n".join(lines)


def table_sup_e1_q(e1) -> str:
    lines = []
    for view in ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM"):
        for stage in STAGES:
            cells = []
            for q in (0.05, 0.10, 0.20, 0.30):
                row = next(r for r in e1["2019"]["q_grid"]
                           if r["stage"] == stage and abs(r["q"] - q) < 1e-9 and r["view"] == view)
                cells.append(f"{fmt(row['attention_loss'], 4)}")
            lines.append(f"{VIEW_LABEL[view]} & {stage} & " + " & ".join(cells) + " \\\\")
    return "\n".join(lines)


def table_sup_e3(e3) -> str:
    lines = []
    for year in YEARS:
        summary = e3[str(year)]["profile_summary"]
        for profile in ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE"):
            row = summary[profile]
            lines.append(
                f"{year} & {PROFILE_LABEL[profile]} & {fmt(row['exact_target_agreement_share'], 3)} & "
                f"{fmt(row['dependence_sensitive_share'], 3)} & {fmt(row['mean_abs_target_change_min'], 2)} & "
                f"{fmt(row['activation_share_joint'], 3)} & {fmt(row['zero_recoverable_value_share_joint'], 3)} & "
                f"{fmt(row['median_V_joint'], 4)} \\\\"
            )
    return "\n".join(lines)


def table_sup_e2_support(e2) -> str:
    return table_5_2_support(e2)


def table_sup_ladder(ladder) -> str:
    lines = []
    for year in YEARS:
        row = ladder[str(year)]
        failures = {key.split(":")[-1] for key in row["decision"]["failed_instances"]}
        eval_failures = sum(1 for key in row["decision"]["failed_instances"] if ":eval:" in key)
        fit_failures = sum(1 for key in row["decision"]["failed_instances"] if ":fit:" in key)
        status = row["decision"]["status"].replace("_", r"\_")
        lines.append(
            f"{year} & 128--2048 & {fmt_count(row['evaluation_E'])} & "
            f"{status} & {eval_failures} & {fit_failures} \\\\"
        )
    return "\n".join(lines)


# ----------------------------------------------------------------------------- figures
def figure_q_boundary(e1) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.45))
    views = ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM")
    labels = ("'17", "'18", "'19", "'20", "'21", "'22")
    x = np.arange(len(YEARS))
    width = 0.13
    offsets = {"PRE": -0.5, "TURN": 0.5}
    for stage_index, stage in enumerate(STAGES):
        pass

    def grouped(ax, metric, with_ci=False):
        for v_index, view in enumerate(views):
            for stage in STAGES:
                if metric == "replacement_share":
                    values, lows, highs = [], [], []
                    for year in YEARS:
                        cell = e1[str(year)]["nominal_q010"][stage][view]
                        values.append(cell["replacement"] / cell["k"])
                        lows.append(cell["replacement_ci"]["low"] / cell["k"])
                        highs.append(cell["replacement_ci"]["high"] / cell["k"])
                else:
                    values = [e1[str(year)]["nominal_q010"][stage][view][metric] for year in YEARS]
                    lows = [e1[str(year)]["nominal_q010"][stage][view]["attention_loss_ci"]["low"] for year in YEARS]
                    highs = [e1[str(year)]["nominal_q010"][stage][view]["attention_loss_ci"]["high"] for year in YEARS]
                offset = (v_index - 1) * (2 * width) + offsets[stage] * width
                err = None
                if with_ci:
                    err = [np.array(values) - np.array(lows), np.array(highs) - np.array(values)]
                ax.bar(x + offset, values, width, color=COLORS[view],
                       hatch=STAGE_HATCH[stage], edgecolor="white", linewidth=0.3,
                       yerr=err if (with_ci and view == "DELAY") else None, capsize=1.6,
                       error_kw={"lw": 0.7})

    ax = axes[0]
    grouped(ax, "replacement_share")
    ax.set_ylabel("Displaced share of shortlist")
    ax.set_title("(a) Displaced positions, $q_0=0.10$")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[v]) for v in views]
    handles += [plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="0.4"),
                plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="0.4", hatch="//")]
    ax.legend(handles, ["Delay", "Delay+Passenger", "Delay+Downstream", "PRE", "TURN"],
              frameon=False, fontsize=6, ncol=2, loc="upper left")

    ax = axes[1]
    grouped(ax, "attention_loss", with_ci=True)
    ax.set_ylabel("$L^{\mathrm{att}}$")
    ax.set_title("(b) Screening loss, $q_0=0.10$")
    ax.set_ylim(bottom=0)

    ax = axes[2]
    qs = (0.05, 0.10, 0.20, 0.30)
    for view, style in (("DELAY", "-"), ("DELAY_PASSENGER", "--")):
        for stage, marker in (("PRE", "o"), ("TURN", "s")):
            means, lows, highs = [], [], []
            for q in qs:
                vals = []
                for year in YEARS:
                    row = next(r for r in e1[str(year)]["q_grid"]
                               if r["stage"] == stage and abs(r["q"] - q) < 1e-9 and r["view"] == view)
                    vals.append(row["attention_loss"])
                means.append(statistics.fmean(vals)); lows.append(min(vals)); highs.append(max(vals))
            ax.plot(qs, means, style, marker=marker, color=COLORS[view],
                    markerfacecolor="white" if stage == "PRE" else COLORS[view],
                    lw=1.1, ms=3, label=f"{VIEW_LABEL[view]}, {stage}")
            ax.fill_between(qs, lows, highs, color=COLORS[view], alpha=0.10, lw=0)
    ax.set_xticks(qs)
    ax.set_xlabel("Review fraction $q$")
    ax.set_ylabel("$L^{\mathrm{att}}$ (year mean, min--max band)")
    ax.set_title("(c) Review-budget sensitivity")
    ax.legend(frameon=False, ncol=1, fontsize=6)

    for ax in (axes[0], axes[1]):
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
    axes[0].set_ylim(0, 0.70)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_1_q_boundary.{suffix}")
    plt.close(fig)


def figure_recoverability(e3) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.5))
    x = np.arange(len(YEARS))
    ax = axes[0]
    positive = [e3[str(y)]["profile_summary"]["BALANCED"]["activation_share_joint"] for y in YEARS]
    zero_v = [e3[str(y)]["profile_summary"]["BALANCED"]["zero_recoverable_value_share_joint"] for y in YEARS]
    ax.bar(x, positive, 0.6, color="#2e7d32", label="positive reference target ($u^*>0$)")
    ax.bar(x, zero_v, 0.6, bottom=positive, color="#bdbdbd", label="zero recoverable value")
    ax.set_xticks(x); ax.set_xticklabels(YEAR_LABELS); ax.set_ylim(0, 1.0)
    ax.set_ylabel("Share of reference cohort")
    ax.set_title("(a) Activation and zero-value shares")
    ax.legend(frameon=False, fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncol=2)

    ax = axes[1]
    medians, p90, means = [], [], []
    for year in YEARS:
        rows = sorted(e3[str(year)]["u_star_distribution"].items())
        medians.append(e3[str(year)]["profile_summary"]["BALANCED"]["median_V_joint"])
        means.append(e3[str(year)]["profile_summary"]["BALANCED"]["mean_V_joint"])
        p90.append(e3[str(year)]["profile_summary"]["BALANCED"]["p90_V_joint"])
    ax.plot(x, medians, "-o", ms=3, color="#1f4e79", label="median $V$")
    ax.plot(x, p90, "-s", ms=3, color="#c00000", label="P90 $V$")
    ax.plot(x, means, ":^", ms=3, color="#7f7f7f", label="mean $V$")
    ax.set_xticks(x); ax.set_xticklabels(YEAR_LABELS)
    ax.set_ylabel("Reference recoverable value (CU)")
    ax.set_title("(b) Recoverable-value distribution")
    ax.legend(frameon=False, fontsize=6)

    ax = axes[2]
    for profile, color in (("BALANCED", "#1f4e79"), ("FLIGHT", "#2e7d32"),
                           ("PASSENGER", "#c00000"), ("RESOURCE", "#7f7f7f")):
        vals = [e3[str(y)]["profile_summary"][profile]["activation_share_joint"] for y in YEARS]
        ax.plot(x, vals, "-o", ms=3, color=color, label=PROFILE_LABEL[profile])
    ax.set_xticks(x); ax.set_xticklabels(YEAR_LABELS)
    ax.set_ylabel("Activation share (HJ reference)")
    ax.set_title("(c) Activation by objective")
    ax.legend(frameon=False, fontsize=6, ncol=2)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_2_recoverability.{suffix}")
    plt.close(fig)


def figure_objectives(e3) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.5))
    x = np.arange(len(YEARS))
    width = 0.2
    profiles = ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE")
    colors = ("#1f4e79", "#2e7d32", "#c00000", "#7f7f7f")
    ax = axes[0]
    for index, (profile, color) in enumerate(zip(profiles, colors)):
        vals = [e3[str(y)]["profile_summary"][profile]["exact_target_agreement_share"] for y in YEARS]
        ax.bar(x + (index - 1.5) * width, vals, width, color=color, label=PROFILE_LABEL[profile])
    ax.set_xticks(x); ax.set_xticklabels(YEAR_LABELS); ax.set_ylim(0, 1.0)
    ax.set_ylabel("Exact target agreement")
    ax.set_title("(a) HM--HJ agreement by objective")
    ax.legend(frameon=False, fontsize=6, ncol=2)

    ax = axes[1]
    for index, (profile, color) in enumerate(zip(profiles, colors)):
        vals = [e3[str(y)]["profile_summary"][profile]["mean_abs_target_change_min"] for y in YEARS]
        ax.bar(x + (index - 1.5) * width, vals, width, color=color)
    ax.set_xticks(x); ax.set_xticklabels(YEARS)
    ax.set_ylabel("Mean $|\\Delta u^*|$ (min)")
    ax.set_title("(b) Dependence-sensitive magnitude")

    ax = axes[2]
    for index, (profile, color) in enumerate(zip(profiles, colors)):
        vals = [e3[str(y)]["profile_summary"][profile]["median_V_joint"] for y in YEARS]
        ax.bar(x + (index - 1.5) * width, vals, width, color=color)
    ax.set_xticks(x); ax.set_xticklabels(YEAR_LABELS)
    ax.set_ylabel("Median $V^{HJ}$ (CU)")
    ax.set_title("(c) Recoverable value by objective")
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_3_objectives.{suffix}")
    plt.close(fig)


def figure_q_boundary_revised(e1) -> None:
    """Less crowded annual screening estimates and review-budget sensitivity."""
    fig, axes = plt.subplots(2, 2, figsize=(7.1, 4.2))
    x = np.arange(len(YEARS))
    methods = ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM")
    labels = {
        "DELAY": "Delay",
        "DELAY_PASSENGER": "Delay + passenger exposure",
        "DELAY_DOWNSTREAM": "Delay + downstream exposure",
    }
    offsets = (-0.18, 0.0, 0.18)
    markers = ("o", "s", "^")

    # Independent annual evaluations are plotted as points, not connected trends.
    for col, stage in enumerate(STAGES):
        ax = axes[0, col]
        for offset, method, marker in zip(offsets, methods, markers):
            rows = [e1[str(year)]["nominal_q010"][stage][method] for year in YEARS]
            values = np.asarray([row["attention_loss"] for row in rows])
            lows = np.asarray([row["attention_loss_ci"]["low"] for row in rows])
            highs = np.asarray([row["attention_loss_ci"]["high"] for row in rows])
            ax.errorbar(
                x + offset, values,
                yerr=np.vstack((values - lows, highs - values)),
                fmt=marker, color=COLORS[method], ms=4, capsize=2,
                elinewidth=0.9, linestyle="none", label=labels[method],
            )
        ax.set_title(f"({'a' if col == 0 else 'b'}) {stage}, $q_0=0.10$")
        ax.set_ylabel("$L^{\\mathrm{att}}$")
        ax.set_xticks(x)
        ax.set_xticklabels(YEAR_LABELS)
        ax.set_ylim(0, 0.24)
        ax.grid(axis="x", visible=False)

    qs = (0.05, 0.10, 0.20, 0.30)
    for col, stage in enumerate(STAGES):
        ax = axes[1, col]
        for method in ("DELAY", "DELAY_PASSENGER"):
            means, lows, highs = [], [], []
            for q in qs:
                annual = [
                    next(row for row in e1[str(year)]["q_grid"]
                         if row["stage"] == stage and abs(row["q"] - q) < 1e-9
                         and row["view"] == method)["attention_loss"]
                    for year in YEARS
                ]
                means.append(statistics.fmean(annual))
                lows.append(min(annual))
                highs.append(max(annual))
            ax.plot(qs, means, marker="o", ms=4, lw=1.4,
                    color=COLORS[method], label=labels[method])
            ax.fill_between(qs, lows, highs, color=COLORS[method], alpha=0.13, lw=0)
        ax.set_title(f"({'c' if col == 0 else 'd'}) {stage}, review-budget sensitivity")
        ax.set_xlabel("Review fraction $q$")
        ax.set_ylabel("Mean $L^{\\mathrm{att}}$")
        ax.set_xticks(qs)
        ax.set_ylim(0, 0.24)
        ax.grid(axis="x", visible=False)

    handles, legend_labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=3,
               frameon=False, bbox_to_anchor=(0.5, 1.02))
    fig.tight_layout()
    fig.subplots_adjust(top=0.88, hspace=0.50, wspace=0.28)
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_1_q_boundary.{suffix}")
    plt.close(fig)


def figure_information_layers(e2) -> None:
    """Compare shortlist replacement with Stage-II loss across the six years."""
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.75))
    x = np.arange(len(YEARS))
    labels = YEAR_LABELS
    keys = {
        "HM--HJ": "CROSS_STATE_DEPENDENCE",
        "HP--HJ": "DISTRIBUTIONAL_INFORMATION",
        "HP--HM paired increment": "MARGINAL_UNCERTAINTY",
    }
    offsets = {"HM--HJ": -0.12, "HP--HJ": 0.0, "HP--HM paired increment": 0.12}
    markers = {"HM--HJ": "o", "HP--HJ": "s", "HP--HM paired increment": "^"}

    ax = axes[0]
    for contrast in ("HM--HJ", "HP--HJ"):
        vals = [
            e2[str(year)]["e2"]["information_value"][keys[contrast]]["stage1_reassigned_share"]
            for year in YEARS
        ]
        ax.plot(x + offsets[contrast], vals, linestyle="none", marker=markers[contrast],
                ms=4.5, color=CONTRAST_COLORS[contrast], label=contrast)
    ax.set_title("(a) Stage-I shortlist positions reassigned")
    ax.set_ylabel("Share of reference shortlist")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.0)
    ax.grid(axis="x", visible=False)

    ax = axes[1]
    for contrast, key in keys.items():
        rows = [e2[str(year)]["e2"]["information_value"][key] for year in YEARS]
        vals = np.asarray([row["L_rec"] for row in rows])
        lows = np.asarray([row["L_rec_ci_low"] for row in rows])
        highs = np.asarray([row["L_rec_ci_high"] for row in rows])
        ax.errorbar(
            x + offsets[contrast], vals,
            yerr=np.vstack((vals - lows, highs - vals)),
            fmt=markers[contrast], ms=4.5, color=CONTRAST_COLORS[contrast],
            capsize=2, elinewidth=0.9, linestyle="none", label=contrast,
        )
    ax.set_title("(b) Stage-II reference loss")
    ax.set_ylabel("$L^{\\mathrm{rec}}$")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.05)
    ax.grid(axis="x", visible=False)

    handles, legend_labels = axes[1].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=3,
               frameon=False, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout()
    fig.subplots_adjust(top=0.82, wspace=0.32)
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_2_information_layers.{suffix}")
    plt.close(fig)


def figure_objectives_revised(e3) -> None:
    """Show the zero-change mass and the shift size conditional on a changed target."""
    profiles = ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE")
    objectives = [PROFILE_LABEL[profile] for profile in profiles]
    agreement = np.asarray([
        [e3[str(year)]["profile_summary"][profile]["exact_target_agreement_share"]
         for year in YEARS]
        for profile in profiles
    ])
    conditional_shift = np.asarray([
        [
            e3[str(year)]["profile_summary"][profile]["mean_abs_target_change_min"]
            / (1.0 - e3[str(year)]["profile_summary"][profile]["exact_target_agreement_share"])
            if e3[str(year)]["profile_summary"][profile]["exact_target_agreement_share"] < 1.0
            else 0.0
            for year in YEARS
        ]
        for profile in profiles
    ])

    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.8))
    panels = (
        (axes[0], agreement, "(a) Exact target agreement", "Agreement share", 0.50, 0.80, ".2f"),
        (axes[1], conditional_shift, "(b) Mean shift when targets differ",
         "Conditional mean $|\\Delta u^*|$ (min)", 0.0, float(np.max(conditional_shift)), ".1f"),
    )
    for ax, values, title, colorbar_label, vmin, vmax, number_format in panels:
        image = ax.imshow(values, aspect="auto", cmap="viridis", vmin=vmin, vmax=vmax)
        ax.set_title(title)
        ax.set_xticks(np.arange(len(YEARS)))
        ax.set_xticklabels(YEAR_LABELS)
        ax.set_yticks(np.arange(len(objectives)))
        ax.set_yticklabels(objectives)
        ax.set_xlabel("Evaluation year")
        for row in range(values.shape[0]):
            for col in range(values.shape[1]):
                value = values[row, col]
                text_color = "white" if value >= vmin + 0.58 * (vmax - vmin) else "black"
                ax.text(col, row, format(value, number_format), ha="center", va="center",
                        fontsize=8, color=text_color)
        colorbar = fig.colorbar(image, ax=ax, fraction=0.048, pad=0.03)
        colorbar.set_label(colorbar_label, fontsize=8)
        colorbar.ax.tick_params(labelsize=8)
        ax.grid(False)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(FIG / f"figure_s5_3_objectives.{suffix}")
    plt.close(fig)


# ----------------------------------------------------------------------------- digest
def digest(e1, e2, e3, derived, ladder) -> str:
    out = ["# Six-year backfill numbers (2017--2022)", ""]
    out.append("## Table 5.1 inputs (populations, q0=0.10)")
    for year in YEARS:
        row = e1[str(year)]
        out.append(
            f"- {year}: PRE N={row['nominal_q010']['PRE']['DELAY']['n']} K={row['nominal_q010']['PRE']['DELAY']['k']} | "
            f"TURN N={row['nominal_q010']['TURN']['DELAY']['n']} K={row['nominal_q010']['TURN']['DELAY']['k']} | "
            f"full-eligible={derived[str(year)]['derived_full_stage2_eligible_total']} | "
            f"paired cohort={e2[str(year)]['e2']['reference_cohort_size']} | "
            f"E3 pairs={e3[str(year)]['joint_marginal_pair_count']}"
        )
    out += ["", "## E1 screening loss at q0=0.10 (L^att, 95% CI for DELAY)"]
    for year in YEARS:
        for stage in STAGES:
            cells = []
            for view in ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM"):
                cell = e1[str(year)]["nominal_q010"][stage][view]
                cells.append(f"{VIEW_LABEL[view]}={cell['attention_loss']:.4f} (repl {cell['replacement']}/{cell['k']})")
            out.append(f"- {year} {stage}: " + "; ".join(cells))
    out += ["", "## E1 q grid (L^att by q)"]
    for view in ("DELAY", "DELAY_PASSENGER", "DELAY_DOWNSTREAM"):
        for stage in STAGES:
            vals = []
            for q in (0.05, 0.10, 0.20, 0.30):
                per_year = []
                for year in YEARS:
                    row = next(r for r in e1[str(year)]["q_grid"]
                               if r["stage"] == stage and abs(r["q"] - q) < 1e-9 and r["view"] == view)
                    per_year.append(row["attention_loss"])
                vals.append(f"q={q}: mean={statistics.fmean(per_year):.4f} [{min(per_year):.4f},{max(per_year):.4f}]")
            out.append(f"- {VIEW_LABEL[view]} {stage}: " + "; ".join(vals))
    out += ["", "## E2 paired contrasts"]
    for year in YEARS:
        info = e2[str(year)]["e2"]["information_value"]
        out.append(f"- {year} cohort={e2[str(year)]['e2']['reference_cohort_size']}:")
        for component in ("ROLLING_HISTORY", "DISTRIBUTIONAL_INFORMATION", "CROSS_STATE_DEPENDENCE",
                          "MARGINAL_UNCERTAINTY"):
            row = info[component]
            out.append(
                f"    - {component} ({row['comparator']}): displaced_share={row['stage1_reassigned_share']} "
                f"L_att={row['L_att']} [{row['L_att_ci_low']},{row['L_att_ci_high']}] "
                f"A0={row['A0']} A5={row['A5']} L_rec={row['L_rec']} [{row['L_rec_ci_low']},{row['L_rec_ci_high']}] "
                f"dJ={row['delta_J']} Vref={row['reference_V']}"
            )
    out += ["", "## E3 objective rows"]
    for year in YEARS:
        for profile in ("BALANCED", "FLIGHT", "PASSENGER", "RESOURCE"):
            row = e3[str(year)]["profile_summary"][profile]
            out.append(
                f"- {year} {PROFILE_LABEL[profile]}: agreement={row['exact_target_agreement_share']} "
                f"dep-sensitive={row['dependence_sensitive_share']} mean|du|={row['mean_abs_target_change_min']} "
                f"activation={row['activation_share_joint']} zeroV={row['zero_recoverable_value_share_joint']} "
                f"medianV={row['median_V_joint']} medianMargin={row['median_decision_margin_joint']}"
            )
    out += ["", "## E4 cohort-size ladder (M5-b battery, reproduced in the cloud run)"]
    for year in YEARS:
        row = ladder[str(year)]
        out.append(
            f"- {year}: decision={row['decision']['status']} evaluation_E={row['evaluation_E']} "
            f"failed_instances={len(row['decision']['failed_instances'])} "
            f"(eval={sum(1 for k in row['decision']['failed_instances'] if ':eval:' in k)}, "
            f"fit={sum(1 for k in row['decision']['failed_instances'] if ':fit:' in k)})"
        )
    return "\n".join(out) + "\n"


def main() -> int:
    TAB.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    e1 = _load("e1_six_year.json")
    e2 = _load("e2_six_year.json")
    e3 = _load("e3_six_year.json")
    derived = _load("derived_and_checks.json")["derived_populations"]
    ladder = _load("derived_and_checks.json")["e4_ladder"]

    (TAB / "table_5_1.tex").write_text(table_5_1(e2, e3) + "\n", encoding="utf-8")
    (TAB / "table_5_2.tex").write_text(table_5_2(e2) + "\n", encoding="utf-8")
    (TAB / "table_sup_support.tex").write_text(table_sup_support(e1, e2, derived, e3) + "\n", encoding="utf-8")
    (TAB / "table_sup_e1.tex").write_text(table_sup_e1(e1) + "\n", encoding="utf-8")
    (TAB / "table_sup_e1_q.tex").write_text(table_sup_e1_q(e1) + "\n", encoding="utf-8")
    (TAB / "table_sup_e2_support.tex").write_text(table_sup_e2_support(e2) + "\n", encoding="utf-8")
    (TAB / "table_sup_e3.tex").write_text(table_sup_e3(e3) + "\n", encoding="utf-8")
    (TAB / "table_sup_ladder.tex").write_text(table_sup_ladder(ladder) + "\n", encoding="utf-8")

    figure_q_boundary_revised(e1)
    figure_information_layers(e2)
    figure_objectives_revised(e3)

    (ROOT / "numbers.md").write_text(digest(e1, e2, e3, derived, ladder), encoding="utf-8")
    print("tables:", sorted(p.name for p in TAB.glob("*.tex")))
    print("figures:", sorted(p.name for p in FIG.glob("*.pdf")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
