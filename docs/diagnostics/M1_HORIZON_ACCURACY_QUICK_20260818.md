# M1 PREDICTIVE ACCURACY — QUICK DEVELOPMENT DIAGNOSTIC

- 状态: `DEVELOPMENT_ONLY` / `QUICK_DIAGNOSTIC` / `NOT_FINAL_PAPER_RESULT`
- 生成: 2026-08-18（只读，未重跑任何上游）
- COHORT: `M1_SIGNED_DEVELOPMENT_SCENARIOS_V1`（128 episodes / 1824 nodes / 250 scenarios / split=DEVELOPMENT）
- 来源 hash: `sha256:ca3370a30…`；cache `sha256:a34c5b1f4…`
- 冻结温度: {'DELTA_OB': 0.9316896200180054, 'R_IB': 0.8575054407119751, 'T_TX': 1.1812664270401}

## 0. 硬约束遵守情况

| 约束 | 值 |
|---|---|
| PRE_REBUILT | FALSE |
| M1_RETRAINED | FALSE |
| H_W_RERUN | FALSE |
| EXP1_RERUN | FALSE |
| CALIBRATION_REFIT | FALSE |
| SCENARIO_REGENERATED | FALSE |
| FINAL_TEST_ACCESS_COUNT | 0 |
| PAPER_FULL_RUN | FALSE |

## 1. 定义与方法

- **Horizon** = 从 decision time 到实际被评价 target/event 的预测提前时间。
  - R_IB: realized predecessor in-block 剩余时间（分钟）；即 realized R_IB 本身。
  - DELTA_OB: (scheduled successor off-block − decision time) + realized DELTA_OB。
  - T_TX / D_TO: (scheduled off-block − decision time) + realized DELTA_OB + realized T_TX（到 takeoff）。
- **匹配规则**: nearest allowed horizon in {30,...,480}; realized leads live on the canonical 5-min grid as integer + k*5 + 2.5 minutes so ties are impossible。
- **真实值**: frozen cache labels M1_SIGNED_OB_DEVELOPMENT_BASE_CACHE_V1 (5-min bin representatives, verified by the frozen scenario artifact with 0 mismatches vs pinned BTS exacts)。
- **预测** = 每节点 250 个 frozen aligned scenario draws 的中位数（已含冻结温度校准）。
- **NLL**: 250 draws 在 realized bin 上的经验频率取 −log（0 频 bin 按 1e-6 截断）。
- **CRPS**: 250 draws 经验 CDF 能量公式。
- 已排除: DELTA_OB 在事件已发生节点（53）不计；T_TX/D_TO 在 POST_OB_PRE_TO（53）不计 horizon。
- 历史窗口 W=30 是 history window，与 prediction horizon 无关（未混淆）。

## 2. 主表（每个 target 单独一张）

### R_IB（单位：minutes）

| Horizon | N | N_ep | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 183 | 43 | 20.4 | 20.0 | 24.3 | 20% | 32% | 44% | 79% |
| 60 | 72 | 13 | 26.1 | 25.0 | 29.9 | 10% | 19% | 32% | 64% |
| 120 | 14 | 2 | 72.5 | 72.5 | 73.1 | 0% | 0% | 0% | 0% |
| **ALL** | 269 | 43 | 24.6 | 22.5 | 30.3 | 16% | 27% | 38% | 71% |

**DISTRIBUTIONAL QUALITY（仅填写 artifact 支持项）**

| Horizon | NLL | CRPS | Cov50 | Cov80 | Cov90 | W50 | W80 | W90 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 2.861 | 19.4 | 54% | 91% | 98% | 74 | 154 | 198 |
| 60 | 4.065 | 18.3 | 76% | 100% | 100% | 66 | 134 | 173 |
| 120 | 4.033 | 41.8 | 0% | 71% | 100% | 60 | 109 | 134 |

- 支持: total 1824 nodes；active（事件未发生、可评估）269；abstain（事件在 decision time 已发生）1555。realized horizon 落在 [30,480] 内的 active 节点 132 个。

### DELTA_OB（单位：minutes）

| Horizon | N | N_ep | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 890 | 118 | 3.4 | 0.0 | 5.9 | 90% | 95% | 98% | 100% |
| 60 | 424 | 94 | 8.7 | 5.0 | 16.4 | 73% | 77% | 81% | 93% |
| 120 | 208 | 22 | 30.7 | 5.0 | 50.0 | 59% | 59% | 59% | 66% |
| 180 | 123 | 14 | 35.3 | 5.0 | 62.1 | 59% | 59% | 59% | 69% |
| 240 | 63 | 6 | 23.9 | 0.0 | 60.1 | 76% | 76% | 76% | 89% |
| 300 | 36 | 4 | 0.0 | 0.0 | 0.0 | 100% | 100% | 100% | 100% |
| 360 | 17 | 2 | 0.0 | 0.0 | 0.0 | 100% | 100% | 100% | 100% |
| 420 | 10 | 1 | 0.0 | 0.0 | 0.0 | 100% | 100% | 100% | 100% |
| **ALL** | 1771 | 128 | 10.7 | 0.0 | 27.8 | 80% | 84% | 86% | 92% |

**DISTRIBUTIONAL QUALITY（仅填写 artifact 支持项）**

| Horizon | NLL | CRPS | Cov50 | Cov80 | Cov90 | W50 | W80 | W90 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 1.492 | 8.2 | 93% | 97% | 100% | 34 | 126 | 191 |
| 60 | 2.719 | 11.2 | 78% | 86% | 95% | 26 | 119 | 185 |
| 120 | 4.981 | 28.9 | 59% | 62% | 65% | 12 | 63 | 122 |
| 180 | 5.593 | 31.8 | 59% | 59% | 72% | 13 | 64 | 133 |
| 240 | 3.458 | 20.1 | 76% | 78% | 89% | 13 | 71 | 167 |
| 300 | 0.398 | 1.5 | 100% | 100% | 100% | 1 | 25 | 146 |
| 360 | 0.367 | 1.3 | 100% | 100% | 100% | 2 | 22 | 126 |
| 420 | 0.306 | 1.1 | 100% | 100% | 100% | 1 | 26 | 94 |

- 支持: total 1824 nodes；active（事件未发生、可评估）1771；abstain（事件在 decision time 已发生）53。realized horizon 落在 [30,480] 内的 active 节点 1204 个。

### T_TX（单位：minutes）

| Horizon | N | N_ep | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 563 | 111 | 5.0 | 5.0 | 6.7 | 75% | 92% | 99% | 100% |
| 60 | 646 | 115 | 6.0 | 5.0 | 9.0 | 71% | 87% | 95% | 99% |
| 120 | 257 | 40 | 7.7 | 5.0 | 10.9 | 60% | 79% | 93% | 98% |
| 180 | 148 | 16 | 8.7 | 5.0 | 11.9 | 55% | 66% | 86% | 100% |
| 240 | 82 | 10 | 8.4 | 10.0 | 10.5 | 48% | 77% | 91% | 100% |
| 300 | 41 | 5 | 8.7 | 10.0 | 10.1 | 41% | 71% | 100% | 100% |
| 360 | 18 | 2 | 13.2 | 15.0 | 13.5 | 0% | 33% | 100% | 100% |
| 420 | 12 | 1 | 15.0 | 15.0 | 15.0 | 0% | 0% | 100% | 100% |
| 480 | 4 | 1 | 13.8 | 15.0 | 13.9 | 0% | 25% | 100% | 100% |
| **ALL** | 1771 | 128 | 6.5 | 5.0 | 9.2 | 66% | 84% | 96% | 99% |

**DISTRIBUTIONAL QUALITY（仅填写 artifact 支持项）**

| Horizon | NLL | CRPS | Cov50 | Cov80 | Cov90 | W50 | W80 | W90 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 1.689 | 4.1 | 80% | 96% | 99% | 13 | 33 | 47 |
| 60 | 1.868 | 4.6 | 76% | 95% | 99% | 12 | 32 | 46 |
| 120 | 2.178 | 5.4 | 55% | 95% | 97% | 10 | 28 | 42 |
| 180 | 3.074 | 6.4 | 47% | 79% | 92% | 8 | 25 | 40 |
| 240 | 2.248 | 5.6 | 61% | 93% | 99% | 11 | 29 | 44 |
| 300 | 1.846 | 4.8 | 41% | 100% | 100% | 10 | 25 | 44 |
| 360 | 2.489 | 7.2 | 0% | 100% | 100% | 10 | 26 | 45 |
| 420 | 2.849 | 8.6 | 0% | 100% | 100% | 5 | 20 | 29 |
| 480 | 2.879 | 8.3 | 0% | 100% | 100% | 6 | 22 | 33 |

- 支持: total 1824 nodes；active（事件未发生、可评估）1824；abstain（事件在 decision time 已发生）0。realized horizon 落在 [30,480] 内的 active 节点 1591 个。

### D_TO（derived，冻结恒等式 max(0, DELTA_OB + T_TX − taxi_ref)）

| Horizon | N | MAE | MedianAE | RMSE | ±5m | ±10m | ±15m | ±30m |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 563 | 6.3 | 5.0 | 8.2 | 60% | 84% | 94% | 100% |
| 60 | 646 | 9.2 | 5.0 | 13.7 | 54% | 74% | 83% | 94% |
| 120 | 257 | 23.5 | 9.0 | 37.2 | 35% | 56% | 63% | 70% |
| 180 | 148 | 43.9 | 14.0 | 65.6 | 30% | 47% | 55% | 55% |
| 240 | 82 | 49.9 | 10.0 | 84.0 | 23% | 52% | 61% | 61% |
| 300 | 41 | 8.1 | 9.0 | 9.5 | 39% | 98% | 98% | 98% |
| 360 | 18 | 10.1 | 10.0 | 10.2 | 0% | 89% | 100% | 100% |
| 420 | 12 | 13.0 | 13.0 | 13.0 | 0% | 0% | 100% | 100% |
| 480 | 4 | 11.9 | 12.2 | 11.9 | 0% | 25% | 100% | 100% |
| **ALL** | 1771 | 15.1 | 6.2 | 31.3 | 48% | 71% | 81% | 88% |

- 说明: realized D_TO built from 5-min binned labels (+-2.5 min quantization); taxi reference frozen。

## 3. Exp1 Lead Time Quantiles（从 frozen parquet 只读计算）

- 定义: sustained-warning positive episodes: minutes from the first sustained warning node (two consecutive 5-min nodes with min(warning_probability) >= threshold) to realized WheelsOff

| Variant | Median | Q25 | Q75 | IQR | N_leads | 与 frozen evidence 交叉验证 |
|---|---:|---:|---:|---:|---:|---|
| CURRENT | 105 min | 80 min | 142 min | 62 min | 4686 | PASS (median/IQR/denominator 与 frozen evidence 完全一致) |
| FIXED_HISTORY | 108 min | 83 min | 145 min | 62 min | 5772 | PASS (median/IQR/recall/denominator 全部与 frozen evidence 完全一致) |
| ADAPTIVE_HISTORY | 108 min | 84 min | 145 min | 61 min | 4325 | PARTIAL (IQR/denominator 与 frozen 一致; 本会话计算 median=108 vs frozen=109, sustained-warning episode 集少约 800, Q25/Q75 为近似值 ±1 min) |

- 交叉验证: FIXED/CURRENT 完全一致; ADAPTIVE IQR 一致、median 差 1 min（近似）。

## 4. 关键解读

### 4.1 60 min ahead

- T_TX: MAE 6.0 min；±10m 87%；±15m 95%；±30m 99%。
- DELTA_OB: MAE 8.7 min；±10m 77%；±15m 81%；±30m 93%。
- R_IB: MAE 26.1 min（N=72）；±10m 19%；±15m 32%；±30m 64%。

### 4.2 120 min ahead

- T_TX: MAE 7.7 min；±10m 79%；±15m 93%；±30m 98%。
- DELTA_OB: MAE 30.7 min；±10m 59%；±15m 59%；±30m 66%。
- R_IB: MAE 72.5 min（N=14）；±10m 0%；±15m 0%；±30m 0%。

### 4.3 30 → 60 → 120 → 180 → 240 的下降趋势

- T_TX（±15m）: 30→60→120→180→240 = 99% → 95% → 93% → 86% → 91%。
- DELTA_OB（±15m）: 30→60→120→180→240 = 98% → 81% → 59% → 59% → 76%。
- R_IB（±15m）: 30→60→120→180→240 = 44% → 32% → 0% → N/A → N/A。

### 4.4 是否表现出 farther horizon → larger uncertainty / error

- T_TX: 是（±10m 从 92% → 66%，Cov50 从 80% → 47%）。
- DELTA_OB: 大体是（30→180 min 明显变差；≥240 min 样本少、多为 on-time 已实现小延迟，MAE 回落是样本组成效应，不是恢复精度）。
- R_IB: 60 min 之后急剧变差（H=120 的 14 个节点 ±30m = 0%），表现为对长提前量系统性低估，但 N 很小（active 仅 269 节点）。

### 4.5 Exp1 ~5% warning recall 的归因（基于本诊断实际数据）

- 事件: D_TO > 30（strict）。frozen 场景 cohort 中 positive 节点 233 个（15 episodes）。
- positive 节点中 P̂(D_TO>30) 中位数 = 0.116，达到 frozen FIXED 阈值 0.384 的仅 1.3%；≥0.5 为 0%。
- negative 节点中 P̂ 中位数 = 0.144（与 positive 几乎同分布）。

**结论: C — 两者都有，且以模型侧为主。**
模型对 D_TO>30 事件几乎不输出高置信度（positive 节点上 P̂ 中位数 0.12，0% 超过 0.5），在 0.384 的 episode-level FPR=0.1 操作点上，绝大多数 positive 节点永远达不到阈值；即 predictive signal 弱（A）导致任何合理的 FPR 操作点都只能给出很低 recall（B 是 A 的后果）。这不代表 T_TX/DELTA_OB 点预测不准——它们的中短期点精度尚可——而是稀有事件概率估计缺乏分离度。

## 5. 局限与声明

- QUICK_DIAGNOSTIC_COHORT: 128 episodes / 1824 nodes（Development 2019-08~09），非全量。
- 真实值为 5-min bin 代表值（±2.5 min 量化误差），tolerance 指标对 5-min 网格上的|误差|≤δ 判定。
- 未触碰 final test（FINAL_TEST_ACCESS_COUNT=0）；未重跑任何上游步骤。
