# ROUND2_M1_V2_1_BEFORE — M1 Scientific Closure 只读审计（Tranche 2.1）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `d506d60ce7b76ca31f080b5106a6845a552c4f6a`
- WORKTREE_STATUS: clean（本文件为 Tranche 2.1 的第一份产物；审计全程只读，未改任何代码）
- 规格: `AIR_SLOT_ROUND2_M1_V2_1_SCIENTIFIC_CLOSURE`（attachment fcf473d4，849 行）
- 范围: 仅 M1 V2.1 scientific closure 的 5 个 closure 问题；不进入 PRE factual availability freeze、
  M2 七分量、RMB omega、Exp1-4、formal paper run
- FINAL_TEST_ACCESS_COUNT: 0

## 0. 审计对象（真实路径）

`model/M1/loss.py`、`contracts.py`、`network.py`、`pipeline.py`、`scenarios.py`、`data.py`、
`fast_path.py`、`target_builder.py`、`lifecycle.py`、`summaries.py`、`configs/scientific/foundation.yaml`，
以及 V2 消费方 `warning.py`、`service.py`、`cli.py`、`cache.py`、`coverage.py`、`preparation.py`。

## 1. A. Hurdle-quantile upper-tail / CVaR compatibility — CODE_STALE

- `model/M1/loss.py::quantile_value`：`uu = clamp(u, 0, 1)` 后，最后一段的
  `weight = ((uu - lo)/(hi - lo)).clamp(0, 1)`。当 `u > q_max` 时 `weight` 被 clamp 到 1.0，
  返回 `Q(q_max)`。即 principal path **静默截平 positive tail**，把 `Q(0.9)` 当作 `u∈(0,1)` 的完整分布。
- `HurdleQuantileContract` 没有 typed `upper_tail_policy`；`quantile_levels` 只有 `(0.1,…,0.9)`，
  manuscript residual-risk 使用 `CVaR_alpha = 0.90`，`alpha == q_max` 时 90–100% 尾需要显式规则。
- config 没有 `m1_v2_positive_tail_policy`。
- 结论: **CODE_STALE**（需 typed tail policy；UNRESOLVED 时 principal path raise/ABSTAIN；
  仅 smoke fixture 允许 TEST_ONLY 规则；输出 human gate `M1_POSITIVE_TAIL_DECISION_REQUIRED`）。

## 2. B. Static + recurrent representation — MANUSCRIPT_IMPLEMENTATION_GAP（+1 项 SCIENTIFIC_DECISION_REQUIRED）

- `M1V2GRU` heads 只消费 `GRU hidden` + stochastic-parent embeddings（`ib_embedding`/`d_ob_embedding`）。
  没有 `state_repr = concat(recurrent_repr, static_repr, optional_fast_repr)`，没有 static encoder。
- Data2/PRE 逐项核查（`model/M1/data.py` V2 特征组）:
  - `schedule`（`schedule_reference.scheduled_departure_utc` → `schedule.signed_minutes_to_crs_departure`）: **SUPPORTED**（SHARED 组）。
  - `route`、`aircraft identity/context`、`carrier`: 无 M1 canonical encoder path → **SUPPORT_ABSTAIN**。
  - `turnaround reference`、`taxi reference`: 有 Data2 参考对象但只进入 label construction / scenario
    provenance，从未作为 encoder 输入 → encoder 侧 **SUPPORT_ABSTAIN**。
  - 禁止构造: live aircraft availability / gate / crew / slot / standby aircraft。
- manuscript "fast representation" 歧义（A. STATE_AWARE 内部共享 fast-path feature；B. FAST 与
  STATE_AWARE 为独立 alternatives）→ **SCIENTIFIC_DECISION_REQUIRED**（`M1_FAST_FUSION_INTERPRETATION_REQUIRED`）。
- 结论: **MANUSCRIPT_IMPLEMENTATION_GAP**（需 minimal static encoder + fusion，hidden=32 共享维度，
  IMPLEMENTATION_CHOICE 记录；无歧义的 recurrent+static fusion 本轮完成，fast fusion 保持 human gate）。

## 3. C. Marginal distribution summary correctness — CODE_STALE

- `model/M1/pipeline.py::predict_distributions`:
  - A. D_OB zero probability **double sigmoid**：每个 IB bin 先 `sigmoid(zero_logit)`，按 pmf 加权平均后
    返回时再 `torch.sigmoid(...)` 一次。
  - B. D_OB positive quantiles 是 `sum_b w_b Q_b(u)`，被文档/调用方称为 "marginal" 摘要 ——
    条件分位数的加权平均 ≠ marginal quantile（除非特殊条件成立，未证明）。
  - C. D_TX 使用 expected-D_OB-bin 近似整个 parent distribution，且 D_TX zero 是 logit-mixture
    （先按 pmf 混合 logits 再 sigmoid），也不是 P(D_TX=0|h)。
- warning `P(D_TO > 30)` 只从 V2 scenarios 计算（正确）。
- 结论: **CODE_STALE**（单次 logit→prob；`conditional_head_summary` 与 `scenario_marginal_summary`
  显式分离；scenario-derived empirical weighted marginals 作为 principal marginal API）。

## 4. D. T_IB public vs internal semantics — CODE_STALE

- `model/M1/target_builder.py::build_v2_target_labels`：`M1V2TargetLabel.target_name = "T_IB_A00"`，
  但 `exact_minutes` 存的是 **remaining minutes** `max(0, actual_arrival - decision_time)`；
  而 `M1V2Scenario.t_ib_a00_utc` / observed dict 的 `"T_IB_A00"` 是 **ISO UTC 绝对时间**。
  同名字段两种语义，公开 primitive 与 internal hazard coordinate 未分离。
- `HazardBinContract(target_name="T_IB_A00")` 的 bins 也是 remaining-time 参数化 —— 契约名未反映
  internal coordinate。
- 已存在转换: `derived_r_ib_minutes`（R_IB = max(0, T_IB_A00 - t)）；scenario 采样已用
  `decision_time + remaining` 恢复绝对时间。但缺少显式命名与公开/internal 转换契约。
- 结论: **CODE_STALE**（internal label/head 使用 `T_IB_REMAINING_HAZARD`；公开 `T_IB_A00` 保持
  ISO UTC；label 保留 past absolute event time，R_IB=0 时仍可区分不同历史事件时间）。

## 5. E. FAST V2 boundary — MANUSCRIPT_IMPLEMENTATION_GAP

- `model/M1/fast_path.py::LightGBMDistributionalPredictor`：只有 scaffold —— `ABSTAIN` 后 raise
  `M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS` / `M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED`，
  没有任何可训练/可执行的 ARX-LightGBM 模型（无 hazard models、无 zero classifier、
  无 positive quantile regressors）。
- 结论: **MANUSCRIPT_IMPLEMENTATION_GAP**（本 tranche 实现 executable ARX-LightGBM 架构 +
  synthetic/unit training smoke；正式 fitting / freeze / artifact 不执行；无 train-frozen artifact 时
  principal predict 仍 ABSTAIN）。

## 6. 其他受控状态（本 tranche 不改）

- `m1_v2_quantile_levels = [0.1,0.3,0.5,0.7,0.9]`：继续 DEVELOPMENT_ONLY / NOT_FROZEN。
- `HORIZON_SEMANTICS_DECISION_REQUIRED`：不伪造 `tau={0,15,60}`。
- `tau_avail`：保持 unresolved；本轮只保证 sampler/public T_IB 契约为 factual replay 做好准备。
- `FINAL_TEST_ACCESS_COUNT = 0`；`exp/` 不修改；无 commit/push。

## 7. 预期最终状态

`PASS_WITH_SCIENTIFIC_DECISIONS_PENDING`：tail policy（含 quantile levels / q_max / 尾表示规则 /
calibration-freeze procedure）、static/fast fusion interpretation、fast artifact freeze 保持 human gates。
