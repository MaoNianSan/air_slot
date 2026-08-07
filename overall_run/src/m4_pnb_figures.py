from __future__ import annotations

LEGACY_M4_NOT_FORMAL = True

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .m4_pnb_contract import NON_NULL_ACTIONS
from .m4_pnb_sensitivity import PARAMETER_GRIDS


def _save_triplet(fig: plt.Figure, stem: Path) -> list[Path]:
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = [stem.with_suffix(suffix) for suffix in (".png", ".pdf", ".svg")]
    fig.savefig(paths[0], dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(paths[1], bbox_inches="tight", facecolor="white")
    fig.savefig(paths[2], bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def create_pnb_figures(
    frame: pd.DataFrame,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    colors = {
        "hold": "#3b6fb6", "retime": "#c44e52", "protect": "#55a868",
        "support": "#8172b3", "combined": "#cc7a00",
    }
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), sharex=True, constrained_layout=True)
    for ax, stratum in zip(axes, ("LOW", "MEDIUM", "HIGH")):
        subset = frame[frame["cost_stratum"].eq(stratum)]
        for family, group in subset.groupby("action_family", observed=True):
            ax.scatter(
                group["expected_implementation_cost_rmb"],
                group["expected_recovered_cost_rmb"],
                s=22,
                alpha=0.55,
                color=colors.get(str(family), "#555555"),
                label=str(family),
            )
        x_max = float(subset["expected_implementation_cost_rmb"].max()) * 1.08
        y_max = float(subset["expected_recovered_cost_rmb"].max()) * 1.05
        reference_max = min(x_max, y_max)
        ax.plot(
            [0, reference_max], [0, reference_max],
            color="#222222", linestyle="--", linewidth=1,
        )
        ax.set_xlim(0, x_max)
        ax.set_ylim(0, y_max)
        ax.set_title(f"{stratum} pre-action cost")
        ax.set_xlabel("Expected implementation (RMB)")
    axes[0].set_ylabel("Expected recovered cost (RMB)")
    handles, labels = axes[-1].get_legend_handles_labels()
    axes[-1].legend(handles, labels, fontsize=8, frameon=False)
    fig.suptitle("Recovered RMB versus implementation RMB")
    outputs = _save_triplet(fig, output_dir / "m4_pnb_a_recovered_vs_implementation")

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.8), sharey=True, constrained_layout=True)
    for ax, stratum in zip(axes, ("LOW", "MEDIUM", "HIGH")):
        subset = frame[frame["cost_stratum"].eq(stratum)]
        data = [
            subset.loc[subset["action_id"].eq(action), "positive_net_benefit_probability"]
            for action in NON_NULL_ACTIONS
        ]
        ax.boxplot(data, tick_labels=NON_NULL_ACTIONS, showfliers=False)
        ax.axhline(0.60, color="#c44e52", linestyle="--", linewidth=1.2)
        ax.set_title(f"{stratum} pre-action cost")
        ax.set_xlabel("Action")
        ax.tick_params(axis="x", rotation=45)
    axes[0].set_ylabel("Positive-net-benefit probability")
    fig.suptitle("Positive-net-benefit probability by action and cost stratum")
    outputs += _save_triplet(fig, output_dir / "m4_pnb_b_probability_by_action_cost")

    independent_counts = [
        len(frame),
        int(frame["physical_feasible"].sum()),
        int(frame["gate_burden_ratio"].sum()),
        int(frame["positive_net_benefit_pass"].sum()),
        int(frame["decision_value_pass"].sum()),
        int(frame["final_candidate"].sum()),
    ]
    independent_labels = ["Triggered", "Physical", "Burden", "PNB", "All value", "Final"]
    cumulative_masks = [
        pd.Series(True, index=frame.index),
        frame["physical_feasible"],
        frame["physical_feasible"] & frame["gate_burden_ratio"],
        frame["physical_feasible"] & frame["gate_burden_ratio"] & frame["positive_net_benefit_pass"],
        frame["final_candidate"],
    ]
    cumulative_counts = [int(mask.sum()) for mask in cumulative_masks]
    cumulative_labels = ["Triggered", "Physical", "+ Burden", "+ PNB", "Final"]
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.0), constrained_layout=True)
    for ax, labels, counts, title in (
        (axes[0], independent_labels, independent_counts, "Independent gate pass counts"),
        (axes[1], cumulative_labels, cumulative_counts, "Cumulative retention funnel"),
    ):
        bars = ax.bar(labels, counts, color=["#555555", "#3b6fb6", "#55a868", "#8172b3", "#c44e52", "#cc7a00", "#2f7f6f"][:len(labels)])
        for bar, count in zip(bars, counts):
            ax.text(bar.get_x() + bar.get_width() / 2, count + 25, f"{count}\n{count/len(frame):.1%}", ha="center", va="bottom", fontsize=8)
        ax.set_ylim(0, len(frame) * 1.15)
        ax.set_title(title)
        ax.tick_params(axis="x", rotation=28)
    axes[0].set_ylabel("Triggered non-null action rows")
    fig.suptitle("Gate loss decomposition")
    outputs += _save_triplet(fig, output_dir / "m4_pnb_c_gate_loss_decomposition")
    return outputs


def create_parameter_figures(
    sensitivity: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    outputs: list[Path] = []
    q0 = sensitivity["q0"].copy()
    q0["value"] = pd.to_numeric(q0["diagnostic_value"])
    fig, ax = plt.subplots(figsize=(7.5, 4.8), constrained_layout=True)
    ax.plot(q0["value"], q0["final_candidate_rate"], marker="o", label="Final candidate")
    ax.plot(q0["value"], q0["non_null_recommendation_rate"], marker="s", label="Non-null recommendation")
    ax.axvline(0.60, color="#c44e52", linestyle="--", label="Formal q0")
    ax.set_xlabel("Offline q0 diagnostic value")
    ax.set_ylabel("Rate")
    ax.set_title("q0 retention curve (not used for formal recommendation)")
    ax.legend(frameon=False)
    outputs += _save_triplet(fig, output_dir / "m4_q0_retention_curve")

    oat = sensitivity["all_oat"]
    fig, ax = plt.subplots(figsize=(9.0, 5.0), constrained_layout=True)
    parameters = list(PARAMETER_GRIDS)
    x = np.arange(len(parameters))
    candidate = [
        float(oat.loc[oat["parameter"].eq(parameter), "candidate_set_disagreement_vs_formal"].max())
        for parameter in parameters
    ]
    recommendation = [
        float(oat.loc[oat["parameter"].eq(parameter), "recommendation_disagreement_vs_formal"].max())
        for parameter in parameters
    ]
    width = 0.36
    ax.bar(x - width / 2, candidate, width, label="Candidate-set disagreement")
    ax.bar(x + width / 2, recommendation, width, label="Recommendation disagreement")
    labels = {
        "b0": "b0", "q0": "q0", "lambda": "lambda",
        "alpha": "alpha", "near_equivalent_relative": "near tol.",
    }
    ax.set_xticks(x, [labels[parameter] for parameter in parameters])
    ax.set_ylabel("Maximum disagreement versus formal")
    ax.set_title("M4 parameter stability across declared OAT grids")
    ax.legend(frameon=False)
    outputs += _save_triplet(fig, output_dir / "m4_parameter_stability")

    strata = sensitivity["cost_strata"]
    strata = strata[strata["parameter"].eq("q0")].copy()
    strata["value"] = pd.to_numeric(strata["diagnostic_value"])
    fig, ax = plt.subplots(figsize=(7.8, 4.8), constrained_layout=True)
    for stratum, group in strata.groupby("cost_stratum", sort=True, observed=True):
        group = group.sort_values("value")
        ax.plot(group["value"], group["final_candidate_rate"], marker="o", label=str(stratum))
    ax.axvline(0.60, color="#c44e52", linestyle="--", label="Formal q0")
    ax.set_xlabel("Offline q0 diagnostic value")
    ax.set_ylabel("Final candidate rate")
    ax.set_title("Cost-strata parameter response")
    ax.legend(frameon=False)
    outputs += _save_triplet(fig, output_dir / "m4_cost_strata_parameter_response")
    return outputs


