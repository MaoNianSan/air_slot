from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

CHANNELS = ("F", "P", "R")
STAGES = ("t1", "t2", "t3")


def save_figure(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix, kwargs in ((".png", {"dpi": 300}), (".pdf", {}), (".svg", {})):
        fig.savefig(path.with_suffix(suffix), bbox_inches="tight", **kwargs)
    plt.close(fig)
