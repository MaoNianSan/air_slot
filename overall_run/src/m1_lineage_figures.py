from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .m1_lineage_contract import FIGURE_ROOT, PROJECT_ROOT, QUANTILES


def _save_figure(fig: plt.Figure, stem: str) -> list[str]:
    FIGURE_ROOT.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ("png", "pdf", "svg"):
        path = FIGURE_ROOT / f"{stem}.{suffix}"
        fig.savefig(path, dpi=300 if suffix == "png" else None, bbox_inches="tight")
        paths.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    plt.close(fig)
    return paths


def generate_figures(context: dict[str, Any]) -> dict[str, list[str]]:
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9})
    outputs: dict[str, list[str]] = {}

    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.axis("off")
    nodes = [
        (0.03, 0.67, "Raw model\nquantiles", "#d9e8f5"),
        (0.25, 0.67, "Residual\ncalibration", "#f6e3b4"),
        (0.47, 0.67, "Isotonic\nprojection", "#d8ead2"),
        (0.69, 0.67, "Final published\nquantiles", "#cfe7df"),
        (0.69, 0.20, "Predictive\nsamples", "#ead7e8"),
    ]
    for x, y, label, color in nodes:
        ax.add_patch(plt.Rectangle((x, y), 0.17, 0.16, facecolor=color, edgecolor="#404040"))
        ax.text(x + 0.085, y + 0.08, label, ha="center", va="center", weight="bold")
    for start, end in [((0.20, 0.75), (0.25, 0.75)), ((0.42, 0.75), (0.47, 0.75)), ((0.64, 0.75), (0.69, 0.75)), ((0.775, 0.67), (0.775, 0.36))]:
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "lw": 1.5})
    ax.text(0.05, 0.53, "raw crossing: 547 rows", color="#2b5d7d")
    ax.text(0.48, 0.53, "projection after calibration", color="#365d32")
    ax.text(0.68, 0.48, "coverage, pinball, CRPS, twCRPS,\nq95/q99, Brier, trigger", ha="left")
    ax.text(0.68, 0.07, "M2 reconstruction reads these samples", ha="left")
    ax.set_title("Figure A. Current M1 metric lineage map")
    outputs["figure_a"] = _save_figure(fig, "figure_a_metric_lineage_map")

    metrics = ["Coverage90", "CRPS", "twCRPS", "q95 exceed", "q99 exceed"]
    values = [
        context["values"]["coverage90"], context["values"]["crps"],
        context["values"]["twcrps"], context["values"]["q95_exceedance"],
        context["values"]["q99_exceedance"],
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), gridspec_kw={"width_ratios": [1.3, 1]})
    axes[0].bar(metrics, values, color=["#4c8c6b", "#5c7ea8", "#8b6f9d", "#c47b5b", "#d0a746"])
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].set_title("Current authoritative Fast metrics")
    for i, value in enumerate(values):
        axes[0].text(i, value, f"{value:.4g}", ha="center", va="bottom")
    axes[1].axis("off")
    axes[1].text(0.03, 0.80, "Historical D6 values omitted", fontsize=13, weight="bold")
    axes[1].text(0.03, 0.57, "HISTORICAL_ARTIFACT_INCOMPLETE\nNON_AUTHORITATIVE\nPROHIBITED_FOR_FORMAL_USE", fontsize=11)
    axes[1].text(0.03, 0.26, "No delta is plotted. Deprecation is evidence\ngovernance, not scientific reconciliation.")
    fig.suptitle("Figure B. Current metric identity and historical disposition")
    outputs["figure_b"] = _save_figure(fig, "figure_b_current_identity_historical_disposition")

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    points = [context["values"]["q95_exceedance"], context["values"]["q99_exceedance"]]
    ax.scatter([0, 1], points, s=90, color=["#b85c4a", "#4f7d72"], zorder=3)
    ax.axhline(0.05, color="#333333", linestyle="--", label="current code review threshold 0.05")
    ax.set_xticks([0, 1], ["q95 exceedance", "q99 exceedance"])
    ax.set_ylabel("Empirical exceedance probability")
    ax.set_ylim(0, 0.08)
    for x, value in enumerate(points):
        ax.text(x, value + 0.003, f"{value:.6f}\n6 events; CI unavailable", ha="center")
    ax.legend(loc="lower left")
    ax.set_title("Figure C. Current q95/q99 calibration evidence (Fast only)")
    outputs["figure_c"] = _save_figure(fig, "figure_c_q95_q99_calibration_evidence")

    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.6))
    axes[0].bar(["Formal evaluation", "Outcome-selected tail"], [640, int(context["tail_mask"].sum())], color=["#4c8c6b", "#c47b5b"])
    axes[0].set_ylabel("Rows")
    axes[0].set_title("Support")
    axes[1].bar(["Coverage90", "Tail diagnostic"], [context["values"]["coverage90"], context["values"]["tail_coverage90"]], color=["#4c8c6b", "#c47b5b"])
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("Observed coverage")
    axes[1].set_title("Different cohorts; not directly comparable")
    fig.suptitle("Figure D. Tail support and diagnostic uncertainty")
    outputs["figure_d"] = _save_figure(fig, "figure_d_tail_support_uncertainty")
    return outputs


