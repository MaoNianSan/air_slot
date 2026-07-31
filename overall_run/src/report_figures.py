from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _quantile_columns(quantiles: list[float]) -> list[str]:
    return [f"q_{str(q).replace('.', '_')}" for q in quantiles]


def _save_figure(fig: Any, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def figure_m1_validity(
    predictions: pd.DataFrame,
    summary: pd.DataFrame,
    quantiles: list[float],
    out: Path,
) -> None:
    qcols = _quantile_columns(quantiles)
    if predictions.empty or not all(c in predictions.columns for c in qcols):
        return
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.8))

    weights = pd.to_numeric(predictions.get("flight_weight", 1.0), errors="coerce")
    if np.isscalar(weights):
        weights = pd.Series(np.ones(len(predictions)), index=predictions.index)
    weights = weights.fillna(0.0).to_numpy(float)
    if weights.sum() <= 0:
        weights = np.ones(len(predictions), dtype=float)
    observed = [
        float(np.average((predictions["target"] <= predictions[col]).to_numpy(float), weights=weights))
        for col in qcols
    ]
    axes[0].plot(quantiles, observed, marker="o", label="Observed")
    axes[0].plot([0, 1], [0, 1], linestyle="--", label="Ideal")
    axes[0].set_xlabel("Nominal quantile")
    axes[0].set_ylabel("Observed cumulative frequency")
    axes[0].set_title("Quantile calibration")
    axes[0].legend()

    reliability = predictions[["p_exceed_15", "target"]].dropna().copy()
    if len(reliability):
        reliability["event"] = (reliability["target"] > 15.0).astype(float)
        try:
            reliability["bin"] = pd.qcut(
                reliability["p_exceed_15"].rank(method="first"),
                min(8, max(2, len(reliability) // 20)),
                duplicates="drop",
            )
            if "flight_weight" not in reliability.columns:
                reliability["flight_weight"] = 1.0
            bin_rows = []
            for _, group in reliability.groupby("bin", observed=False):
                bin_rows.append(
                    {
                        "predicted": np.average(group["p_exceed_15"], weights=group["flight_weight"]),
                        "observed": np.average(group["event"], weights=group["flight_weight"]),
                        "n": len(group),
                    }
                )
            bins = pd.DataFrame(bin_rows)
            axes[1].plot(bins["predicted"], bins["observed"], marker="o")
        except ValueError:
            axes[1].scatter(reliability["p_exceed_15"], reliability["event"], alpha=0.2)
    axes[1].plot([0, 1], [0, 1], linestyle="--")
    axes[1].set_xlim(0, 1)
    axes[1].set_ylim(0, 1)
    axes[1].set_xlabel("Predicted Pr(Y > 15)")
    axes[1].set_ylabel("Observed frequency")
    axes[1].set_title("Exceedance reliability")

    del summary  # The stage panel is computed directly from the frozen prediction table.
    lower_q = min(quantiles, key=lambda value: abs(float(value) - 0.05))
    upper_q = min(quantiles, key=lambda value: abs(float(value) - 0.95))
    lower_col = f"q_{str(lower_q).replace('.', '_')}"
    upper_col = f"q_{str(upper_q).replace('.', '_')}"
    stage_rows = []
    for stage_name, group in predictions.groupby("snapshot_stage", sort=False):
        if lower_col not in group or upper_col not in group:
            continue
        coverage = float(
            (
                (group["target"] >= group[lower_col])
                & (group["target"] <= group[upper_col])
            ).mean()
        )
        pinball = []
        target = group["target"].to_numpy(float)
        for quantile, column in zip(quantiles, qcols):
            error = target - group[column].to_numpy(float)
            pinball.append(np.maximum(float(quantile) * error, (float(quantile) - 1.0) * error))
        crps = float(2.0 * np.mean(np.vstack(pinball)))
        stage_rows.append((str(stage_name), coverage, crps, len(group)))
    stage_frame = pd.DataFrame(stage_rows, columns=["stage", "coverage", "crps", "n"])
    order = [stage for stage in ["t1", "t2", "t3"] if stage in set(stage_frame["stage"])]
    stage_frame = stage_frame.set_index("stage").reindex(order).dropna(subset=["coverage"])
    axes[2].axhline(0.90, linestyle="--", label="Nominal 90%")
    axes[2].plot(stage_frame.index, stage_frame["coverage"], marker="o", label="Coverage")
    for stage_name, row in stage_frame.iterrows():
        axes[2].annotate(
            f"CRPS = {row['crps']:.2f}\nn = {int(row['n']):,}",
            (stage_name, row["coverage"]),
            xytext=(0, -12),
            textcoords="offset points",
            ha="center",
            va="top",
            fontsize=8,
        )
    for stage_name, row in stage_frame.iterrows():
        axes[2].annotate(
            f"{row['coverage']:.2f}",
            (stage_name, row["coverage"]),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    axes[2].set_ylim(0, 1.05)
    axes[2].margins(x=0.12)
    axes[2].set_xlabel("Snapshot stage")
    axes[2].set_ylabel("Empirical 90% coverage")
    axes[2].set_title("Distributional performance by stage")
    axes[2].legend(frameon=False)

    fig.tight_layout()
    _save_figure(fig, out)


def figure_rolling(
    ranking: pd.DataFrame,
    predictions: pd.DataFrame,
    m3_audit: pd.DataFrame,
    balanced: pd.DataFrame,
    out: Path,
) -> None:
    if ranking.empty or predictions.empty or balanced.empty:
        return
    balanced_ids = set(balanced["flight_id"].astype(str))
    pred = predictions[predictions["flight_id"].astype(str).isin(balanced_ids)].copy()
    rank = ranking[ranking["flight_id"].astype(str).isin(balanced_ids)].copy()
    key_set = set(zip(balanced["episode_id"].astype(str), balanced["snapshot_id"].astype(str)))
    gate = m3_audit[
        [(str(e), str(s)) in key_set for e, s in zip(m3_audit["episode_id"], m3_audit["snapshot_id"])]
    ].copy()
    if pred.empty or rank.empty:
        return

    stages = [s for s in ["t1", "t2", "t3"] if s in set(pred["snapshot_stage"])]
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.8))

    values = [pred.loc[pred["snapshot_stage"] == stage, "p_exceed_15"].to_numpy(float) for stage in stages]
    if values:
        axes[0].boxplot(values, tick_labels=stages, showfliers=False)
    axes[0].set_xlabel("Snapshot stage")
    axes[0].set_ylabel("Pr(Y > 15)")
    axes[0].set_title("Rolling execution risk")

    feasible = gate[gate["is_feasible"]].groupby(["episode_id", "snapshot_id"])["action_id"].nunique().reset_index(name="feasible_count")
    stage_map = pred[["episode_id", "snapshot_id", "flight_id", "snapshot_stage"]].drop_duplicates()
    feasible = feasible.merge(stage_map, on=["episode_id", "snapshot_id"], how="inner")
    pivot = feasible.pivot_table(index="flight_id", columns="snapshot_stage", values="feasible_count", aggfunc="first")
    transitions = []
    labels = []
    for left, right in zip(stages[:-1], stages[1:]):
        if left not in pivot or right not in pivot:
            continue
        diff = pivot[right] - pivot[left]
        transitions.append([
            float((diff < 0).mean()),
            float((diff == 0).mean()),
            float((diff > 0).mean()),
        ])
        labels.append(f"{left}→{right}")
    if transitions:
        arr = np.asarray(transitions)
        bottom = np.zeros(len(arr))
        for j, name in enumerate(["Contracted", "Unchanged", "Expanded"]):
            axes[1].bar(labels, arr[:, j], bottom=bottom, label=name)
            bottom += arr[:, j]
        axes[1].legend(fontsize="small")
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("Flight share")
    axes[1].set_title("Feasible-set transition")

    top = rank[rank["recommended"]].copy()
    top_pivot = top.pivot_table(index="flight_id", columns="snapshot_stage", values="action_family", aggfunc="first")
    families = ["null", "hold", "retime", "protect", "support", "combined"]
    if len(stages) >= 2 and stages[0] in top_pivot and stages[-1] in top_pivot:
        matrix = pd.crosstab(top_pivot[stages[0]], top_pivot[stages[-1]]).reindex(index=families, columns=families, fill_value=0)
        row_total = matrix.sum(axis=1).replace(0, np.nan)
        share = matrix.div(row_total, axis=0).fillna(0.0)
        image = axes[2].imshow(share.to_numpy(float), vmin=0, vmax=1, aspect="auto")
        axes[2].set_xticks(range(len(families)), families, rotation=35, ha="right")
        axes[2].set_yticks(range(len(families)), families)
        axes[2].set_xlabel(stages[-1])
        axes[2].set_ylabel(stages[0])
        axes[2].set_title("Recommended-family transition")
        fig.colorbar(image, ax=axes[2], fraction=0.046, pad=0.04)
    fig.tight_layout()
    _save_figure(fig, out)


def figure_m3_appendix(m3_audit: pd.DataFrame, out: Path) -> None:
    if m3_audit.empty:
        return
    nonnull = m3_audit[m3_audit["action_id"] != "A00"].copy()
    gates = ["capacity", "window", "resource", "authority", "lead"]
    actions = sorted(nonnull["action_id"].unique())
    matrix = np.asarray([
        [float((~nonnull.loc[nonnull["action_id"] == action, f"gate_{gate}"].astype(bool)).mean()) for action in actions]
        for gate in gates
    ])
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.8))
    image = axes[0].imshow(matrix, vmin=0, vmax=1, aspect="auto")
    axes[0].set_xticks(range(len(actions)), actions, rotation=35)
    axes[0].set_yticks(range(len(gates)), gates)
    axes[0].set_title("Gate rejection rate")
    fig.colorbar(image, ax=axes[0], fraction=0.046, pad=0.04)
    feasible = nonnull.groupby("action_id")["is_feasible"].mean().reindex(actions)
    axes[1].bar(actions, feasible)
    axes[1].set_ylim(0, 1)
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].set_ylabel("Feasible share")
    axes[1].set_title("Action feasibility")
    fig.tight_layout()
    _save_figure(fig, out)


def figure_precision(action_compare: pd.DataFrame, summary: pd.DataFrame, out: Path) -> None:
    if action_compare.empty:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9.8, 3.8))
    x = np.sort(action_compare["relative_score_error"].to_numpy(float))
    y = np.arange(1, len(x) + 1) / len(x)
    axes[0].plot(x, y)
    axes[0].axvline(0.02, linestyle="--")
    axes[0].axvline(0.05, linestyle=":")
    axes[0].set_xlabel("Relative action-score error")
    axes[0].set_ylabel("ECDF")
    axes[0].set_title("Score convergence")
    rank_metrics = summary[summary["metric"].isin(["top1_agreement", "top3_overlap", "median_kendall_tau"])].copy()
    labels = {"top1_agreement": "Top-1", "top3_overlap": "Top-3", "median_kendall_tau": "Kendall τ"}
    axes[1].bar([labels[x] for x in rank_metrics["metric"]], rank_metrics["estimate"])
    axes[1].axhline(0.95, linestyle="--")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_ylabel("Agreement")
    axes[1].set_title("Ranking convergence")
    fig.tight_layout()
    _save_figure(fig, out)


