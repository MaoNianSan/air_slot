"""Create auditable Development-only Exp1 tables, figure, and interpretation."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PALETTE = {
    "baseline": "#B64342",
    "current": "#42949E",
    "history": "#0F4D92",
}


def _hash_file(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_exp1_report(root: str | Path = ".", output_root: str | Path | None = None) -> dict[str, str]:
    root = Path(root).resolve()
    source = root / "artifacts/experiment/exp1_full_development/EXP1_FULL_DEVELOPMENT_VARIANT_COMPARISON.json"
    manifest = root / "artifacts/experiment/exp1_full_development/EXP1_FULL_DEVELOPMENT_EXECUTION_MANIFEST.json"
    comparison = json.loads(source.read_text(encoding="utf-8"))
    output = Path(output_root).resolve() if output_root else root / "artifacts/experiment/exp1_full_development/paper_ready_development"
    output.mkdir(parents=True, exist_ok=True)

    order = ("NO_HISTORY", "CURRENT_STATE_ONLY", "HISTORY_CONDITIONED_GRU_H32")
    labels = {
        "NO_HISTORY": "No history",
        "CURRENT_STATE_ONLY": "Current state only",
        "HISTORY_CONDITIONED_GRU_H32": "History-conditioned GRU H32",
    }
    rows = []
    for variant in order:
        m = comparison["variants"][variant]
        rows.append({
            "variant": labels[variant],
            "variant_id": variant,
            "n_nodes": m["node_count"],
            "MAE_minutes": m["mae_minutes"],
            "CRPS_minutes": m["crps_minutes"],
            "Brier": m["brier"],
            "Calibration_gap": m["calibration_absolute_gap"],
            "Coverage": m["coverage"],
        })

    csv_path = output / "EXP1_DEVELOPMENT_TABLE.csv"
    csv_path.write_text(
        "variant,variant_id,n_nodes,MAE_minutes,CRPS_minutes,Brier,Calibration_gap,Coverage\n"
        + "".join(
            f"{r['variant']},{r['variant_id']},{r['n_nodes']},{r['MAE_minutes']:.8f},{r['CRPS_minutes']:.8f},{r['Brier']:.8f},{r['Calibration_gap']:.8f},{r['Coverage']:.8f}\n"
            for r in rows
        ),
        encoding="utf-8",
    )
    tex_path = output / "EXP1_DEVELOPMENT_TABLE.tex"
    tex_lines = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Variant & MAE (min) & CRPS (min) & Brier & Cal. gap & Coverage \\",
        r"\midrule",
    ]
    for r in rows:
        tex_lines.append(
            f"{r['variant']} & {r['MAE_minutes']:.3f} & {r['CRPS_minutes']:.3f} & {r['Brier']:.3f} & {r['Calibration_gap']:.3f} & {r['Coverage']:.3f} \\\\" 
        )
    tex_lines.extend([r"\bottomrule", r"\end{tabular}", ""])
    tex_path.write_text("\n".join(tex_lines), encoding="utf-8")

    hist = comparison["variants"]["HISTORY_CONDITIONED_GRU_H32"]
    current = comparison["variants"]["CURRENT_STATE_ONLY"]
    delta = {
        "CRPS_minutes_reduction_history_vs_current": current["crps_minutes"] - hist["crps_minutes"],
        "MAE_minutes_change_history_vs_current": hist["mae_minutes"] - current["mae_minutes"],
        "Brier_reduction_history_vs_current": current["brier"] - hist["brier"],
        "Calibration_gap_reduction_history_vs_current": current["calibration_absolute_gap"] - hist["calibration_absolute_gap"],
        "Coverage_change_history_vs_current": hist["coverage"] - current["coverage"],
    }

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.4), constrained_layout=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    x = list(range(len(rows)))
    colors = [PALETTE["baseline"], PALETTE["current"], PALETTE["history"]]
    axes[0].plot(x, [r["MAE_minutes"] for r in rows], marker="o", linewidth=2.2, color=PALETTE["current"], label="MAE")
    axes[0].plot(x, [r["CRPS_minutes"] for r in rows], marker="s", linewidth=2.2, color=PALETTE["history"], label="CRPS")
    axes[0].set_ylabel("Minutes")
    axes[0].set_title("State error")
    axes[1].bar([i - 0.18 for i in x], [r["Brier"] for r in rows], width=0.36, color=colors, alpha=0.9, label="Brier")
    axes[1].bar([i + 0.18 for i in x], [r["Calibration_gap"] for r in rows], width=0.36, color="#AADCA9", alpha=0.95, label="Calibration gap")
    axes[1].set_ylabel("Score")
    axes[1].set_title("Probabilistic reliability")
    for ax in axes:
        ax.set_xticks(x, ["No\nhistory", "Current\nonly", "History\nGRU H32"])
        ax.grid(axis="y", alpha=0.25)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(frameon=False, fontsize=8)
    fig_path = output / "EXP1_DEVELOPMENT_STATE_COMPARISON"
    fig.savefig(fig_path.with_suffix(".png"), dpi=300)
    fig.savefig(fig_path.with_suffix(".pdf"))
    plt.close(fig)

    interpretation = (
        "# Exp1 Development-only interpretation\n\n"
        "在同一 Data2 Development cohort（1769 nodes）和冻结 M1_V2_GRU_H32 条件下，"
        "history-conditioned state 的 CRPS 和 Brier 略低于 current-state-only，"
        "calibration gap 也略有改善；MAE 基本持平但略高。该结果支持“历史条件化会改变状态表示”"
        "这一工程/Development 观察，但不构成 Final Test 或 paper-full 证据。\n\n"
        f"相对 current-state-only：CRPS 改善 {delta['CRPS_minutes_reduction_history_vs_current']:.4f} min，"
        f"Brier 改善 {delta['Brier_reduction_history_vs_current']:.4f}，"
        f"calibration gap 改善 {delta['Calibration_gap_reduction_history_vs_current']:.4f}；"
        f"MAE 变化 {delta['MAE_minutes_change_history_vs_current']:.4f} min。\n\n"
        "解释边界：这些是 Development-only predictive/state metrics；未生成 M2/M3/M4 downstream decision evidence，"
        "不能解释为动作因果效果、真实货币损失或最终恢复策略最优性。"
    )
    interpretation_path = output / "EXP1_DEVELOPMENT_INTERPRETATION.md"
    interpretation_path.write_text(interpretation, encoding="utf-8")

    bundle = {
        "schema_version": "EXP1_DEVELOPMENT_REPORT_BUNDLE_V1",
        "status": "DEVELOPMENT_ONLY_PAPER_READY_PREPARATION",
        "paper_result": False,
        "source": {"comparison": str(source), "manifest": str(manifest), "comparison_sha256": _hash_file(source), "manifest_sha256": _hash_file(manifest)},
        "outputs": {"table_csv": str(csv_path), "table_tex": str(tex_path), "figure_png": str(fig_path.with_suffix('.png')), "figure_pdf": str(fig_path.with_suffix('.pdf')), "interpretation": str(interpretation_path)},
        "delta_history_vs_current": delta,
        "safety": {"FINAL_TEST_ACCESS_COUNT": 0, "PAPER_FULL_RUN": False, "AUTHORITATIVE_RANKING": False},
        "claim_scope": "Development-only evidence for history-conditioned state representation; no downstream decision claim",
    }
    bundle_path = output / "EXP1_DEVELOPMENT_REPORT_BUNDLE.json"
    _write_json(bundle_path, bundle)
    return {"bundle": str(bundle_path), "table": str(csv_path), "figure": str(fig_path.with_suffix('.pdf')), "interpretation": str(interpretation_path)}


if __name__ == "__main__":
    print(json.dumps(build_exp1_report(), ensure_ascii=True, indent=2))
