from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
from downstream_common import (
    FORMAL_TARGET_COLUMN,
    FORMAL_TARGET_CONTRACT_VERSION,
    ParallelPlan,
    SENSITIVITY_TARGET_COLUMN,
    load_common_passenger_cohort,
    parallel_metadata,
    resolve_parallel_plan,
    run_ordered_thread_tasks,
    sha256_file,
    stable_hash,
    task_seed_hash,
    thread_limit_environment,
)

MODELS = ["HIST", "QRF", "NGB", "PROP", "POINT_OOF"]
M2_CONFIGS = [
    "DAG_BASE", "ADD_BASE", "SCOPE_LOW", "SCOPE_HIGH", "SEQUENCE_LOW",
    "SEQUENCE_HIGH", "PASSENGER_LOW", "PASSENGER_HIGH", "AIRPORT_HEAVY",
    "SEQUENCE_HEAVY", "PASSENGER_HEAVY",
]


def validate_m1_target_mapping(mapping: dict[str, str]) -> None:
    if set(mapping) != set(MODELS):
        raise ValueError("PART_ADV_M1_TARGET_MAPPING_INCOMPLETE")
    wrong = {model: target for model, target in mapping.items() if target != FORMAL_TARGET_COLUMN}
    if wrong:
        raise ValueError("PART_ADV_M1_TARGET_MISMATCH:" + ",".join(sorted(wrong)))


def _atomic_joblib(value: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(value, temporary)
    os.replace(temporary, path)


class _RunTelemetry:
    def __init__(
        self,
        cfg: dict[str, Any],
        progress: str,
        log: Path,
        input_hash: str,
        implementation_hash: str,
        formal_target_definition_hash: str,
    ) -> None:
        self.cfg = cfg
        self.progress = progress
        self.log = log
        self.input_hash = input_hash
        self.implementation_hash = implementation_hash
        self.formal_target_definition_hash = formal_target_definition_hash
        self.started = time.monotonic()
        self.stage = "initializing"
        self.model = "NONE"
        self.rows_processed = 0
        self.last_checkpoint: str | None = None
        self.records_path = cfg["output"] / "model_progress.json"
        self.records: list[dict[str, Any]] = []
        if self.records_path.exists():
            loaded = json.loads(self.records_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                self.records = loaded
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def context(self, stage: str, model: str, rows: int = 0) -> None:
        self.stage = stage
        self.model = model
        self.rows_processed = int(rows)

    def _memory_mb(self) -> float:
        try:
            import psutil

            return float(psutil.Process().memory_info().rss / (1024 * 1024))
        except (ImportError, OSError):
            return float("nan")

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(300.0):
            payload = {
                "module": "part_adv",
                "mode": self.cfg["mode"],
                "stage": self.stage,
                "model": self.model,
                "elapsed": float(time.monotonic() - self.started),
                "last_checkpoint": self.last_checkpoint,
                "rows_processed": self.rows_processed,
                "memory_mb": self._memory_mb(),
            "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "requested_n_jobs": self.cfg.get("requested_n_jobs", 1),
                "resolved_n_jobs": self.cfg.get("resolved_n_jobs", 1),
                "outer_workers": self.cfg.get("outer_workers", 1),
                "inner_model_threads": self.cfg.get("inner_model_threads", 1),
                "running_task_ids": [self.model] if self.model != "NONE" else [],
                "completed_task_count": len([row for row in self.records if row.get("status") == "PASS"]),
                "pending_task_count": max(0, len(MODELS) - len([row for row in self.records if row.get("status") == "PASS"])),
            }
            _log("HEARTBEAT " + json.dumps(payload, default=str), self.progress, self.log)

    def _signature(self, model_id: str) -> dict[str, Any]:
        return {
            "input_hash": self.input_hash,
            "config_hash": self.cfg["config_hash"],
            "implementation_hash": self.implementation_hash,
            "mode": self.cfg["mode"],
            "stage": "m1",
            "model_id": model_id,
            "formal_target_column": FORMAL_TARGET_COLUMN,
            "formal_target_contract_version": FORMAL_TARGET_CONTRACT_VERSION,
            "formal_target_definition_hash": self.formal_target_definition_hash,
        }

    def _record(self, record: dict[str, Any]) -> None:
        self.records = [row for row in self.records if row.get("model_id") != record["model_id"]]
        self.records.append(record)
        self.records.sort(key=lambda row: MODELS.index(row["model_id"]))
        _write_json(self.records, self.records_path)

    def model_step(
        self,
        index: int,
        model_id: str,
        input_rows: int,
        compute: Callable[[], Any],
    ) -> Any:
        checkpoint = self.cfg["output"] / "checkpoints" / "m1" / f"{model_id.lower()}.joblib"
        metadata_path = checkpoint.with_suffix(".json")
        signature = self._signature(model_id)
        started_at = pd.Timestamp.now(tz="UTC")
        started_clock = time.monotonic()
        self.context("m1", model_id, input_rows)
        _log(f"[1/4][{index}/5] {model_id}", self.progress, self.log)
        record = {
            "model_id": model_id,
            "start_time": started_at,
            "end_time": None,
            "elapsed_seconds": None,
            "input_rows": int(input_rows),
            "output_path": str(checkpoint),
            "status": "RUNNING",
            "checkpoint_path": str(checkpoint),
            "resume_reused": False,
        }
        self._record(record)
        try:
            if checkpoint.exists() or metadata_path.exists():
                if not checkpoint.exists() or not metadata_path.exists():
                    raise ValueError(f"CHECKPOINT_INCOMPLETE:{model_id}")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                for key, expected in signature.items():
                    if metadata.get(key) != expected:
                        raise ValueError(f"CHECKPOINT_HASH_MISMATCH:{model_id}:{key}")
                if metadata.get("output_hash") != sha256_file(checkpoint):
                    raise ValueError(f"CHECKPOINT_OUTPUT_HASH_MISMATCH:{model_id}")
                value = joblib.load(checkpoint)
                reused = True
            else:
                value = compute()
                _atomic_joblib(value, checkpoint)
                metadata = {
                    **signature,
                    "output_hash": sha256_file(checkpoint),
                    "completed_at": pd.Timestamp.now(tz="UTC"),
                    "requested_n_jobs": self.cfg.get("requested_n_jobs", 1),
                    "resolved_n_jobs": self.cfg.get("resolved_n_jobs", 1),
                    "outer_workers": self.cfg.get("outer_workers", 1),
                    "inner_model_threads": self.cfg.get("inner_model_threads", 1),
                    "parallel_backend": self.cfg.get("parallel_backend", "native"),
                    "task_partition_version": self.cfg.get("task_partition_version"),
                    "task_seed_hash": self.cfg.get("task_seed_hash"),
                }
                _write_json(metadata, metadata_path)
                reused = False
            ended_at = pd.Timestamp.now(tz="UTC")
            self.last_checkpoint = str(checkpoint)
            record.update(
                {
                    "end_time": ended_at,
                    "elapsed_seconds": float(time.monotonic() - started_clock),
                    "status": "PASS",
                    "resume_reused": reused,
                }
            )
            self._record(record)
            _log(
                f"[1/4][{index}/5] {model_id} complete elapsed={record['elapsed_seconds']:.1f}s "
                f"resume_reused={str(reused).lower()} checkpoint={checkpoint}",
                self.progress,
                self.log,
            )
            return value
        except Exception:
            record.update(
                {
                    "end_time": pd.Timestamp.now(tz="UTC"),
                    "elapsed_seconds": float(time.monotonic() - started_clock),
                    "status": "INCOMPLETE",
                }
            )
            self._record(record)
            raise


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


def _part_adv_figures(
    output: Path,
    m1_metrics: pd.DataFrame,
    downstream: pd.DataFrame,
    m2_results: pd.DataFrame,
    m4_metrics: pd.DataFrame,
) -> None:
    figures = output / "figures"
    figures.mkdir(exist_ok=True)

    # Figure 1: predictive quality and propagated decision quality remain separate.
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
    model_order = [model for model in MODELS if model in set(m1_metrics["model_id"])]
    indexed = m1_metrics.set_index("model_id").reindex(model_order)
    x = np.arange(len(model_order))
    axes[0].bar(x - 0.18, indexed["crps"], 0.36, label="CRPS")
    axes[0].bar(x + 0.18, indexed["twcrps"], 0.36, label="Tail-weighted CRPS")
    # 重绘 POINT_OOF 为 hollow with hatch
    if "POINT_OOF" in model_order:
        po_idx = model_order.index("POINT_OOF")
        for offset, col in [(-0.18, "crps"), (0.18, "twcrps")]:
            axes[0].bar(x[po_idx] + offset, [indexed.loc["POINT_OOF", col]], 0.36,
                        color="none", edgecolor=["C0", "C1"][{"crps": 0, "twcrps": 1}[col]],
                        hatch="///", linewidth=1.5)
    axes[0].set_yscale("log")
    axes[0].text(0.02, 0.98, "Log scale", transform=axes[0].transAxes,
                 ha="left", va="top", fontsize=9, alpha=0.7)
    axes[0].set_xticks(x, model_order, rotation=30, ha="right")
    axes[0].set_ylabel("Predictive score")
    axes[0].set_title("A. Distributional prediction")
    axes[0].legend(frameon=False)

    formal = downstream[downstream.get("formal_ranking", True).astype(bool)].copy() if "formal_ranking" in downstream else downstream.copy()
    decision = formal.groupby("model_id", observed=True)["regret"].agg(["mean", lambda values: float(values[values >= values.quantile(.9)].mean())])
    decision.columns = ["mean_regret", "_worst_decile_regret"]
    decision = decision[["mean_regret"]]
    decision = decision.reindex([model for model in model_order if model in decision.index])
    y = np.arange(len(decision))
    axes[1].bar(y, decision["mean_regret"], 0.5, label="Mean controlled-benchmark regret")
    axes[1].set_yscale("log")
    axes[1].text(0.02, 0.98, "Log scale", transform=axes[1].transAxes,
                 ha="left", va="top", fontsize=9, alpha=0.7)
    # 在每个模型旁标注 action disagreement vs PROP
    prop_actions = downstream.loc[downstream["model_id"].eq("PROP"), "action_id"]
    for model in decision.index:
        if model == "PROP":
            axes[1].text(y[decision.index.get_loc(model)] + 0.3,
                         decision.loc[model, "mean_regret"],
                         "Reference", va="center", fontsize=8)
        else:
            model_actions = downstream.loc[downstream["model_id"].eq(model), "action_id"]
            if len(prop_actions) and len(model_actions):
                disagree = (model_actions.to_numpy() != prop_actions.to_numpy()).mean()
                axes[1].text(y[decision.index.get_loc(model)] + 0.3,
                             decision.loc[model, "mean_regret"],
                             f"Disagreement vs PROP: {disagree*100:.1f}%",
                             va="center", fontsize=7)
    axes[1].set_xticks(y, decision.index, rotation=30, ha="right")
    axes[1].set_ylabel("Controlled-benchmark regret (RMB)")
    axes[1].set_title("B. Downstream decision quality")
    axes[1].legend(frameon=False)
    figure.tight_layout()
    _save_publication_figure(figure, figures / "fig01_m1_predictive_and_downstream")

    # Figure 2: M2 structure and one-factor sensitivities.
    base_actions = m2_results[m2_results["configuration"].eq("DAG_BASE")][["recovery_case_id", "action_id"]].rename(columns={"action_id": "base_action"})
    m2_plot = m2_results.merge(base_actions, on="recovery_case_id", how="left")
    m2_summary = m2_plot.groupby("configuration", observed=True).agg(
        mean_post_cost=("post_cost", "mean"),
        recommendation_agreement=("action_id", lambda values: 0.0),
    ).reset_index()
    agreements = (
        m2_plot.assign(agreement=m2_plot["action_id"].eq(m2_plot["base_action"]))
        .groupby("configuration", observed=True)["agreement"]
        .mean()
    )
    m2_summary["recommendation_agreement"] = m2_summary["configuration"].map(agreements)
    base_cost = float(m2_summary.loc[m2_summary["configuration"].eq("DAG_BASE"), "mean_post_cost"].iloc[0])
    m2_summary["post_cost_difference"] = m2_summary["mean_post_cost"] - base_cost
    order = m2_summary.sort_values("post_cost_difference")["configuration"].tolist()
    ordered = m2_summary.set_index("configuration").reindex(order)
    figure, axes = plt.subplots(1, 2, figsize=(12.2, 5.0), sharey=True)
    axes[0].axvline(0.0, linestyle="--")
    axes[0].barh(ordered.index, ordered["post_cost_difference"])
    axes[0].set_xlabel("Mean post-action constructed-cost difference vs DAG_BASE (RMB)")
    axes[0].set_title("A. Cost sensitivity")
    ordered["recommendation_disagreement"] = 100 * (1 - ordered["recommendation_agreement"])
    axes[1].barh(ordered.index, ordered["recommendation_disagreement"])
    axes[1].set_xlabel("Recommendation disagreement with DAG_BASE (%)")
    axes[1].axvline(0, linestyle="--", color="gray", linewidth=0.8)
    axes[1].set_title("B. Ranking stability")
    figure.tight_layout()
    _save_publication_figure(figure, figures / "fig02_m2_structure_and_sensitivity")

    # Figure 3: M4 risk-functional trade-off — two panels.
    figure, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(12.2, 4.8))

    # --- Left: Mean benchmark regret ---
    variant_order = ["EV", "Mean-CVaR", "CVaR"]
    m4_plot = m4_metrics.set_index("variant").reindex(variant_order)
    x = np.arange(len(variant_order))
    colors = ["C0", "C1", "C2"]
    ax_left.bar(x, m4_plot["mean_benchmark_regret"], color=colors)
    ax_left.set_xticks(x, variant_order)
    ax_left.set_ylabel("Mean controlled-benchmark regret (RMB)")
    ax_left.set_title("A. Mean benchmark regret")

    # Mean-CVaR 的零值旁标注
    if "Mean-CVaR" in variant_order:
        mc_idx = variant_order.index("Mean-CVaR")
        mc_val = float(m4_plot.loc["Mean-CVaR", "mean_benchmark_regret"])
        y_offset = abs(mc_val) * 0.05 if mc_val != 0 else 0.01
        ax_left.text(mc_idx, mc_val + y_offset,
                     "0 by objective consistency", ha="center", va="bottom",
                     fontsize=8, fontstyle="italic")

    # --- Right: Non-A00 selection rate ---
    ax_right.bar(x, 100 * m4_plot["non_a00_rate"].to_numpy(float), color=colors)
    ax_right.set_xticks(x, variant_order)
    ax_right.set_ylabel("Non-A00 selection rate (%)")
    ax_right.set_ylim(0, max(20, 100 * m4_plot["non_a00_rate"].max() * 1.3))
    ax_right.set_title("B. Non-A00 selection rate")

    # 标注实际百分比
    for i, var in enumerate(variant_order):
        rate = 100 * float(m4_plot.loc[var, "non_a00_rate"])
        ax_right.text(i, rate + 1, f"{rate:.2f}%", ha="center", va="bottom", fontsize=8)

    figure.tight_layout()
    _save_publication_figure(figure, figures / "fig03_m4_risk_tradeoff")


def _log(message: str, level: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{pd.Timestamp.now(tz='UTC').isoformat()} {message}\n")
    if level != "quiet":
        print(message, flush=True)


