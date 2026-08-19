"""Exp1 lead-time quantiles (Q25/Q75/IQR) from frozen Exp1 outputs — READ-ONLY.

Replicates the frozen episode-level operating-point logic
(exp/exp1/metrics.py: episode_operating_point / summarize_operating_point)
directly on the frozen FIXED_HISTORY / CURRENT / ADAPTIVE_HISTORY parquet
outputs of AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE (principal_s250).

No Exp1 inference rerun. Cross-validated against the frozen evidence.json
median/IQR. Then merges into the quick-diagnostic JSON and writes the final
markdown report.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "artifacts" / "diagnostics" / "v5_development_freeze"
PRINCIPAL = FREEZE / "exp1_development_warning" / "principal_s250"
EVIDENCE = json.loads((PRINCIPAL / "evidence.json").read_text(encoding="utf-8"))
JSON_PATH = ROOT / "artifacts" / "diagnostics" / "M1_HORIZON_ACCURACY_QUICK_20260818.json"
MD_PATH = ROOT / "docs" / "diagnostics" / "M1_HORIZON_ACCURACY_QUICK_20260818.md"

VARIANTS = {
    "CURRENT": {"dir": "CURRENT", "threshold": 0.364},
    "FIXED_HISTORY": {"dir": "FIXED_HISTORY", "threshold": 0.384},
    "ADAPTIVE_HISTORY": {"dir": "ADAPTIVE_HISTORY", "threshold": 0.392},
}
THRESHOLD_KEY = "0.1"  # frozen operating point at target FPR 0.1


def read_variant_month(variant_dir: str, month: str) -> pd.DataFrame:
    import pyarrow.dataset as ds
    base = PRINCIPAL / f"month={month}" / variant_dir
    schema = ds.dataset(base, format="parquet").schema
    keep = [c for c in schema.names if c in {
        "episode_id", "decision_time", "lead_time_minutes", "warning_probability",
        "warning_support_state", "realized_event_positive",
    }]
    table = ds.dataset(base, format="parquet").to_table(columns=keep)
    return table.to_pandas()


def episode_lead_quantiles(frame: pd.DataFrame, threshold: float) -> dict:
    """Frozen episode_operating_point semantics, fully vectorized.

    Rows are episode-contiguous and already in node order
    (decision_time ascending == lead_time descending), verified against the
    frozen evidence.json below.
    """
    f = frame.copy()
    f["sup"] = (f["warning_support_state"] == "SUPPORTED") & np.isfinite(
        f["warning_probability"].to_numpy(dtype=np.float64))
    grp_ep = f.groupby("episode_id", sort=False)
    prev_lead = f["lead_time_minutes"].shift(1)
    prev_prob = f["warning_probability"].shift(1)
    prev_sup = f["sup"].shift(1)
    boundary = f["episode_id"] != f["episode_id"].shift(1)
    prev_lead[boundary] = np.nan
    prev_prob[boundary] = np.nan
    prev_sup[boundary] = False

    gap_ok = (prev_lead - f["lead_time_minutes"] - 5.0).abs() <= 1e-9
    pair_ok = gap_ok & f["sup"] & prev_sup
    score = np.where(pair_ok.to_numpy(), np.minimum(prev_prob.to_numpy(),
                    f["warning_probability"].to_numpy(dtype=np.float64)), -1.0)
    score = np.nan_to_num(score, nan=-1.0)
    f["score"] = score
    f["pair_ok"] = pair_ok

    score_grp = f.groupby("episode_id", sort=False)["score"]
    ep_max = score_grp.transform("max")
    run_max = score_grp.cummax()
    prev_best = run_max.shift(1).fillna(-1.0)
    first_max = (score >= 0) & (score == ep_max.to_numpy()) & (score > prev_best.to_numpy())
    sustained_lead = pd.Series(np.where(first_max, prev_lead.to_numpy(dtype=np.float64), np.nan),
                               index=f.index)

    any_warning = (f["sup"] & (f["warning_probability"] >= threshold)).groupby(
        f["episode_id"], sort=False).transform("any")
    sustained = (f["pair_ok"] & (f["score"] >= threshold)).groupby(
        f["episode_id"], sort=False).transform("any")
    evaluable = f["pair_ok"].groupby(f["episode_id"], sort=False).transform("any")
    lead_ep = sustained_lead.groupby(f["episode_id"], sort=False).transform("first")
    realized_ep = f["realized_event_positive"].groupby(
        f["episode_id"], sort=False).transform("first")

    keep = boundary.to_numpy()
    pos = (realized_ep & evaluable & sustained)[keep].to_numpy()
    leads = lead_ep[keep].to_numpy(dtype=np.float64)
    leads = leads[pos]
    leads = leads[np.isfinite(leads)]
    ordered = np.sort(leads)
    if len(ordered):
        q1 = float(ordered[int((len(ordered) - 1) * 0.25)])
        q3 = float(ordered[int((len(ordered) - 1) * 0.75)])
        return {
            "threshold": threshold,
            "N_leads": int(len(ordered)),
            "median_min": float(np.median(ordered)),
            "q25_min": q1,
            "q75_min": q3,
            "iqr_min": float(q3 - q1),
            "positive_evaluable": int(((realized_ep & evaluable)[keep]).sum()),
            "sustained_warning_count": int((pos).sum()),
            "episode_recall": float(((realized_ep & evaluable & any_warning)[keep].sum()
                                     / (realized_ep & evaluable)[keep].sum())),
            "sustained_warning_recall": float((pos.sum() / (realized_ep & evaluable)[keep].sum())),
        }
    return {"threshold": threshold, "N_leads": 0}


def main() -> None:
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    results = {}
    print("reading Exp1 frozen parts (principal_s250, 3 variants x 2 months) ...")
    for name, spec in VARIANTS.items():
        frames = []
        for month in ("08", "09"):
            df = read_variant_month(spec["dir"], month)
            frames.append(df)
        frame = pd.concat(frames, ignore_index=True)
        # frozen _ordered_rows sorts each episode by lead_time_minutes descending;
        # some variants' files are not pre-sorted, so sort explicitly (stable).
        frame = frame.sort_values(
            ["episode_id", "lead_time_minutes"], ascending=[True, False],
            kind="stable", ignore_index=True)
        assert frame["warning_support_state"].notna().all()
        res = episode_lead_quantiles(frame, threshold=spec["threshold"])
        res["variant"] = name
        frozen = EVIDENCE["metrics"][name]
        res["frozen_median_crosscheck"] = frozen["median_risk_lead_minutes"]
        res["frozen_iqr_crosscheck"] = frozen["iqr_risk_lead_minutes"]
        res["frozen_positive_denominator"] = frozen["positive_denominator"]
        assert abs(res["median_min"] - frozen["median_risk_lead_minutes"]) < 1e-9, (name, res, frozen)
        assert abs(res["iqr_min"] - frozen["iqr_risk_lead_minutes"]) < 1e-9, (name, res, frozen)
        assert res["positive_evaluable"] == frozen["positive_denominator"], (name, res, frozen)
        results[name] = res
        print(name, res)
        del frames, frame
    payload["exp1_lead_time_quantiles"] = {
        "source": "AIR_SLOT_EXP1_DEVELOPMENT_WARNING_FREEZE principal_s250 (frozen parquet, read-only)",
        "operating_point": "target episode FPR 0.1",
        "lead_definition": (
            "sustained-warning positive episodes: minutes from the first sustained warning node "
            "(two consecutive 5-min nodes with min(warning_probability) >= threshold) to realized WheelsOff"
        ),
        "quantile_rule": "nearest-rank, identical to frozen exp/exp1/metrics.py",
        "variants": results,
        "crosscheck_against_frozen_evidence": "PASS (median/IQR/denominators identical)",
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("MERGED", JSON_PATH)

    write_markdown(payload)
    print("WROTE", MD_PATH)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def fmt(v, nd=1):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def target_tables(payload, name, horizons):
    item = payload["targets"][name]
    rows = {r["horizon_minutes"]: r for r in item["horizons"]}
    lines = [
        f"### {name}（单位：minutes）",
        "",
        f"| Horizon | N | N_ep | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for h in horizons:
        r = rows.get(h)
        if r is None:
            continue
        lines.append(
            f"| {h} | {r['N']} | {r['N_episodes']} | {r['MAE_min']:.1f} | {r['MedianAE_min']:.1f} | "
            f"{r['RMSE_min']:.1f} | {r['acc_within_5_min']*100:.0f}% | {r['acc_within_10_min']*100:.0f}% | "
            f"{r['acc_within_15_min']*100:.0f}% | {r['acc_within_30_min']*100:.0f}% |"
        )
    overall = item["overall"]
    lines.append(
        f"| **ALL** | {overall['N']} | {overall['N_episodes']} | {overall['MAE_min']:.1f} | "
        f"{overall['MedianAE_min']:.1f} | {overall['RMSE_min']:.1f} | "
        f"{overall['acc_within_5_min']*100:.0f}% | {overall['acc_within_10_min']*100:.0f}% | "
        f"{overall['acc_within_15_min']*100:.0f}% | {overall['acc_within_30_min']*100:.0f}% |"
    )
    lines += ["", "**DISTRIBUTIONAL QUALITY（仅填写 artifact 支持项）**", "",
              "| Horizon | NLL | CRPS | Cov50 | Cov80 | Cov90 | W50 | W80 | W90 |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for h in horizons:
        r = rows.get(h)
        if r is None:
            continue
        lines.append(
            f"| {h} | {r['NLL']:.3f} | {r['CRPS_min']:.1f} | {r['cov50']*100:.0f}% | "
            f"{r['cov80']*100:.0f}% | {r['cov90']*100:.0f}% | {r['width50_min']:.0f} | "
            f"{r['width80_min']:.0f} | {r['width90_min']:.0f} |"
        )
    return lines


def write_markdown(payload: dict) -> None:
    horizons = (30, 60, 120, 180, 240, 300, 360, 420, 480)
    lead = payload["exp1_lead_time_quantiles"]
    we = payload["warning_event_evidence"]
    lines = [
        "# M1 PREDICTIVE ACCURACY — QUICK DEVELOPMENT DIAGNOSTIC",
        "",
        "- 状态: `DEVELOPMENT_ONLY` / `QUICK_DIAGNOSTIC` / `NOT_FINAL_PAPER_RESULT`",
        "- 生成: 2026-08-18（只读，未重跑任何上游）",
        f"- COHORT: `{payload['cohort']['QUICK_DIAGNOSTIC_COHORT']}`（128 episodes / 1824 nodes / 250 scenarios / split=DEVELOPMENT）",
        f"- 来源 hash: `{payload['cohort']['artifact_hash'][:16]}…`；cache `{payload['cohort']['cache_hash'][:16]}…`",
        f"- 冻结温度: {payload['cohort']['temperatures']}",
        "",
        "## 0. 硬约束遵守情况",
        "",
        "| 约束 | 值 |",
        "|---|---|",
        f"| PRE_REBUILT | {fmt(payload['flags']['PRE_REBUILT'])} |",
        f"| M1_RETRAINED | {fmt(payload['flags']['M1_RETRAINED'])} |",
        f"| H_W_RERUN | {fmt(payload['flags']['H_W_RERUN'])} |",
        f"| EXP1_RERUN | {fmt(payload['flags']['EXP1_RERUN'])} |",
        f"| CALIBRATION_REFIT | {fmt(payload['flags']['CALIBRATION_REFIT'])} |",
        f"| SCENARIO_REGENERATED | {fmt(payload['flags']['SCENARIO_REGENERATED'])} |",
        f"| FINAL_TEST_ACCESS_COUNT | {payload['flags']['FINAL_TEST_ACCESS_COUNT']} |",
        f"| PAPER_FULL_RUN | {fmt(payload['flags']['PAPER_FULL_RUN'])} |",
        "",
        "## 1. 定义与方法",
        "",
        "- **Horizon** = 从 decision time 到实际被评价 target/event 的预测提前时间。",
        f"  - R_IB: realized predecessor in-block 剩余时间（分钟）；即 realized R_IB 本身。",
        f"  - DELTA_OB: (scheduled successor off-block − decision time) + realized DELTA_OB。",
        f"  - T_TX / D_TO: (scheduled off-block − decision time) + realized DELTA_OB + realized T_TX（到 takeoff）。",
        f"- **匹配规则**: {payload['horizon_matching_rule']}。",
        f"- **真实值**: {payload['realized_label_source']}。",
        "- **预测** = 每节点 250 个 frozen aligned scenario draws 的中位数（已含冻结温度校准）。",
        "- **NLL**: 250 draws 在 realized bin 上的经验频率取 −log（0 频 bin 按 1e-6 截断）。",
        "- **CRPS**: 250 draws 经验 CDF 能量公式。",
        "- 已排除: DELTA_OB 在事件已发生节点（53）不计；T_TX/D_TO 在 POST_OB_PRE_TO（53）不计 horizon。",
        "- 历史窗口 W=30 是 history window，与 prediction horizon 无关（未混淆）。",
        "",
        "## 2. 主表（每个 target 单独一张）",
        "",
    ]
    for name in ("R_IB", "DELTA_OB", "T_TX"):
        lines += target_tables(payload, name, horizons)
        support = payload["targets"][name]["support"]
        lines += [
            "",
            f"- 支持: total 1824 nodes；active（事件未发生、可评估）{support['active_nodes']}；"
            f"abstain（事件在 decision time 已发生）{support['abstain_nodes']}。"
            f"realized horizon 落在 [30,480] 内的 active 节点 {support['nodes_with_realized_horizon_in_30_480']} 个。",
            "",
        ]
    dto = payload["targets"]["D_TO"]
    rows = {r["horizon_minutes"]: r for r in dto["horizons"]}
    lines += ["### D_TO（derived，冻结恒等式 max(0, DELTA_OB + T_TX − taxi_ref)）", "",
              "| Horizon | N | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for h in horizons:
        r = rows.get(h)
        if r is None:
            continue
        lines.append(
            f"| {h} | {r['N']} | {r['MAE_min']:.1f} | {r['MedianAE_min']:.1f} | {r['RMSE_min']:.1f} | "
            f"{r['acc_within_5_min']*100:.0f}% | {r['acc_within_10_min']*100:.0f}% | "
            f"{r['acc_within_15_min']*100:.0f}% | {r['acc_within_30_min']*100:.0f}% |"
        )
    o = dto["overall"]
    lines.append(
        f"| **ALL** | {o['N']} | {o['MAE_min']:.1f} | {o['MedianAE_min']:.1f} | {o['RMSE_min']:.1f} | "
        f"{o['acc_within_5_min']*100:.0f}% | {o['acc_within_10_min']*100:.0f}% | "
        f"{o['acc_within_15_min']*100:.0f}% | {o['acc_within_30_min']*100:.0f}% |"
    )
    lines += [f"\n- 说明: {dto['caveats']}。", ""]

    lines += ["## 3. Exp1 Lead Time Quantiles（从 frozen parquet 只读计算）", "",
              f"- 定义: {lead['lead_definition']}", "",
              "| Variant | Median | Q25 | Q75 | IQR | N_leads | 与 frozen evidence 交叉验证 |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for name in ("CURRENT", "FIXED_HISTORY", "ADAPTIVE_HISTORY"):
        v = lead["variants"][name]
        lines.append(
            f"| {name} | {v['median_min']:.0f} min | {v['q25_min']:.0f} min | {v['q75_min']:.0f} min | "
            f"{v['iqr_min']:.0f} min | {v['N_leads']} | {v.get('crosscheck_status','PASS')} |"
        )
    lines += ["", f"- 交叉验证: {lead['crosscheck_against_frozen_evidence']}。", ""]

    pos = we["positive_nodes_realized_DTO_gt_30"]
    neg = we["negative_nodes_realized_DTO_le_30"]
    lines += ["## 4. 关键解读", "", "### 4.1 60 min ahead", ""]
    lines += [
        f"- T_TX: MAE {payload['targets']['T_TX']['horizons'][1]['MAE_min']:.1f} min；"
        f"±10m {payload['targets']['T_TX']['horizons'][1]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['T_TX']['horizons'][1]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['T_TX']['horizons'][1]['acc_within_30_min']*100:.0f}%。",
        f"- DELTA_OB: MAE {payload['targets']['DELTA_OB']['horizons'][1]['MAE_min']:.1f} min；"
        f"±10m {payload['targets']['DELTA_OB']['horizons'][1]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['DELTA_OB']['horizons'][1]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['DELTA_OB']['horizons'][1]['acc_within_30_min']*100:.0f}%。",
        f"- R_IB: MAE {payload['targets']['R_IB']['horizons'][1]['MAE_min']:.1f} min（N={payload['targets']['R_IB']['horizons'][1]['N']}）；"
        f"±10m {payload['targets']['R_IB']['horizons'][1]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['R_IB']['horizons'][1]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['R_IB']['horizons'][1]['acc_within_30_min']*100:.0f}%。",
        "", "### 4.2 120 min ahead", "",
        f"- T_TX: MAE {payload['targets']['T_TX']['horizons'][2]['MAE_min']:.1f} min；"
        f"±10m {payload['targets']['T_TX']['horizons'][2]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['T_TX']['horizons'][2]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['T_TX']['horizons'][2]['acc_within_30_min']*100:.0f}%。",
        f"- DELTA_OB: MAE {payload['targets']['DELTA_OB']['horizons'][2]['MAE_min']:.1f} min；"
        f"±10m {payload['targets']['DELTA_OB']['horizons'][2]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['DELTA_OB']['horizons'][2]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['DELTA_OB']['horizons'][2]['acc_within_30_min']*100:.0f}%。",
        f"- R_IB: MAE {payload['targets']['R_IB']['horizons'][2]['MAE_min']:.1f} min（N={payload['targets']['R_IB']['horizons'][2]['N']}）；"
        f"±10m {payload['targets']['R_IB']['horizons'][2]['acc_within_10_min']*100:.0f}%；"
        f"±15m {payload['targets']['R_IB']['horizons'][2]['acc_within_15_min']*100:.0f}%；"
        f"±30m {payload['targets']['R_IB']['horizons'][2]['acc_within_30_min']*100:.0f}%。",
        "", "### 4.3 30 → 60 → 120 → 180 → 240 的下降趋势", "",
    ]
    for name, col in (("T_TX", "T_TX"), ("DELTA_OB", "DELTA_OB"), ("R_IB", "R_IB")):
        acc = []
        for h in (30, 60, 120, 180, 240):
            r = next((x for x in payload["targets"][name]["horizons"] if x["horizon_minutes"] == h), None)
            acc.append("N/A" if r is None else f"{r['acc_within_15_min']*100:.0f}%")
        lines.append(f"- {name}（±15m）: 30→60→120→180→240 = {' → '.join(acc)}。")
    lines += [
        "",
        "### 4.4 是否表现出 farther horizon → larger uncertainty / error",
        "",
        "- T_TX: 是（±10m 从 92% → 66%，Cov50 从 80% → 47%）。",
        "- DELTA_OB: 大体是（30→180 min 明显变差；≥240 min 样本少、多为 on-time 已实现小延迟，"
        "MAE 回落是样本组成效应，不是恢复精度）。",
        "- R_IB: 60 min 之后急剧变差（H=120 的 14 个节点 ±30m = 0%），表现为对长提前量系统性低估，"
        "但 N 很小（active 仅 269 节点）。",
        "",
        "### 4.5 Exp1 ~5% warning recall 的归因（基于本诊断实际数据）",
        "",
        f"- 事件: D_TO > 30（strict）。frozen 场景 cohort 中 positive 节点 {pos['N_nodes']} 个"
        f"（{pos['N_episodes']} episodes）。",
        f"- positive 节点中 P̂(D_TO>30) 中位数 = {pos['median_p_hat_DTO_gt30']:.3f}，"
        f"达到 frozen FIXED 阈值 0.384 的仅 {pos['share_ge_0.384']*100:.1f}%；≥0.5 为 {pos['share_ge_0.5']*100:.0f}%。",
        f"- negative 节点中 P̂ 中位数 = {neg['median_p_hat_DTO_gt30']:.3f}（与 positive 几乎同分布）。",
        "",
        "**结论: C — 两者都有，且以模型侧为主。**",
        "模型对 D_TO>30 事件几乎不输出高置信度（positive 节点上 P̂ 中位数 0.12，"
        "0% 超过 0.5），在 0.384 的 episode-level FPR=0.1 操作点上，绝大多数 positive 节点"
        "永远达不到阈值；即 predictive signal 弱（A）导致任何合理的 FPR 操作点都只能给出"
        "很低 recall（B 是 A 的后果）。这不代表 T_TX/DELTA_OB 点预测不准——它们的中短期"
        "点精度尚可——而是稀有事件概率估计缺乏分离度。",
        "",
        "## 5. 局限与声明",
        "",
        "- QUICK_DIAGNOSTIC_COHORT: 128 episodes / 1824 nodes（Development 2019-08~09），非全量。",
        "- 真实值为 5-min bin 代表值（±2.5 min 量化误差），tolerance 指标对 5-min 网格上的"
        "|误差|≤δ 判定。",
        "- 未触碰 final test（FINAL_TEST_ACCESS_COUNT=0）；未重跑任何上游步骤。",
        "",
    ]
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
