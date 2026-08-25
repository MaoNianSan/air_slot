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
EXP4_METRICS = Path(
    "artifacts/experiments/exp4/full_development_v1/"
    "EXP4_FULL_DEVELOPMENT_METRICS.json"
)

REPRESENTATION_LABELS = {
    "POINT": "Point",
    "MARGINAL": "Marginal",
    "JOINT": "Joint",
}
REPRESENTATION_ORDER = ("POINT", "MARGINAL", "JOINT")
COMPARISON_LABELS = {
    "NUMERICAL": "Numerical comparison",
    "CONDITIONAL": "Conditional comparison",
    "SUPPORT_QUALIFIED": "Support-qualified comparison",
}
COMPARISON_ORDER = ("NUMERICAL", "CONDITIONAL", "SUPPORT_QUALIFIED")
ESTIMATOR_LABELS = {
    "HISTORICAL": "Historical reference",
    "LIGHTGBM": "LightGBM",
    "RANDOM_FOREST": "Random Forest",
    "STATE_AWARE_H32": "History-conditioned estimator",
}
TARGET_ROWS = (
    ("T_IB_REMAINING_HAZARD", "Predecessor availability", "Finite-support CRPS (minutes)"),
    ("D_OB", "Successor off-block delay", "CRPS (minutes)"),
    ("D_TX", "Excess taxi delay", "CRPS (minutes)"),
)

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
    return (
        node_values.groupby(["episode_id", "representation"], as_index=False)["variogram_score"]
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
    columns = (
        "episode_id",
        "decision_node_id",
        "response_sensitivity",
        "response_support",
        "finite_support_scenario_count",
        "diagnostic_support_status",
        "conditional_residual_risk",
    )
    risks = pd.read_parquet(root / EXP3_ACTION_RISK, columns=list(columns))
    base = risks.loc[risks["response_sensitivity"] == "BASE"].copy()
    records: list[dict[str, object]] = []
    for (episode_id, node_id), node in base.groupby(["episode_id", "decision_node_id"], sort=False):
        stored = node["conditional_residual_risk"].notna()
        assessed = bool(stored.any())
        flags = {
            "NUMERICAL": int(stored.sum()) >= 2,
            "CONDITIONAL": int((stored & node["response_support"].eq("SCENARIO_ASSUMPTION")).sum()) >= 2,
            "SUPPORT_QUALIFIED": int(
                (
                    stored
                    & node["diagnostic_support_status"].eq("PARTIAL_DIAGNOSTIC")
                    & node["finite_support_scenario_count"].gt(0)
                ).sum()
            ) >= 2,
        }
        for key in COMPARISON_ORDER:
            records.append(
                {
                    "episode_id": episode_id,
                    "decision_node_id": node_id,
                    "comparison": COMPARISON_LABELS[key],
                    "assessed": assessed,
                    "comparable": flags[key] if assessed else np.nan,
                }
            )
    node_values = pd.DataFrame(records)
    episode_values = (
        node_values.loc[node_values["assessed"]]
        .groupby(["episode_id", "comparison"], as_index=False)["comparable"]
        .mean()
        .rename(columns={"comparable": "coverage"})
    )
    summary_rows: list[dict[str, object]] = []
    unavailable = (
        node_values.loc[~node_values["assessed"]]
        .groupby("comparison")["decision_node_id"]
        .nunique()
        .to_dict()
    )
    assessed_nodes = (
        node_values.loc[node_values["assessed"]]
        .groupby("comparison")["decision_node_id"]
        .nunique()
        .to_dict()
    )
    comparable_nodes = (
        node_values.loc[node_values["assessed"] & node_values["comparable"].astype(bool)]
        .groupby("comparison")["decision_node_id"]
        .nunique()
        .to_dict()
    )
    for comparison in (COMPARISON_LABELS[item] for item in COMPARISON_ORDER):
        values = episode_values.loc[episode_values["comparison"] == comparison, "coverage"]
        estimate = episode_bootstrap(values, replicates=replicates)
        summary_rows.append(
            {
                "comparison": comparison,
                "coverage": estimate.estimate,
                "ci_lower": estimate.ci_lower,
                "ci_upper": estimate.ci_upper,
                "episodes": estimate.n_episodes,
                "comparable_nodes": int(comparable_nodes.get(comparison, 0)),
                "assessed_nodes": int(assessed_nodes.get(comparison, 0)),
                "unavailable_nodes": int(unavailable.get(comparison, 0)),
            }
        )
    return episode_values, pd.DataFrame(summary_rows)


def exp4_benchmark_table(root: Path) -> pd.DataFrame:
    payload = _read_json(root / EXP4_METRICS)
    baselines = payload["data2"]["baselines"]
    rows: list[dict[str, object]] = []
    for target_id, target_label, score_label in TARGET_ROWS:
        for estimator_id, estimator_label in ESTIMATOR_LABELS.items():
            values = baselines[estimator_id].get("target_metrics", {}).get(target_id, {})
            mae = values.get("mae_minutes")
            score = values.get("crps_minutes")
            rows.append(
                {
                    "target": target_label,
                    "estimator": estimator_label,
                    "overall_mae_minutes": mae,
                    "distributional_score": score,
                    "distributional_score_type": score_label if score is not None else "",
                    "mae_95_ci": "",
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
    colors = [PALETTE["neutral"], PALETTE["blue_secondary"], PALETTE["blue_main"]]
    hatches = ["", "//", "\\\\"]
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
    axis.set_xticks(
        positions,
        ["Numerical\ncomparison", "Conditional\ncomparison", "Support-qualified\ncomparison"],
    )
    axis.set_ylabel("Recovery-comparison coverage (%)")
    axis.set_ylim(0, 105)
    axis.text(0.0, 1.02, "A", transform=axis.transAxes, fontweight="bold", fontsize=16)
    figure.tight_layout(pad=1.0)
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
    rendered.columns = [
        "Target",
        "Estimator",
        "Overall MAE (min)",
        "Distributional score",
        "Score definition",
        "MAE 95\\% CI",
    ]
    path.write_text(rendered.to_latex(index=False, escape=False), encoding="utf-8")


def _write_captions(output_root: Path) -> None:
    captions = {
        "figure_6_caption.txt": (
            "Figure 6. Dependence-sensitive predictive score for marginal and joint "
            "representations with finite saved predictive terms. Each decision-node score is first averaged within its aircraft-linked "
            "episode; error bars are 95% episode-cluster bootstrap confidence intervals."
        ),
        "figure_7_caption.txt": (
            "Figure 7. Coverage of recovery comparisons with at least two comparable options. "
            "Coverage is calculated within each aircraft-linked episode and then averaged across "
            "episodes; error bars are 95% episode-cluster bootstrap confidence intervals."
        ),
        "table_1_caption.txt": (
            "Table 1. Predictive benchmark by operational target and estimator. Point estimates are "
            "episode-balanced in the saved result. Episode-level prediction errors were not saved, "
            "so 95% confidence intervals cannot be reconstructed for this table. Blank cells indicate "
            "that a target-specific value was not saved."
        ),
    }
    for name, text in captions.items():
        (output_root / name).write_text(text + "\n", encoding="utf-8")


def _write_audit(output_root: Path, coverage: pd.DataFrame) -> None:
    unavailable_nodes = int(coverage["unavailable_nodes"].max())
    audit = f"""# Paper output audit

## 1. Planned main-text panels with real saved-result support

- Figure 6A is generated for the Marginal and Joint predictive representations using saved scenario-level outputs. The score is aggregated within aircraft-linked episodes and reported with 2,000 episode-cluster bootstrap replicates.
- Figure 7A is generated from saved action-level comparisons. For every displayed definition, the available comparison set contains at least two recovery options. {unavailable_nodes} decision nodes lacked stored comparison results and are not treated as zero coverage.
- Table 1 contains the target-specific point estimates that are present in the saved benchmark output.

## 2. Outputs that are Development inspection only and cannot yet enter final Test results

- Figure 6A, Figure 7A, and Table 1 are based on the saved Development cohort. They are suitable for inspection and manuscript planning, not for final Test-result claims.
- The Exp3 recovery comparisons remain conditional diagnostic comparisons; they do not establish an authoritative recovery ranking.

## 3. Panels not generated because saved outputs are missing or their statistical definition is insufficient

- Figure 5A--C: the Exp1 directory does not contain saved node-level coverage, prediction, or action-comparison values for the requested direct-information and history contrasts.
- Figure 6A Point: the saved point-selection rule has no finite paired predictive terms in the frozen scenario output, so a Point variogram score cannot be formed without inventing a new point rule.
- Figure 6B--C: no saved dependency-disruption series contains consequence distortion and Top-1 disagreement for the required perturbation levels.
- Figure 7B: the available LOW/BASE/HIGH records jointly change response parameters and monetary coefficients, so they cannot be interpreted as a single response-robustness mechanism. No independent relative-valuation perturbation is saved.
- Figure 8A--C: target-specific MAE by operational lead time is not saved. The available lead-time curves are overall values and cannot be relabelled as the three requested targets.
- Table 1 confidence intervals: episode-level prediction errors are not saved. History-conditioned target-specific MAE and distributional scores are also not saved, so those cells remain blank rather than inferred from overall values.
"""
    (output_root / "paper_output_audit.md").write_text(audit, encoding="utf-8")


def run(*, root: Path = ROOT, output_root: Path | None = None, bootstrap_replicates: int = 2000) -> dict[str, Path]:
    """Generate only the paper panels supported by the current saved outputs."""
    root = root.resolve()
    output_root = (output_root or root / DEFAULT_OUTPUT_ROOT).resolve()
    _require_files(
        root,
        (EXP1_SUMMARY, EXP2_SUMMARY, EXP3_SUMMARY, EXP4_SUMMARY, EXP2_SCENARIOS, EXP2_LABELS, EXP3_ACTION_RISK, EXP4_METRICS),
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
    exp2_episode_values.to_csv(data_root / "figure_6a_variogram_episode_values.csv", index=False)
    exp2_summary.to_csv(data_root / "figure_6a_variogram_summary.csv", index=False)
    exp2_contrasts.to_csv(data_root / "figure_6a_paired_contrasts.csv", index=False)
    figure_6_variogram(exp2_summary, figures_root / "figure_6_uncertainty_representation")

    exp3_episode_values, exp3_summary = exp3_comparison_coverage(root, bootstrap_replicates)
    exp3_episode_values.to_csv(data_root / "figure_7a_comparison_coverage_episode_values.csv", index=False)
    exp3_summary.to_csv(data_root / "figure_7a_comparison_coverage_summary.csv", index=False)
    figure_7_coverage(exp3_summary, figures_root / "figure_7_recovery_comparison_coverage")

    benchmark = exp4_benchmark_table(root)
    benchmark.to_csv(data_root / "table_1_predictive_benchmark.csv", index=False)
    benchmark.to_csv(tables_root / "table_1_predictive_benchmark.csv", index=False)
    _write_table_tex(benchmark, tables_root / "table_1_predictive_benchmark.tex")
    _write_captions(output_root)
    _write_audit(output_root, exp3_summary)

    return {
        "figure_6": figures_root / "figure_6_uncertainty_representation.pdf",
        "figure_7": figures_root / "figure_7_recovery_comparison_coverage.pdf",
        "table_1": tables_root / "table_1_predictive_benchmark.csv",
        "audit": output_root / "paper_output_audit.md",
    }


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
