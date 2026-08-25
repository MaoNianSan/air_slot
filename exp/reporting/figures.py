"""Publication-style figure bundles for the output contract.

OUTPUT_CONTRACT_20260823 section 5 style: white background, no top/right
spines, low-saturation accents (#42949E formal/adaptive, #0F4D92), neutral
gray baseline (#8C8C8C), no truncated y-axis, 95% CI error bars, PDF
vector plus 300 dpi PNG output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ACCENT = "#42949E"
ACCENT_DARK = "#0F4D92"
BASELINE_GRAY = "#8C8C8C"
PALETTE = (ACCENT, ACCENT_DARK, BASELINE_GRAY, "#B07AA1", "#D69A3A")


def _style_axis(ax) -> None:
    ax.set_facecolor("white")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)


def _draw_frame(ax, frame: pd.DataFrame, *, ci: Mapping[str, Any] | None) -> None:
    columns = list(frame.columns)
    if len(frame) == 0 or len(columns) < 2:
        return
    x = frame[columns[0]]
    series_key = columns[2] if len(columns) >= 3 else None
    groups = sorted(frame[series_key].dropna().unique()) if series_key is not None else [None]
    for index, name in enumerate(groups):
        subset = frame if name is None else frame[frame[series_key] == name]
        color = PALETTE[index % len(PALETTE)]
        label = str(name) if name is not None else None
        ax.plot(subset[columns[0]], subset[columns[1]], marker="o", color=color, label=label)
        if ci is not None and "ci_lower" in subset and "ci_upper" in subset:
            y = subset[columns[1]]
            ax.errorbar(
                subset[columns[0]], y,
                yerr=[y - subset["ci_lower"], subset["ci_upper"] - y],
                fmt="none", ecolor=color, capsize=2, linewidth=1,
            )
    if any(label is not None for label in groups):
        ax.legend(frameon=False)


def generate_figure_bundle(
    rows, figure_id: str, output: Path, metadata: Mapping[str, Any],
    *, panels: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
    ci: Mapping[str, Any] | None = None,
    layout: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Write CSV sources plus PDF and 300 dpi PNG for one figure.

    With ``panels`` the figure becomes a multi-panel bundle; each panel gets
    its own ``figure_source_{figure_id}_{panel}.csv``.  CI columns
    (ci_lower/ci_upper) are rendered as 95% CI error bars.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    meta = {
        "figure_id": figure_id,
        **dict(metadata),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if panels is None:
        frame = pd.DataFrame(list(rows or ()))
        source = output / f"figure_source_{figure_id}.csv"
        source.write_text(frame.to_csv(index=False), encoding="utf-8")
        meta["source_data"] = source.name
        fig, ax = plt.subplots(figsize=(5, 3))
        _draw_frame(ax, frame, ci=ci)
        _style_axis(ax)
        fig.tight_layout()
    else:
        panel_items = list(panels.items())
        layout = layout or (1, len(panel_items))
        fig, axes = plt.subplots(
            *layout, figsize=(5 * layout[1], 3 * layout[0]), squeeze=False,
        )
        flat = [ax for row in axes for ax in row]
        source_files = []
        questions = {}
        for index, (panel_id, panel_rows) in enumerate(panel_items):
            ax = flat[index]
            frame = pd.DataFrame(list(panel_rows or ()))
            source = output / f"figure_source_{figure_id}_{panel_id}.csv"
            source.write_text(frame.to_csv(index=False), encoding="utf-8")
            source_files.append(source.name)
            _draw_frame(ax, frame, ci=ci)
            _style_axis(ax)
            ax.set_title(str(panel_id), loc="left", fontsize=10)
            panel_meta = dict(metadata.get("panels", {})).get(panel_id, {})
            questions[str(panel_id)] = panel_meta.get("question", "")
        for ax in flat[len(panel_items):]:
            ax.set_visible(False)
        fig.tight_layout()
        meta["source_data"] = source_files
        meta["panel_questions"] = questions
    fig.savefig(output / f"{figure_id}.pdf")
    fig.savefig(output / f"{figure_id}.png", dpi=300)
    plt.close(fig)
    (output / f"{figure_id}.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8",
    )
    return meta


__all__ = ["ACCENT", "ACCENT_DARK", "BASELINE_GRAY", "generate_figure_bundle"]
