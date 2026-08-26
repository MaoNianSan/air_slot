"""Paper-oriented secondary analysis of the saved Exp1--Exp4 Development outputs.

This module never trains a model, mutates an experiment artifact, or accesses the
Final Test split.  It only reads the saved outputs and writes presentation-ready
tables and figures.  Empirical uncertainty is always clustered by aircraft-linked
episode: decision nodes are aggregated inside an episode before bootstrap
resampling across episodes.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = Path("outputs/manuscript_values/section5_secondary_analysis")

EXP1_SUMMARY = Path("artifacts/experiment/exp1_full_development/exp1_summary.json")
EXP2_SUMMARY = Path("artifacts/experiments/exp2/full_development_v1/exp2_summary.json")
EXP3_SUMMARY = Path("artifacts/experiments/exp3/full_development_v1/exp3_summary.json")
EXP4_SUMMARY = Path("artifacts/experiments/exp4/full_development_v1/exp4_summary.json")
EXP2_SCENARIOS = Path(
    "artifacts/experiments/exp2/full_development_scenarios_v1/"
    "M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet"
)
EXP2_LABELS = Path(
    "artifacts/experiment/full_development_inputs_v1/"
    "M1_V2_FULL_DEVELOPMENT_LABELS.json"
)
EXP3_ACTION_RISK = Path(
    "artifacts/experiments/exp3/full_development_v1/"
    "EXP3_FULL_DEVELOPMENT_ACTION_RISK.parquet"
)
EXP2A_POINT_RECORDS = Path(
    "artifacts/experiment/exp2/exp2a_point_variogram_closure_20260825/"
    "EXP2A_POINT_VARIOGRAM_RECORDS_DEVELOPMENT_ONLY.parquet"
)
EXP2A_VARIOGRAM_SUMMARIES = Path(
    "artifacts/experiment/exp2/exp2a_point_variogram_closure_20260825/"
    "EXP2A_VARIOGRAM_SUMMARIES_DEVELOPMENT_ONLY.csv"
)
EXP3_VALUATION_RECORDS = Path(
    "artifacts/experiment/exp3/exp3_valuation_only_sensitivity_20260825/"
    "EXP3_VALUATION_ONLY_RECORDS_DEVELOPMENT_ONLY.parquet"
)
EXP4_GRID = Path(
    "artifacts/experiment/exp4/exp4_per_node_records_20260825/"
    "EXP4_LEAD_TIME_GRID_DEVELOPMENT_ONLY.csv"
)
EXP3_FIGURE7A_EPISODE_VALUES = Path(
    "artifacts/experiment/exp3/exp3_refresh_sync_20260826/"
    "EXP3_FIGURE7A_EPISODE_VALUES_DEVELOPMENT_ONLY.csv"
)
EXP3_FIGURE7A_SUMMARY = Path(
    "artifacts/experiment/exp3/exp3_refresh_sync_20260826/"
    "EXP3_FIGURE7A_SUMMARY_DEVELOPMENT_ONLY.csv"
)

REPRESENTATION_LABELS = {
    "POINT": "Point",
    "MARGINAL": "Marginal",
    "JOINT": "Joint",
}
REPRESENTATION_ORDER = ("POINT", "MARGINAL", "JOINT")
COMPARISON_LABELS = {
    "ONE_SHOT_EXECUTABLE": "One-Shot executable (aged)",
    "ROLLING_COMPARABLE": "Rolling refreshed",
    "STATE_SYNC_5": "State-sync delta=5",
    "STATE_SYNC_10": "State-sync delta=10",
}
COMPARISON_ORDER = ("ONE_SHOT_EXECUTABLE", "ROLLING_COMPARABLE", "STATE_SYNC_5", "STATE_SYNC_10")
COMPARISON_TICK_LABELS = ["One-Shot\naged-executable", "Rolling\nrefreshed", "State-sync\nδ=5", "State-sync\nδ=10"]
ESTIMATOR_LABELS = {
    "HISTORICAL": "Historical reference",
    "LIGHTGBM": "LightGBM",
    "RANDOM_FOREST": "Random Forest",
    "STATE_AWARE_H32": "History-conditioned estimator",
}
PALETTE = {
    "blue_main": "#0F4D92",
    "blue_secondary": "#3775BA",
    "neutral": "#CFCECE",
}


@dataclass(frozen=True)
class Estimate:
    estimate: float
    ci_lower: float
    ci_upper: float
    n_episodes: int


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_files(root: Path, relative_paths: Iterable[Path]) -> None:
    missing = [str(path) for path in relative_paths if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError("Missing saved analysis input(s): " + ", ".join(missing))


def episode_bootstrap(
    values: Iterable[float], *, replicates: int = 2000, seed: int = 20260825
) -> Estimate:
    """Episode-cluster estimate and percentile bootstrap confidence interval."""
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        raise ValueError("No finite episode-level values")
    if replicates <= 0:
        raise ValueError("Bootstrap replicates must be positive")
    generator = np.random.default_rng(seed)
    indices = generator.integers(0, len(array), size=(replicates, len(array)))
    bootstrap_means = array[indices].mean(axis=1)
    return Estimate(
        estimate=float(array.mean()),
        ci_lower=float(np.quantile(bootstrap_means, 0.025)),
        ci_upper=float(np.quantile(bootstrap_means, 0.975)),
        n_episodes=int(len(array)),
    )


def _variogram_score(
    draws: np.ndarray, observation: tuple[float, float], *, p: float = 0.5
) -> float | None:
    if not len(draws):
        return None
    observed_distance = abs(observation[0] - observation[1]) ** p
    expected_distance = np.mean(np.abs(draws[:, 0] - draws[:, 1]) ** p)
    return float((expected_distance - observed_distance) ** 2)


def _point_medoid_index(frame: pd.DataFrame) -> int:
    """Match the saved Exp2 coherent weighted-medoid point-collapse rule."""
    ordered = frame.sort_values("scenario_id", kind="stable").reset_index(drop=True)
    weights = ordered["scenario_weight"].to_numpy(dtype=float)
    values = ordered[["D_OB", "D_TX"]].to_numpy(dtype=float)
    distances = np.zeros(len(ordered), dtype=float)
    for column in range(values.shape[1]):
        source = values[:, column]
        available = np.isfinite(source)
        if not available.any():
            continue
        source_values = source[available]
        source_weights = weights[available]
        weight_sum = source_weights.sum()
        first_moment = np.dot(source_weights, source_values)
        second_moment = np.dot(source_weights, source_values * source_values)
        candidates = source
        candidate_available = np.isfinite(candidates)
        distances[candidate_available] += (
            second_moment
            - 2.0 * candidates[candidate_available] * first_moment
            + (candidates[candidate_available] ** 2) * weight_sum
        )
    return int(np.argmin(distances))


def _representation_draws(frame: pd.DataFrame, representation: str) -> np.ndarray:
    ordered = frame.sort_values("scenario_id", kind="stable").reset_index(drop=True)
    values = ordered[["D_OB", "D_TX"]].to_numpy(dtype=float)
    if representation == "JOINT":
        output = values
    elif representation == "MARGINAL":
        output = np.column_stack((values[:, 0], np.roll(values[:, 1], -1)))
    elif representation == "POINT":
        output = values[[_point_medoid_index(ordered)]]
    else:
        raise ValueError(f"Unknown representation: {representation}")
    return output[np.isfinite(output).all(axis=1)]


def exp2_variogram_episode_values(root: Path) -> pd.DataFrame:
    """Recompute Exp2 variograms separately for Point, Marginal, and Joint.

    The saved implementation reused the Joint draws for all three variants.  This
    function changes only that post-processing: each representation is formed from
    the frozen scenario rows before its node-level score is calculated.
    """
    labels_payload = _read_json(root / EXP2_LABELS)
    label_frame = pd.DataFrame(labels_payload["labels"])
    labels = label_frame[
        label_frame["target_name"].isin(("D_OB", "D_TX"))
        & label_frame["active"].astype(bool)
        & label_frame["exact_minutes"].notna()
    ]
    label_pivot = labels.pivot_table(
        index=["episode_id", "decision_node_id"],
        columns="target_name",
        values="exact_minutes",
        aggfunc="first",
    )
    scenario_frame = pd.read_parquet(
        root / EXP2_SCENARIOS,
        columns=["episode_id", "decision_node_id", "scenario_id", "scenario_weight", "D_OB", "D_TX"],
    )
    rows: list[dict[str, object]] = []
    for (episode_id, node_id), node_frame in scenario_frame.groupby(
        ["episode_id", "decision_node_id"], sort=False
    ):
        try:
            observed = label_pivot.loc[(episode_id, node_id)]
        except KeyError:
            continue
        if "D_OB" not in observed or "D_TX" not in observed:
            continue
        observation = (float(observed["D_OB"]), float(observed["D_TX"]))
        if observation[0] >= 210.0 or observation[1] >= 60.0:
            continue
        for representation in REPRESENTATION_ORDER:
            score = _variogram_score(_representation_draws(node_frame, representation), observation)
            if score is not None:
                rows.append(
                    {
                        "episode_id": episode_id,
                        "decision_node_id": node_id,
                        "representation": REPRESENTATION_LABELS[representation],
                        "variogram_score": score,
                    }
                )
    node_values = pd.DataFrame(rows)
    if node_values.empty:
        raise ValueError("No finite Exp2 node-level variogram scores were available")
    point_frame = pd.read_parquet(root / EXP2A_POINT_RECORDS)
    point_frame = point_frame.loc[point_frame["support_status"] == "SUPPORTED"]
    point_values = point_frame[
        ["episode_id", "decision_node_id", "representation", "variogram_score"]
    ].copy()
    combined = pd.concat([node_values, point_values], ignore_index=True)
    return (
        combined.groupby(["episode_id", "representation"], as_index=False)["variogram_score"]
        .mean()
        .sort_values(["representation", "episode_id"], kind="stable")
    )


def exp2_variogram_summaries(episode_values: pd.DataFrame, replicates: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    by_representation = {
        name: group.set_index("episode_id")["variogram_score"]
        for name, group in episode_values.groupby("representation", sort=False)
    }
    available_order = [
        REPRESENTATION_LABELS[item]
        for item in REPRESENTATION_ORDER
        if REPRESENTATION_LABELS[item] in by_representation
    ]
    if "Joint" not in by_representation:
        raise ValueError("Joint representation has no finite Exp2 variogram scores")
    for representation in available_order:
        estimate = episode_bootstrap(by_representation[representation].to_numpy(), replicates=replicates)
        summary_rows.append(
            {
                "representation": representation,
                "variogram_score": estimate.estimate,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "episodes": estimate.n_episodes,
            }
        )
    contrast_rows: list[dict[str, object]] = []
    reference = by_representation["Joint"]
    for representation in available_order:
        if representation == "Joint":
            continue
        paired = pd.concat([by_representation[representation], reference], axis=1, join="inner")
        paired.columns = ["comparison", "joint"]
        difference = paired["comparison"] - paired["joint"]
        estimate = episode_bootstrap(difference.to_numpy(), replicates=replicates)
        contrast_rows.append(
            {
                "contrast": f"{representation} minus Joint",
                "difference_in_variogram_score": estimate.estimate,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "paired_episodes": estimate.n_episodes,
            }
        )
    return pd.DataFrame(summary_rows), pd.DataFrame(contrast_rows)


def exp3_comparison_coverage(root: Path, replicates: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Figure 7A data source: Exp3 refresh/sync records (V3 T3, 2026-08-26).

    Reads the materialized One-Shot/Rolling executable rates and state-sync
    exact-vintage coverage (freeze F3) instead of the pre-T3 action-level
    comparison flags.  Episode values are per-episode rates; the summary is
    the episode-cluster percentile bootstrap (frozen seed 20260825, 2,000
    replicates) written by the materialization manifest.
    """
    del replicates
    episode_values = pd.read_csv(root / EXP3_FIGURE7A_EPISODE_VALUES)
    summary = pd.read_csv(root / EXP3_FIGURE7A_SUMMARY)
    summary["coverage"] = pd.to_numeric(summary["coverage"], errors="coerce")
    summary["ci_lower"] = pd.to_numeric(summary["ci_lower"], errors="coerce")
    summary["ci_upper"] = pd.to_numeric(summary["ci_upper"], errors="coerce")
    summary = summary.set_index("comparison").loc[list(COMPARISON_LABELS)].reset_index()
    summary["comparison"] = summary["comparison"].map(COMPARISON_LABELS)
    episode_values["comparison"] = episode_values["comparison"].map(COMPARISON_LABELS)
    return episode_values, summary


def exp4_benchmark_table(root: Path) -> pd.DataFrame:
    grid = pd.read_csv(root / EXP4_GRID)
    overall = grid.loc[grid["lead_time_bin_minutes"] == "OVERALL"]
    target_labels = {
        "T_IB_A00": "Predecessor availability",
        "D_OB": "Successor off-block delay",
        "D_TX": "Excess taxi delay",
    }
    rows: list[dict[str, object]] = []
    for target, target_label in target_labels.items():
        for estimator_id, estimator_label in ESTIMATOR_LABELS.items():
            cell = overall.loc[
                (overall["target"] == target) & (overall["method"] == estimator_id)
            ]
            mae = cell.loc[cell["metric"] == "MAE_MINUTES"]
            crps = cell.loc[cell["metric"] == "CRPS_MINUTES"]
            mae_value = None if mae.empty else float(mae.iloc[0]["estimate"])
            crps_value = None if crps.empty else float(crps.iloc[0]["estimate"])
            rows.append(
                {
                    "target": target_label,
                    "estimator": estimator_label,
                    "overall_mae_minutes": mae_value,
                    "mae_95_ci": (
                        ""
                        if mae.empty
                        else f"[{float(mae.iloc[0]['ci_lower']):.2f}, {float(mae.iloc[0]['ci_upper']):.2f}]"
                    ),
                    "distributional_score": crps_value,
                    "crps_95_ci": (
                        ""
                        if crps.empty
                        else f"[{float(crps.iloc[0]['ci_lower']):.2f}, {float(crps.iloc[0]['ci_upper']):.2f}]"
                    ),
                    "distributional_score_type": "CRPS (minutes)" if crps_value is not None else "",
                }
            )
    return pd.DataFrame(rows)


def _exp2_point_parity(root: Path, summary: pd.DataFrame) -> None:
    saved = pd.read_csv(root / EXP2A_VARIOGRAM_SUMMARIES)
    saved_point = saved.loc[saved["representation"] == "Point"]
    computed_point = summary.loc[summary["representation"] == "Point"]
    if len(saved_point) != 1 or len(computed_point) != 1:
        raise ValueError("EXP2A_POINT_SUMMARY_PARITY_INCOMPLETE")
    for column in ("variogram_score", "ci_lower", "ci_upper", "episodes"):
        difference = abs(
            float(saved_point.iloc[0][column]) - float(computed_point.iloc[0][column])
        )
        if difference > 1e-9:
            raise ValueError(f"EXP2A_POINT_SUMMARY_PARITY_DRIFT:{column}:{difference}")


def exp3_valuation_band_summary(root: Path, replicates: int) -> pd.DataFrame:
    frame = pd.read_parquet(
        root / EXP3_VALUATION_RECORDS,
        columns=[
            "episode_id", "decision_node_id", "action_id", "valuation_band",
            "conditional_expected_constructed_eur",
        ],
    )
    frame = frame.loc[
        (frame["action_id"] == "A00")
        & frame["conditional_expected_constructed_eur"].notna()
    ]
    rows: list[dict[str, object]] = []
    for band in ("LOW", "BASE", "HIGH"):
        band_frame = frame.loc[frame["valuation_band"] == band]
        episode_values = (
            band_frame.groupby("episode_id")["conditional_expected_constructed_eur"]
            .mean()
            .to_numpy(dtype=float)
        )
        estimate = episode_bootstrap(episode_values, replicates=replicates)
        rows.append(
            {
                "valuation_band": band,
                "expected_constructed_eur": estimate.estimate,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "episodes": estimate.n_episodes,
                "nodes": int(len(band_frame)),
                "claim_status": "ASSUMPTION_GROUNDED",
            }
        )
    return pd.DataFrame(rows)


def _apply_publication_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 15,
            "axes.linewidth": 2.0,
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
        figure.savefig(output_base.with_suffix(f".{extension}"), dpi=600, bbox_inches="tight", pad_inches=0.04)
    plt.close(figure)


def figure_6_variogram(summary: pd.DataFrame, output_base: Path) -> None:
    _apply_publication_style()
    order = [
        REPRESENTATION_LABELS[item]
        for item in REPRESENTATION_ORDER
        if REPRESENTATION_LABELS[item] in set(summary["representation"])
    ]
    ordered = summary.set_index("representation").loc[order].reset_index()
    styles = {
        "Point": (PALETTE["neutral"], ""),
        "Marginal": (PALETTE["blue_secondary"], "//"),
        "Joint": (PALETTE["blue_main"], "\\\\"),
    }
    colors = [styles[name][0] for name in ordered["representation"]]
    hatches = [styles[name][1] for name in ordered["representation"]]
    figure, axis = plt.subplots(figsize=(7.2, 5.2))
    positions = np.arange(len(ordered))
    bars = axis.bar(
        positions,
        ordered["variogram_score"],
        color=colors,
        edgecolor="black",
        linewidth=1.5,
        width=0.64,
    )
    for bar, hatch in zip(bars, hatches, strict=True):
        bar.set_hatch(hatch)
    lower = ordered["variogram_score"] - ordered["ci_lower"]
    upper = ordered["ci_upper"] - ordered["variogram_score"]
    axis.errorbar(
        positions,
        ordered["variogram_score"],
        yerr=np.vstack([lower, upper]),
        fmt="none",
        color="black",
        capsize=4,
        linewidth=1.4,
    )
    axis.set_xticks(positions, ordered["representation"])
    axis.set_ylabel("Variogram score (lower is better)")
    axis.text(0.0, 1.02, "A", transform=axis.transAxes, fontweight="bold", fontsize=16)
    axis.set_ylim(bottom=0)
    figure.tight_layout(pad=1.0)
    _save_figure(figure, output_base)


def figure_7_coverage(summary: pd.DataFrame, output_base: Path) -> None:
    _apply_publication_style()
    order = [COMPARISON_LABELS[item] for item in COMPARISON_ORDER]
    ordered = summary.set_index("comparison").loc[order].reset_index()
    colors = [PALETTE["neutral"], PALETTE["blue_secondary"], PALETTE["blue_main"], PALETTE["blue_main"]]
    hatches = ["", "//", "\\\\", "xx"]
    figure, axis = plt.subplots(figsize=(8.6, 5.2))
    positions = np.arange(len(ordered))
    values = ordered["coverage"] * 100.0
    bars = axis.bar(
        positions,
        values,
        color=colors,
        edgecolor="black",
        linewidth=1.5,
        width=0.64,
    )
    for bar, hatch in zip(bars, hatches, strict=True):
        bar.set_hatch(hatch)
    lower = values - ordered["ci_lower"] * 100.0
    upper = ordered["ci_upper"] * 100.0 - values
    axis.errorbar(
        positions,
        values,
        yerr=np.vstack([lower, upper]),
        fmt="none",
        color="black",
        capsize=4,
        linewidth=1.4,
    )
    axis.set_xticks(positions, COMPARISON_TICK_LABELS)
    axis.set_ylabel("Recovery-comparison coverage (%)")
    axis.set_ylim(0, 105)
    axis.text(0.0, 1.02, "A", transform=axis.transAxes, fontweight="bold", fontsize=16)
    figure.tight_layout(pad=1.0)
    _save_figure(figure, output_base)


def figure_7b_valuation(summary: pd.DataFrame, output_base: Path) -> None:
    _apply_publication_style()
    order = ["LOW", "BASE", "HIGH"]
    ordered = summary.set_index("valuation_band").loc[order].reset_index()
    colors = [PALETTE["neutral"], PALETTE["blue_secondary"], PALETTE["blue_main"]]
    figure, axis = plt.subplots(figsize=(6.4, 5.2))
    positions = np.arange(len(ordered))
    values = ordered["expected_constructed_eur"]
    bars = axis.bar(
        positions,
        values,
        color=colors,
        edgecolor="black",
        linewidth=1.5,
        width=0.6,
    )
    lower = values - ordered["ci_lower"]
    upper = ordered["ci_upper"] - values
    axis.errorbar(
        positions,
        values,
        yerr=np.vstack([lower, upper]),
        fmt="none",
        color="black",
        capsize=4,
        linewidth=1.4,
    )
    axis.set_xticks(positions, ordered["valuation_band"])
    axis.set_ylabel("Expected constructed EUR (reference action A00)")
    axis.set_ylim(bottom=0)
    axis.text(
        0.02, 0.97, "ASSUMPTION_GROUNDED",
        transform=axis.transAxes, fontsize=9, style="italic", va="top",
    )
    axis.text(0.0, 1.02, "B", transform=axis.transAxes, fontweight="bold", fontsize=16)
    figure.tight_layout(pad=1.0)
    _save_figure(figure, output_base)


def figure_8_lead_time(summary: pd.DataFrame, output_base: Path) -> None:
    _apply_publication_style()
    targets = [target for target in ("T_IB_A00", "D_OB") if target in set(summary["target"])]
    metrics = ("MAE_MINUTES", "CRPS_MINUTES")
    metric_labels = {"MAE_MINUTES": "MAE (min)", "CRPS_MINUTES": "CRPS (min)"}
    figure, axes = plt.subplots(len(metrics), len(targets), figsize=(12.8, 8.0), squeeze=False)
    letters = iter("ABCD")
    for column, target in enumerate(targets):
        for row, metric in enumerate(metrics):
            axis = axes[row][column]
            cell = summary.loc[
                (summary["target"] == target) & (summary["metric"] == metric)
                & (summary["lead_time_bin_minutes"] != "OVERALL")
            ]
            for index, (method, label) in enumerate(ESTIMATOR_LABELS.items()):
                method_rows = cell.loc[cell["method"] == method].sort_values(
                    "lead_time_bin_minutes"
                )
                if method_rows.empty:
                    continue
                x = method_rows["lead_time_bin_minutes"].astype(float).astype(int).to_numpy()
                y = method_rows["estimate"].to_numpy(dtype=float)
                lower = method_rows["ci_lower"].to_numpy(dtype=float)
                upper = method_rows["ci_upper"].to_numpy(dtype=float)
                color = f"C{index}"
                axis.plot(x, y, marker="o", markersize=4, linewidth=1.6, color=color, label=label)
                axis.fill_between(x, lower, upper, color=color, alpha=0.14)
            axis.set_xlabel("Lead time (min)")
            axis.set_ylabel(metric_labels[metric])
            axis.set_title(f"{target} - {metric_labels[metric]}")
            axis.set_xticks([0, 120, 240, 360, 480])
            axis.text(0.0, 1.02, next(letters), transform=axis.transAxes, fontweight="bold", fontsize=16)
    handles, labels = axes[0][0].get_legend_handles_labels()
    figure.legend(
        handles, labels, loc="upper center", ncol=4, frameon=False,
        bbox_to_anchor=(0.5, 1.02),
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    _save_figure(figure, output_base)


def _format_number(value: object, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "--"
    return f"{float(value):.{digits}f}"


def _write_table_tex(table: pd.DataFrame, path: Path) -> None:
    rendered = table.copy()
    rendered["overall_mae_minutes"] = rendered["overall_mae_minutes"].map(_format_number)
    rendered["distributional_score"] = rendered["distributional_score"].map(_format_number)
    rendered["mae_95_ci"] = rendered["mae_95_ci"].replace("", "--")
    rendered["crps_95_ci"] = rendered["crps_95_ci"].replace("", "--")
    rendered.columns = [
        "Target",
        "Estimator",
        "Overall MAE (min)",
        "MAE 95\\% CI",
        "Distributional score",
        "CRPS 95\\% CI",
        "Score definition",
    ]
    path.write_text(rendered.to_latex(index=False, escape=False), encoding="utf-8")


def _write_captions(output_root: Path) -> None:
    captions = {
        "figure_6_caption.txt": (
            "Figure 6. Dependence-sensitive predictive score for Point, Marginal, and Joint "
            "representations with finite saved predictive terms. Point uses the frozen F1 "
            "weighted-medoid variogram records over (R_IB, D_OB, D_TX); D_TO is identity-checked "
            "only. Each decision-node score is first averaged within its aircraft-linked episode; "
            "error bars are 95% episode-cluster bootstrap confidence intervals."
        ),
        "figure_7_caption.txt": (
            "Figure 7. (A) Exp3 refresh/sync rates (freeze F3, exact vintage): the One-Shot "
            "recommendation formed at t_i^0 (eq:exp_anchor) remains executable as it ages; the "
            "Rolling recommendation is refreshed at each node; state-sync delta=5/10 report the "
            "fraction of nodes with an exact t-delta vintage (EXP3B_VINTAGE_NOT_AVAILABLE "
            "otherwise; no nearest-past, no fallback, no interpolation). Rates are averaged "
            "within each aircraft-linked episode; error bars are 95% episode-cluster bootstrap "
            "confidence intervals. (B) Valuation-only "
            "sensitivity for the reference action A00: LOW/BASE/HIGH bands move the frozen "
            "five-anchor monetary coefficients only (0.5x/1.0x/2.0x); response parameters stay at "
            "the F4-frozen declared values. Status: ASSUMPTION_GROUNDED, not authoritative."
        ),
        "figure_8_caption.txt": (
            "Figure 8. Per-target lead-time errors for the four estimators. MAE and CRPS are "
            "averaged within each aircraft-linked episode; shaded bands are 95% episode-cluster "
            "bootstrap confidence intervals. D_TX is not plotted: without a planned wheels-off "
            "reference its lead-time bins are NA and no interpolation is applied."
        ),
        "table_1_caption.txt": (
            "Table 1. Predictive benchmark by operational target and estimator from the "
            "Development per-node records. Point estimates are node-level means; 95% confidence "
            "intervals are episode-cluster bootstrap intervals (2,000 replicates). "
            "STATE_AWARE_H32 CRPS is saved only for the finite-support T_IB scope; blank cells "
            "are not available and are not inferred."
        ),
    }
    for name, text in captions.items():
        (output_root / name).write_text(text + "\n", encoding="utf-8")


def _write_audit(output_root: Path, coverage: pd.DataFrame) -> None:
    unavailable_nodes = int(coverage["unavailable_nodes"].max())
    audit = f"""# Paper output audit

## 1. Planned main-text panels with real saved-result support

- Figure 5A--C is generated from the frozen Exp1 closure records (Exp1A 3,538 rows; Exp1B 10,614 rows; frozen sorting diagnostic 1,420/1,765 rows). Exp1A contrasts state-driven vs context-conditioned sorting; Exp1B contrasts the H32 HISTORICAL model with a CURRENT-only comparator under the same architecture, training budget, and calibration path, using each model's own checkpoint. All statistics are computed on the common supported observations; 95% confidence intervals are episode-cluster bootstrap (2,000 replicates, seed 20260825).
- Figure 6A is generated for the Point, Marginal, and Joint predictive representations. Point uses the frozen F1 weighted-medoid variogram records materialized by the Exp2A closure; Marginal and Joint use the saved scenario-level outputs. Scores are aggregated within aircraft-linked episodes and reported with 2,000 episode-cluster bootstrap replicates.
- Figure 7A is generated from the Exp3 refresh/sync records (freeze F3): One-Shot executable (aged) vs Rolling refreshed rates anchored at the first-valid-suggestion time t_i^0 (eq:exp_anchor), plus state-sync coverage at exact-vintage deltas of 5 and 10 minutes. Vintage binding requires decision_time exactly equal to t - delta (P2 exact_vintage_bindings); unmatched nodes are typed EXP3B_VINTAGE_NOT_AVAILABLE with no nearest-past fallback. {unavailable_nodes} decision nodes lacked stored comparison results and are not treated as zero coverage.
- Figure 7B is generated as valuation-only: LOW/BASE/HIGH bands move the frozen five-anchor monetary coefficients only (0.5x/1.0x/2.0x), while response parameters stay at the F4-frozen declared values. The panel shows the reference action A00; the materialized records cover all 23 action envelopes. Status: ASSUMPTION_GROUNDED, not authoritative.
- Figure 8 is generated for T_IB_A00 and D_OB as target x lead-time MAE and CRPS curves with episode-cluster confidence intervals. D_TX is not plotted: without a planned wheels-off reference its lead-time bins are NA and no interpolation is applied.
- Table 1 contains target-specific point estimates and episode-cluster 95% confidence intervals reconstructed from the Development per-node records.

## 2. Outputs that are Development inspection only and cannot yet enter final Test results

- All outputs in this directory are DEVELOPMENT_ONLY (paper_result=false): they are based on the saved Development cohort and are suitable for inspection and manuscript planning, not for final Test-result claims.
- The Exp3 valuation-only records are ASSUMPTION_GROUNDED: the monetary coefficients are assumption-grounded frozen values, not authoritative or causal.

## 3. Panels not generated or intentionally removed

- Figure 6B--C: intentionally removed per F2 (PARTIAL_Q_SERIES_NOT_IMPLEMENTED; q-series frozen). No Figure 6B--C code path, caption, or audit entry is kept.
- Figure 8 panel for D_TX: not drawn because D_TX has no planned wheels-off reference; lead-time bins are NA and are never interpolated.
- STATE_AWARE_H32 D_OB/D_TX CRPS cells are blank: M1 does not save those distributional scores; nothing is inferred.
"""
    (output_root / "paper_output_audit.md").write_text(audit, encoding="utf-8")


def run(*, root: Path = ROOT, output_root: Path | None = None, bootstrap_replicates: int = 2000) -> dict[str, Path]:
    """Generate only the paper panels supported by the current saved outputs."""
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT_ROOT).resolve()
    _require_files(
        root,
        (
            EXP1_SUMMARY, EXP2_SUMMARY, EXP3_SUMMARY, EXP4_SUMMARY,
            EXP2_SCENARIOS, EXP2_LABELS,
            EXP2A_POINT_RECORDS, EXP2A_VARIOGRAM_SUMMARIES,
            EXP3_ACTION_RISK, EXP3_VALUATION_RECORDS, EXP4_GRID,
        ),
    )
    # Read summaries solely to assert the expected Development scope is present;
    # no summary estimate is used as a substitute for detailed values.
    for path in (EXP1_SUMMARY, EXP2_SUMMARY, EXP3_SUMMARY, EXP4_SUMMARY):
        if _read_json(root / path).get("split") != "DEVELOPMENT":
            raise ValueError(f"Unexpected non-Development summary: {path}")

    data_root = output_root / "data"
    figures_root = output_root / "figures"
    tables_root = output_root / "tables"
    for directory in (data_root, figures_root, tables_root):
        directory.mkdir(parents=True, exist_ok=True)

    exp2_episode_values = exp2_variogram_episode_values(root)
    exp2_summary, exp2_contrasts = exp2_variogram_summaries(exp2_episode_values, bootstrap_replicates)
    _exp2_point_parity(root, exp2_summary)
    exp2_episode_values.to_csv(data_root / "figure_6a_variogram_episode_values.csv", index=False)
    exp2_summary.to_csv(data_root / "figure_6a_variogram_summary.csv", index=False)
    exp2_contrasts.to_csv(data_root / "figure_6a_paired_contrasts.csv", index=False)
    figure_6_variogram(exp2_summary, figures_root / "figure_6_uncertainty_representation")

    exp3_episode_values, exp3_summary = exp3_comparison_coverage(root, bootstrap_replicates)
    exp3_episode_values.to_csv(data_root / "figure_7a_comparison_coverage_episode_values.csv", index=False)
    exp3_summary.to_csv(data_root / "figure_7a_comparison_coverage_summary.csv", index=False)
    figure_7_coverage(exp3_summary, figures_root / "figure_7_recovery_comparison_coverage")

    exp3_valuation_summary = exp3_valuation_band_summary(root, bootstrap_replicates)
    exp3_valuation_summary.to_csv(data_root / "figure_7b_valuation_only_summary.csv", index=False)
    figure_7b_valuation(exp3_valuation_summary, figures_root / "figure_7b_valuation_only")

    exp4_grid = pd.read_csv(root / EXP4_GRID)
    exp4_grid.to_csv(data_root / "figure_8_lead_time_grid.csv", index=False)
    figure_8_lead_time(exp4_grid, figures_root / "figure_8_lead_time_target_errors")

    benchmark = exp4_benchmark_table(root)
    benchmark.to_csv(data_root / "table_1_predictive_benchmark.csv", index=False)
    benchmark.to_csv(tables_root / "table_1_predictive_benchmark.csv", index=False)
    _write_table_tex(benchmark, tables_root / "table_1_predictive_benchmark.tex")
    _write_captions(output_root)
    _write_audit(output_root, exp3_summary)
    _write_scope_marker(output_root)

    return {
        "figure_6": figures_root / "figure_6_uncertainty_representation.pdf",
        "figure_7": figures_root / "figure_7_recovery_comparison_coverage.pdf",
        "figure_7b": figures_root / "figure_7b_valuation_only.pdf",
        "figure_8": figures_root / "figure_8_lead_time_target_errors.pdf",
        "table_1": tables_root / "table_1_predictive_benchmark.csv",
        "audit": output_root / "paper_output_audit.md",
    }


def _write_scope_marker(output_root: Path) -> None:
    payload = {
        "scope": "DEVELOPMENT_ONLY",
        "paper_result": False,
        "final_test_access_count": 0,
        "generated_by": "exp.reporting.section5_secondary_analysis",
    }
    (output_root / "OUTPUT_SCOPE_DEVELOPMENT_ONLY.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--bootstrap-replicates", type=int, default=2000)
    args = parser.parse_args(argv)
    paths = run(output_root=args.output_root, bootstrap_replicates=args.bootstrap_replicates)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
