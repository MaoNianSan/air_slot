from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil

try:
    import pyarrow.parquet as pq
except ModuleNotFoundError:
    pq = None
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from downstream_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    ParallelPlan,
    load_common_passenger_cohort,
    parallel_metadata,
    resolve_parallel_plan,
    run_ordered_thread_tasks,
    sha256_file,
    stable_hash,
    task_seed_hash,
    thread_limit_environment,
)

CHECKPOINT_SCHEMA_VERSION = "overall-adv-checkpoint-v1"
HEARTBEAT_SECONDS = 300


def _seed(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16) % (2**32 - 1)


def _write_df(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    os.replace(temporary, path)


def _write_json(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


def _save_publication_figure(figure: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    figure.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    figure.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def _overall_adv_figure(
    metrics: pd.DataFrame,
    paired: pd.DataFrame,
    summary: pd.DataFrame,
    bootstrap: pd.DataFrame,
    path: Path,
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(11.5, 8.0))

    # --- A. Overall paired difference with cluster-bootstrap CI ---
    delta = pd.to_numeric(paired.get("local_minus_global_regret"), errors="coerce").dropna()
    point = float(delta.mean()) if len(delta) else np.nan
    boot = pd.to_numeric(bootstrap.get("local_minus_global_regret"), errors="coerce").dropna()
    lower = float(boot.quantile(0.025)) if len(boot) else np.nan
    upper = float(boot.quantile(0.975)) if len(boot) else np.nan
    axes[0, 0].axvline(0.0, linestyle="--", color="gray")
    if np.isfinite(point):
        xerr = None if not np.isfinite(lower + upper) else [[point - lower], [upper - point]]
        axes[0, 0].errorbar(point, [0], xerr=xerr, fmt="o", capsize=4, color="C0")
    axes[0, 0].set_yticks([0], ["Local \u2212 Global"])
    axes[0, 0].set_xlabel("Local \u2212 Global controlled-benchmark regret (RMB)")
    axes[0, 0].set_title("A. Mean difference with 95% cluster-bootstrap CI")

    # --- B. Only policy-disagreement cases ---
    wide = metrics.pivot_table(index="recovery_case_id", columns="policy_id", values="regret", observed=True)
    if {"LOCAL_F", "GLOBAL_FPR"}.issubset(wide.columns):
        wide.columns.name = None
        wide = wide.reset_index()
        # 筛选分歧 case
        disagreement = wide["LOCAL_F"].ne(wide["GLOBAL_FPR"])
        if disagreement.any():
            plot_df = wide.loc[disagreement].copy()
            axes[0, 1].scatter(plot_df["LOCAL_F"], plot_df["GLOBAL_FPR"], alpha=0.6, s=15)
            bound = float(np.nanmax(plot_df[["LOCAL_F", "GLOBAL_FPR"]].to_numpy(float)))
            axes[0, 1].plot([0, bound], [0, bound], linestyle="--", color="gray")
            axes[0, 1].set_title(f"B. Policy-disagreement cases (n={disagreement.sum()})")
        else:
            axes[0, 1].text(0.5, 0.5, "No disagreement cases", ha="center", va="center",
                            transform=axes[0, 1].transAxes)
            axes[0, 1].set_title("B. Policy-disagreement cases (n=0)")
    axes[0, 1].set_xlabel("Local benchmark loss (RMB)")
    axes[0, 1].set_ylabel("Global benchmark loss (RMB)")

    # --- C. All supported vs disagreement-only ---
    local_minus_global = paired["local_minus_global_regret"].dropna()
    disc_regret = None
    if {"LOCAL_F", "GLOBAL_FPR"}.issubset(wide.columns) and disagreement.any():
        disc = wide.loc[disagreement]
        disc_regret = (disc["LOCAL_F"] - disc["GLOBAL_FPR"]).mean()
    all_mean = float(local_minus_global.mean()) if len(local_minus_global) else 0.0
    bars = {"All supported cases": all_mean}
    if disc_regret is not None:
        bars["Policy-disagreement\ncases only"] = disc_regret
    bar_labels = list(bars.keys())
    bar_values = list(bars.values())
    colors_bar = ["C0", "C1"] if len(bar_values) > 1 else ["C0"]
    axes[1, 0].bar(bar_labels, bar_values, color=colors_bar)
    axes[1, 0].axhline(0, linestyle="--", color="gray")
    axes[1, 0].set_ylabel("Mean Local \u2212 Global controlled-benchmark regret (RMB)")
    axes[1, 0].set_title("C. Overall vs conditional effect")

    # --- D. Decision outcome composition: Tie / Global lower / Local lower ---
    if {"LOCAL_F", "GLOBAL_FPR"}.issubset(wide.columns):
        tie = ((wide["LOCAL_F"] == wide["GLOBAL_FPR"]) | (wide["LOCAL_F"].isna() & wide["GLOBAL_FPR"].isna())).sum()
        global_lower = (wide["GLOBAL_FPR"] < wide["LOCAL_F"]).sum()
        local_lower = (wide["LOCAL_F"] < wide["GLOBAL_FPR"]).sum()
        total = tie + global_lower + local_lower
        if total > 0:
            axes[1, 1].bar(["Tie", "Global lower loss", "Local lower loss"],
                           [tie / total, global_lower / total, local_lower / total],
                           color=["gray", "C1", "C0"])
    axes[1, 1].set_ylim(0, 1)
    axes[1, 1].set_ylabel("Proportion of supported cases")
    axes[1, 1].set_title("D. Decision outcome composition")

    figure.tight_layout()
    _save_publication_figure(figure, path)


def _log(message: str, level: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{pd.Timestamp.now(tz='UTC').isoformat()} {message}\n")
    if level != "quiet":
        print(message, flush=True)


class _Heartbeat:
    def __init__(self, mode: str, progress: str, log: Path, plan: ParallelPlan) -> None:
        self.mode = mode
        self.progress = progress
        self.log = log
        self.plan = plan
        self.started = time.monotonic()
        self.last_emitted = self.started
        self.last_checkpoint: str | None = None

    def tick(self, stage: str, model: str, rows_processed: int, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_emitted < HEARTBEAT_SECONDS:
            return
        memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        payload = {
            "module": "overall_adv",
            "mode": self.mode,
            "stage": stage,
            "model": model,
            "elapsed": round(now - self.started, 1),
            "last_checkpoint": self.last_checkpoint,
            "rows_processed": int(rows_processed),
            "memory_mb": round(memory_mb, 1),
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "requested_n_jobs": self.plan.requested_n_jobs,
            "resolved_n_jobs": self.plan.resolved_n_jobs,
            "outer_workers": self.plan.outer_workers,
            "inner_model_threads": self.plan.inner_model_threads,
            "running_task_ids": [],
            "completed_task_count": int(rows_processed),
            "pending_task_count": 0,
        }
        _log("HEARTBEAT " + json.dumps(payload, sort_keys=True), self.progress, self.log)
        self.last_emitted = now

    def checkpointed(self, path: Path) -> None:
        self.last_checkpoint = str(path)


