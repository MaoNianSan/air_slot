import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


ROOT = Path(r"D:\Local_Projects\airslot")
DATA = ROOT / "backfill_20261014" / "extracted"
OUT = ROOT / "reports" / "section5_candidate_20261017_v3" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
YEAR_LABELS = ("'17", "'18", "'19", "'20", "'21", "'22")
CONTRASTS = {
    "HM–HJ": ("CROSS_STATE_DEPENDENCE", "#0072B2", "o"),
    "HP–HJ": ("DISTRIBUTIONAL_INFORMATION", "#D55E00", "s"),
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.labelsize": 8.2,
        "axes.titlesize": 9.0,
        "xtick.labelsize": 7.6,
        "ytick.labelsize": 7.6,
        "legend.fontsize": 7.6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#d9d9d9",
        "grid.linewidth": 0.55,
        "grid.alpha": 0.7,
    }
)


def read_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


e2 = read_json("e2_six_year.json")
fig, axs = plt.subplots(2, 2, figsize=(8.0, 5.35))
x = np.arange(len(YEARS))
offsets = {"HM–HJ": -0.09, "HP–HJ": 0.09}

panel_specs = [
    ("stage1_reassigned_share", "Stage-I shortlist positions reassigned", "Share of HJ shortlist (%)", 0, 100, "a"),
    ("L_att", "Stage-I normalized reference loss", r"$L^{\mathrm{att}}$", 0, 0.62, "b"),
    ("agreement", "Stage-II action agreement: exact vs ≤5 min", "Share of fixed HJ cohort", 0, 1.0, "c"),
    ("L_rec", "Stage-II normalized reference loss", r"$L^{\mathrm{rec}}$", 0, 1.05, "d"),
]

for ax, (metric, title, ylabel, ymin, ymax, letter) in zip(axs.flat, panel_specs):
    for contrast, (key, color, marker) in CONTRASTS.items():
        values, lows, highs = [], [], []
        for year in YEARS:
            row = e2[str(year)]["e2"]["information_value"][key]
            if metric == "stage1_reassigned_share":
                value = row[metric] * 100
                low = high = value
            elif metric == "agreement":
                continue
            else:
                value = row[metric]
                low = row.get(metric + "_ci_low", value)
                high = row.get(metric + "_ci_high", value)
            values.append(value)
            lows.append(low)
            highs.append(high)

        if metric == "agreement":
            a0, a5 = [], []
            for year in YEARS:
                row = e2[str(year)]["e2"]["information_value"][key]
                a0.append(row["A0"])
                a5.append(row["A5"])
            pos = x + offsets[contrast]
            ax.plot(
                pos,
                a0,
                linestyle="none",
                marker=marker,
                color=color,
                markerfacecolor=color,
                markeredgecolor=color,
                markersize=4.2,
            )
            ax.plot(
                pos,
                a5,
                linestyle="none",
                marker=marker,
                color=color,
                markerfacecolor="white",
                markeredgecolor=color,
                markeredgewidth=1.05,
                markersize=4.4,
            )
            continue

        values, lows, highs = map(np.asarray, (values, lows, highs))
        pos = x + offsets[contrast]
        if metric in ("L_att", "L_rec"):
            ax.errorbar(
                pos,
                values,
                yerr=np.vstack((values - lows, highs - values)),
                fmt=marker,
                color=color,
                markersize=4.1,
                capsize=1.8,
                elinewidth=0.85,
                linestyle="none",
            )
        else:
            ax.plot(pos, values, linestyle="none", marker=marker, color=color, markersize=4.2)

    ax.set_title(f"({letter}) {title}", loc="left")
    ax.set_ylabel(ylabel)
    ax.set_ylim(ymin, ymax)
    ax.set_xticks(x, YEAR_LABELS)
    ax.grid(axis="x", visible=False)
    if metric == "stage1_reassigned_share":
        ax.set_yticks([0, 25, 50, 75, 100])
    elif metric in ("agreement", "L_rec"):
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])

contrast_handles = [
    Line2D(
        [0],
        [0],
        marker=marker,
        color="none",
        markerfacecolor=color,
        markeredgecolor=color,
        markersize=4.5,
        label=contrast,
    )
    for contrast, (_key, color, marker) in CONTRASTS.items()
]
fig.legend(
    handles=contrast_handles,
    loc="upper center",
    ncol=2,
    frameon=False,
    bbox_to_anchor=(0.5, 1.01),
    columnspacing=1.8,
    handletextpad=0.4,
)
axs[1, 0].text(
    0.5,
    -0.22,
    "Filled markers: exact A0; open markers: within-5-min A5",
    transform=axs[1, 0].transAxes,
    ha="center",
    va="top",
    fontsize=7.4,
)
fig.subplots_adjust(left=0.09, right=0.985, bottom=0.13, top=0.88, hspace=0.42, wspace=0.28)
fig.savefig(OUT / "figure_5_2_information_layers_a5_v3.pdf")
fig.savefig(OUT / "figure_5_2_information_layers_a5_v3.png", dpi=300)
plt.close(fig)
