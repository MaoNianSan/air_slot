"""Development-only journal-style figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .protocol import DISPLAY_NAMES


def priority_figure(base: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(9.0, 3.8), constrained_layout=True)
    axes[0].hexbin(
        base["delay_rank_pct"],
        base["consequence_rank_pct"],
        gridsize=20,
        mincnt=1,
        cmap="viridis",
    )
    axes[0].plot([0, 1], [0, 1], color="black", linewidth=0.8)
    axes[0].set(
        xlabel="Delay-priority percentile", ylabel="Consequence-priority percentile"
    )
    delay_decile = np.minimum((base["delay_rank_pct"] * 10).astype(int), 9)
    consequence_decile = np.minimum((base["consequence_rank_pct"] * 10).astype(int), 9)
    matrix = pd.crosstab(delay_decile, consequence_decile).reindex(
        index=range(10), columns=range(10), fill_value=0
    )
    axes[1].imshow(matrix.to_numpy(), origin="lower", cmap="magma", aspect="auto")
    axes[1].set(xlabel="Consequence-priority decile", ylabel="Delay-priority decile")
    figure.savefig(path)
    plt.close(figure)


def component_figure(
    information: pd.DataFrame, component_gaps: pd.DataFrame, path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(10.0, 4.2), constrained_layout=True)
    info = information.iloc[::-1]
    x_error = np.vstack(
        [
            info["estimate"].to_numpy(dtype=float)
            - info["ci_low"].to_numpy(dtype=float),
            info["ci_high"].to_numpy(dtype=float)
            - info["estimate"].to_numpy(dtype=float),
        ]
    )
    axes[0].errorbar(
        info["estimate"],
        range(len(info)),
        xerr=x_error,
        fmt="o",
        color="#1f6f8b",
        capsize=2,
    )
    axes[0].axvline(0, color="black", linewidth=0.8)
    axes[0].set_yticks(
        range(len(info)),
        [DISPLAY_NAMES.get(item, item) for item in info["quantity_id"]],
    )
    axes[0].set_xlabel("Kendall tau-b")
    gaps = component_gaps.iloc[::-1]
    gap_error = np.vstack(
        [
            gaps["estimate"].to_numpy(dtype=float)
            - gaps["ci_low"].to_numpy(dtype=float),
            gaps["ci_high"].to_numpy(dtype=float)
            - gaps["estimate"].to_numpy(dtype=float),
        ]
    )
    axes[1].errorbar(
        gaps["estimate"],
        range(len(gaps)),
        xerr=gap_error,
        fmt="o",
        color="#b24c3d",
        capsize=2,
    )
    axes[1].set_yticks(
        range(len(gaps)),
        [DISPLAY_NAMES.get(item, item) for item in gaps["component_id"]],
    )
    axes[1].set_xlabel("Median standardized component gap")
    figure.savefig(path)
    plt.close(figure)
