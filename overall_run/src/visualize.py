"""Manuscript-ready figures generated only from frozen metric/artifact tables."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .visualize_common import CHANNELS, STAGES, save_figure
from .visualize_representative import _figure_representative
STAGES = ("t1", "t2", "t3")
ACTION_FAMILY_ORDER = ("null", "hold", "retime", "protect", "support", "combined")




def _read_first(paths: Iterable[Path]) -> pd.DataFrame:
    for path in paths:
        if path.exists():
            return pd.read_parquet(path)
    return pd.DataFrame()


def _available_stages(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "snapshot_stage" not in frame:
        return []
    available = set(frame["snapshot_stage"].dropna().astype(str))
    return [stage for stage in STAGES if stage in available]


def _finite(values: pd.Series | np.ndarray) -> np.ndarray:
    result = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(float)
    return result[np.isfinite(result)]


def _figure_m2(m2: pd.DataFrame, out: Path, run_dir: Path | None = None) -> None:
    if m2.empty:
        return
    stages = _available_stages(m2)
    if not stages:
        return
    fig, axes = plt.subplots(1, 3, figsize=(14.2, 4.2))

    # A. Constructed RMB costs. Each box is an episode-level expected cost.
    positions: list[float] = []
    values: list[np.ndarray] = []
    labels: list[str] = []
    position = 1.0
    for stage in stages:
        for channel in CHANNELS:
            column = f"cost_rmb_mean_{channel}"
            current = _finite(m2.loc[m2["snapshot_stage"].eq(stage), column]) if column in m2 else np.array([])
            if len(current):
                positions.append(position)
                values.append(current)
                labels.append(f"{stage}\n{channel}")
            position += 1.0
        position += 0.5
    if values:
        bp = axes[0].boxplot(values, positions=positions, widths=0.65, whis=(5, 95), showfliers=False)
        axes[0].set_xticks(positions, labels)
    axes[0].set_ylabel("Constructed cost (RMB)")
    axes[0].set_title("A. Channel-cost distributions\nCentral 90% distribution")

    # B. Mean channel composition by stage.
    composition = []
    for stage in stages:
        subset = m2[m2["snapshot_stage"].eq(stage)]
        means = np.asarray([
            pd.to_numeric(subset.get(f"cost_rmb_mean_{channel}"), errors="coerce").mean()
            for channel in CHANNELS
        ], dtype=float)
        total = np.nansum(means)
        composition.append(means / total if np.isfinite(total) and total > 0 else np.zeros(3))
    composition_array = np.vstack(composition)
    bottom = np.zeros(len(stages))
    for index, channel in enumerate(CHANNELS):
        axes[1].bar(stages, composition_array[:, index], bottom=bottom, label=channel)
        bottom += composition_array[:, index]
    axes[1].set_ylim(0, 1)
    axes[1].set_ylabel("Share of mean pre-action cost")
    axes[1].set_title("B. F/P/R cost composition")
    axes[1].legend(title="Channel", frameon=False)

    # C. Frozen graph-edge exposure increments. These are not causal estimates.
    # 从正式运行 artifact 读取图边系数
    if run_dir:
        config_path = run_dir / "merged_config.json"
        if config_path.exists():
            import json
            merged = json.loads(config_path.read_text(encoding="utf-8"))
            graph_edges = merged.get("m2", {}).get("graph_edges", {})
    edge_columns = [column for column in m2 if column.startswith("edge_contribution_")]
    edge_labels = [column.replace("edge_contribution_", "").replace("_to_", "→") for column in edge_columns]
    if edge_columns:
        x = np.arange(len(stages), dtype=float)
        width = 0.8 / max(len(edge_columns), 1)
        for index, (column, label) in enumerate(zip(edge_columns, edge_labels)):
            estimates = [
                pd.to_numeric(
                    m2.loc[m2["snapshot_stage"].eq(stage), column], errors="coerce"
                ).mean()
                for stage in stages
            ]
            axes[2].bar(x + (index - (len(edge_columns) - 1) / 2) * width, estimates, width, label=label)
        axes[2].set_xticks(x, stages)
        axes[2].legend(title="graph_edges", frameon=False, fontsize="small")
    axes[2].set_ylabel("Mean exposure increment")
    axes[2].set_title("C. Cross-channel coupling")
    fig.tight_layout()
    save_figure(fig, out)


def _figure_m3(samples: pd.DataFrame, parameters: pd.DataFrame, out: Path) -> None:
    if samples.empty:
        return
    action_ids = sorted(samples.loc[samples["action_id"].ne("A00"), "action_id"].astype(str).unique())
    if not action_ids:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13.6, 6.0), sharey=True)
    y = np.arange(len(action_ids), dtype=float)
    offsets = {"F": -0.22, "P": 0.0, "R": 0.22}
    # 找到分割位置: A52 与 A61 之间
    split_y = None
    for i, aid in enumerate(action_ids):
        if aid == "A52":
            split_y = i + 0.5
            break
    if split_y is not None:
        axes[0].axhline(split_y, color="gray", linestyle="-", linewidth=0.8, alpha=0.5)
        axes[1].axhline(split_y, color="gray", linestyle="-", linewidth=0.8, alpha=0.5)
        axes[1].text(1.05, split_y, "burden-only", transform=axes[1].get_yaxis_transform(),
                     ha="left", va="center", fontsize=9, color="gray", alpha=0.7)

    for channel in CHANNELS:
        means = []
        low = []
        high = []
        costs = []
        cost_low = []
        cost_high = []
        for action_id in action_ids:
            subset = samples[samples["action_id"].astype(str).eq(action_id)]
            recovery = _finite(subset[f"recovery_rate_{channel}"])
            implementation = _finite(subset[f"implementation_cost_rmb_{channel}"])
            means.append(float(np.mean(recovery)) if len(recovery) else np.nan)
            low.append(float(np.quantile(recovery, 0.05)) if len(recovery) else np.nan)
            high.append(float(np.quantile(recovery, 0.95)) if len(recovery) else np.nan)
            costs.append(float(np.mean(implementation)) if len(implementation) else np.nan)
            cost_low.append(float(np.quantile(implementation, 0.05)) if len(implementation) else np.nan)
            cost_high.append(float(np.quantile(implementation, 0.95)) if len(implementation) else np.nan)
        means_a = np.asarray(means)
        costs_a = np.asarray(costs)
        # 区分结构零: recovery_rate == 0 且 implementation_cost > 0
        structural_zero = (means_a == 0) & (costs_a > 0)
        normal = ~structural_zero
        if normal.any():
            axes[0].errorbar(
                means_a[normal],
                (y + offsets[channel])[normal],
                xerr=np.vstack([means_a[normal] - np.asarray(low)[normal], np.asarray(high)[normal] - means_a[normal]]),
                fmt="o",
                capsize=2,
                label=channel,
            )
        if structural_zero.any():
            axes[0].errorbar(
                means_a[structural_zero],
                (y + offsets[channel])[structural_zero],
                xerr=np.vstack([means_a[structural_zero] - np.asarray(low)[structural_zero], np.asarray(high)[structural_zero] - means_a[structural_zero]]),
                fmt="o",
                markerfacecolor="none",
                markeredgecolor=f"C{['F','P','R'].index(channel)}",
                capsize=2,
            )
        axes[1].errorbar(
            costs_a,
            y + offsets[channel],
            xerr=np.vstack([costs_a - np.asarray(cost_low), np.asarray(cost_high) - costs_a]),
            fmt="o",
            capsize=2,
            label=channel,
        )

    axes[0].set_xlim(left=0)
    axes[0].set_xlabel("Recovery rate: mean and 5–95% interval")
    axes[0].set_title("A. Scenario response")
    axes[1].set_xlim(left=0)
    axes[1].set_xlabel("Implementation cost (RMB): mean and 5–95% interval")
    axes[1].set_title("B. Scenario burden")
    axes[0].set_yticks(y, action_ids)
    axes[0].invert_yaxis()
    axes[0].legend(title="Channel", frameon=False)
    axes[1].legend(title="Channel", frameon=False)
    source = "scenario-declared"
    if not parameters.empty and "parameter_source" in parameters:
        unique_sources = sorted(set(parameters["parameter_source"].dropna().astype(str)))
        if unique_sources:
            source = ", ".join(unique_sources)
    a00 = samples[samples["action_id"].astype(str).eq("A00")]
    a00_columns = [
        f"{prefix}_{channel}"
        for prefix in ("recovery_rate", "implementation_cost_rmb")
        for channel in CHANNELS
    ]
    a00_identity = bool(
        len(a00)
        and all(column in a00 for column in a00_columns)
        and np.allclose(a00[a00_columns].to_numpy(float), 0.0)
    )
    fig.suptitle("Frozen M3 scenario-response library")
    fig.text(
        0.5,
        0.01,
        f"A00 identity: recovery rate = 0 and implementation cost = 0 ({'PASS' if a00_identity else 'FAIL'})",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    save_figure(fig, out)


def _figure_m4(candidates: pd.DataFrame, rankings: pd.DataFrame, out: Path) -> None:
    if candidates.empty:
        return
    stages = _available_stages(candidates)
    if not stages:
        return
    nonnull = candidates[candidates["action_id"].astype(str).ne("A00")].copy()
    fig, axes = plt.subplots(1, 3, figsize=(15.4, 4.3))

    # A. Average action counts through the two screening layers.
    count_rows = []
    for stage in stages:
        subset = nonnull[nonnull["snapshot_stage"].eq(stage)]
        grouped = subset.groupby(["episode_id", "snapshot_id"], sort=False)
        count_rows.append({
            "stage": stage,
            "available": float(grouped.size().mean()) if len(subset) else 0.0,
            "physical": float(grouped["physical_feasible"].sum().mean()) if len(subset) else 0.0,
            "decision": float(grouped.apply(lambda g: (g["physical_feasible"] & g["decision_value_pass"]).sum(), include_groups=False).mean()) if len(subset) else 0.0,
            "retained": float(grouped["candidate_flag"].sum().mean()) if len(subset) else 0.0,
        })
    counts = pd.DataFrame(count_rows).set_index("stage")
    if np.allclose(counts["decision"], counts["retained"]):
        counts = counts.drop(columns=["retained"])
    x = np.arange(len(stages))
    width = 0.2
    funnel_labels = {
        "available": "Candidate",
        "physical": "Physically feasible",
        "decision": "DV-pass",
        "retained": "Evaluated",
    }
    funnel_columns = [col for col in ("available", "physical", "decision", "retained") if col in counts]
    for index, column in enumerate(funnel_columns):
        axes[0].bar(x + (index - (len(funnel_columns) - 1) / 2) * width, counts[column], width, label=funnel_labels[column])
    axes[0].set_xticks(x, stages)
    axes[0].set_ylabel("Mean non-null actions per snapshot")
    axes[0].set_title("A. Screening funnel")
    axes[0].legend(frameon=False, fontsize="small")

    # B. Rejection rates by action and gate.
    gate_columns = [
        "gate_capacity", "gate_window", "gate_resource", "gate_authority", "gate_lead",
        "gate_recovery_ratio", "gate_burden_ratio", "gate_positive_net_benefit",
    ]
    gate_columns = [column for column in gate_columns if column in nonnull]
    action_ids = sorted(nonnull["action_id"].astype(str).unique())
    matrix = np.zeros((len(action_ids), len(gate_columns)), dtype=float)
    for row_index, action_id in enumerate(action_ids):
        subset = nonnull[nonnull["action_id"].astype(str).eq(action_id)]
        for column_index, column in enumerate(gate_columns):
            matrix[row_index, column_index] = float((~subset[column].fillna(False).astype(bool)).mean())
    image = axes[1].imshow(matrix, vmin=0, vmax=1, aspect="auto")
    axes[1].set_yticks(range(len(action_ids)), action_ids)
    short_names = [
        name.replace("gate_", "").replace("positive_net_benefit", "positive net benefit").replace("recovery_ratio", "recovery").replace("burden_ratio", "burden")
        for name in gate_columns
    ]
    axes[1].set_xticks(range(len(gate_columns)), short_names, rotation=40, ha="right")
    axes[1].set_title("B. Rejection rate among triggered action rows")
    fig.colorbar(image, ax=axes[1], fraction=0.046, pad=0.04)

    # C. Recommendation composition by stage.
    recommended = rankings[rankings.get("recommended", False).astype(bool)].copy() if not rankings.empty and "recommended" in rankings else pd.DataFrame()
    if not recommended.empty:
        table = pd.crosstab(
            recommended["snapshot_stage"],
            recommended["action_family"],
            normalize="index",
        ).reindex(index=stages, columns=ACTION_FAMILY_ORDER, fill_value=0.0)
        bottom = np.zeros(len(table))
        for family in ACTION_FAMILY_ORDER:
            axes[2].bar(table.index, table[family], bottom=bottom, label=family)
            bottom += table[family].to_numpy(float)
        # 在 null 区域标注 A00 rate
        for i, stage in enumerate(table.index):
            a00_rate = float(table.loc[stage, "null"])
            if a00_rate > 0:
                axes[2].text(i, a00_rate / 2, f"{a00_rate*100:.1f}%",
                             ha="center", va="center", fontsize=9,
                             color="white" if a00_rate > 0.3 else "black")
        axes[2].legend(frameon=False, fontsize="small", ncol=2)
    axes[2].set_ylim(0, 1)
    axes[2].set_ylabel("Recommendation share")
    axes[2].set_title("C. Recommended action family")
    fig.tight_layout()
    save_figure(fig, out)






def generate(run_dir: Path, quantiles: list[float]) -> None:
    del quantiles  # M1 validity is generated once by report.figure_m1_validity.
    metrics = run_dir / "metrics"
    core = run_dir / "figures" / "core"
    audit = run_dir / "figures" / "audit"
    optional = run_dir / "figures" / "optional"
    for path in (core, audit, optional):
        path.mkdir(parents=True, exist_ok=True)

    pred = _read_first([
        metrics / "m1_predictions_evaluation.parquet",
        metrics / "m1_predictions_all_valid.parquet",
    ])
    m2 = _read_first([metrics / "m2_summary.parquet"])
    m3_samples = _read_first([run_dir / "m3_response_samples.parquet"])
    m3_parameters = _read_first([run_dir / "m3_response_parameters.parquet"])
    candidates = _read_first([
        run_dir / "m4_candidate_screen.parquet",
        metrics / "m4_candidate_screen.parquet",
    ])
    rankings = _read_first([
        run_dir / "m4_rankings.parquet",
        metrics / "m4_rankings.parquet",
    ])

    _figure_m2(m2, core / "fig02_channel_reconstruction", run_dir)
    _figure_m3(m3_samples, m3_parameters, core / "fig03_action_response_library")
    _figure_m4(candidates, rankings, core / "fig04_screening_and_recommendation")
    _figure_representative(
        pred,
        m2,
        candidates,
        rankings,
        metrics,
        core / "fig05_representative_episode",
    )
