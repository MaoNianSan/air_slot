# Development Evidence Closure — Audit & Execution Plan (2026-08-25)

Scope: 论文所需展示逻辑已基本确定（Figure 5–8 + 主表），但底层结果尚未全部以
“论文可统计”粒度保存。本文档把当前缺口按可执行性分型，并给出 Exp1 的
Development closure 具体执行路径。**不进入 Final Test；不跑 paper_full；不发明指标。**

## 0. 当前仓库状态（已核实，HEAD `fd0bab7`）

| 输入 | 路径 | 状态 |
| --- | --- | --- |
| M1 V2 场景（history 模型 GRU_H32，250 draws/node） | `artifacts/experiments/exp1/full_development_scenarios_v1/M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet` | 442,250 rows / 1,769 nodes |
| 标签（post-outcome，3 targets × 1,769） | `artifacts/experiment/full_development_inputs_v1/M1_V2_FULL_DEVELOPMENT_LABELS.json` | 5,307 rows |
| PRE 推理输入 + pre states（128 episodes） | `artifacts/experiment/full_development_inputs_v1/M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json` | 1,769 nodes |
| M2 后果（7 components + 3 channels，250/node） | `artifacts/experiments/exp2/full_development_v1/M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet` | 442,250 rows |
| M1 checkpoint（fast-mode） | `artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt` | `sha256:e3401c76…`，2 epochs / 128 examples |
| NO_HISTORY checkpoint（fast-mode） | `artifacts/experiment/m1_v2_tuning_stage1_fast/NO_HISTORY/M1_V2_FAST_TRAIN_MODE.pt` | H16，7,620 params，`EXECUTED_FAST_NOT_SELECTED` |
| 现有 paper 层输出 | `outputs/manuscript_values/section5_secondary_analysis/` | Figure 6A / 7A / Table 1 + `paper_output_audit.md` |

关键事实（与本 audit 结论一致）：

1. **Exp1 的 scientific metrics 全部 NOT_RUN**：`artifacts/experiment/exp1_full_development/exp1_summary.json` 中
   CRPS/STATE/TOP1/EXPOST 均为 `NOT_RUN`，主表只有工程覆盖事实。
2. **M1 V2 唯一 checkpoint 是 FAST_TRAIN_MODE**（2 epochs，`EXECUTED_FAST_NOT_SELECTED`，
   `HUMAN_SELECTION_REQUIRED`）。`M1_V2_MODEL_SELECTION_REPORT.json` 状态为
   `M1_V2_FINAL_DEVELOPMENT_FREEZE_READY`（preparation only）。Development closure 可用它出图，
   但任何 Test/paper 口径都需要先在冻结 protocol 下完整训练。
3. **NO_HISTORY 基线是 fast、H16**：`history_mode=NO_HISTORY_CURRENT_OBSERVATION`，
   `selection_role=BASELINE_DIAGNOSTIC_ONLY`。与 GRU_H32 相比 capacity 不同 → **不是公平的
   Exp1B CURRENT 对照**。公平对照（同 protocol、同 capacity、无 history encoder）需要新训练。
4. **M2 后果形成只消费 S_t + identity + train-frozen reference**（见
   `exp/workflows/m2_v2_current_stage_consequence_materialization.py::_m2_input`）：
   raw weather / hidden history 等 E_t 字段不进入 M2。**因此 Exp1A REDUCED 的后果重形成
   必须重新聚合而非复制 FULL 行；若数值不变，这是结果（consequence 由 S_t 决定），不是捷径。**
5. **M3 action eligibility 只消费 template `required_facts`**（`model/M3/instantiate.py`）：
   REDUCED 下把 facts 过滤到结构性必需集后，n_instantiated_actions 可独立重算。
6. **M4 production mapping 未冻结**：`registries/m4_v2_monetary_mapping_design.json`
   `production_mapping_enabled=false`；`EXP2_EXECUTION_READINESS` 状态
   `BLOCKED_UNSUPPORTED_MAPPING`。comparison/ranking/top1 在 principal lane 保持 NOT_RUN。
7. **Episode-level errors 未保存**：Exp4 只有 overall MAE / horizon MAE（T_IB 单 target），
   没有 per-node 记录 → 95% CI 无法重建；Figure 8 的三个 target 曲线不存在。
8. **Exp2 Point variogram 缺 finite paired terms**：已保存实现为所有 variant 复用 JOINT draws；
   `section5_secondary_analysis.exp2_variogram_episode_values` 已改为 per-representation 重算，
   但 Point 在保存的 frozen scenario 上没有有限配对项（POINT 规则需重新定义/重算）。
9. **Exp3 LOW/BASE/HIGH 同时改 response 参数和 monetary 系数** → 无法单独解释
   response robustness；valuation-only 扰动未保存。
10. **Exp2 q=0~1 dependency-disruption series 未保存**（Figure 6B–C 需要）。

## 1. 用户 audit 的分型映射（A/B/C）

| audit 类型 | 内容 | 本仓库状态 | 动作 |
| --- | --- | --- | --- |
| A 已有真实结果，继续加工 | Fig 6A Joint/Marginal；Fig 7A coverage；Exp4 target-specific point | READY（`section5_secondary_analysis` 已生成 6A/7A/Table1） | 保留，仅重标 DEVELOPMENT_ONLY |
| B 不需重训，需重新 materialize | Fig 6A Point；Fig 6B–C；Fig 7B；Fig 8；Exp4 episode CI；target-specific outputs；Exp1A records；Exp1B history-side records | 部分原料存在（见 §0） | 本次实现 Exp1A/Exp1B records（§3–4） |
| C 真正需要重跑实验 | Exp1B CURRENT（M^cur 公平训练）；M3/M4 冻结 | NO_HISTORY fast 存在但不公平 | **HUMAN GATE**：训练 + M3/M4 冻结 |

## 2. 执行顺序（对应用户 audit §24）

1. Exp1 FULL/REDUCED + CURRENT/HISTORY —— 本次实现（§3–4）
2. Exp2 Point + per-variant Variogram —— 已有重算函数，待接入新 records
3. Exp2 q=0~1 dependency-disruption series —— MISSING，后续
4. Exp3 response-only / valuation-only —— MISSING（LOW/BASE/HIGH 混淆），后续
5. Exp4 target × node × lead-time predictions —— 本次提供 record schema 模板，Exp4 侧后续接入
6. 统一 episode-cluster bootstrap —— `exp/common/bootstrap.py` 已有；records 落地后直接可用
7. Development Figure 5–8 + Table —— `section5_secondary_analysis` 扩展，后续
8. paper-output audit —— 已有 `paper_output_audit.md` 骨架，每步更新
9. 冻结 `PAPER_OUTPUT_SPEC_V1.json` —— 最后，human gate
10. 才进入 Test —— **不在本次范围**

## 3. Exp1A：paper-facing per-node records（本次实现）

每 decision node 一行 × variant（EXP1A_FULL / EXP1A_REDUCED）：

```text
episode_id | decision_node_id | variant
consequence_available | action_instantiation_available | comparison_available
n_instantiated_actions | n_comparable_actions
F_consequence | P_consequence | R_consequence
top1_action | ranking_available
```

- FULL 上下文 = 完整 PRE facts；REDUCED 上下文 = scenario state + identity + timing +
  action structurally required facts（= 全部 template `required_facts` 并集）+ support provenance；
  其余 current operational context（weather、hidden history、realized outcomes、future info）BLOCKED。
- consequence 按 variant **重新聚合**（不复制 FULL 行）；若 REDUCED==FULL，记录
  `consequence_invariant_to_reduced_context=true`（这是结果）。
- comparison/top1/ranking 在 M4 gate 前为 NOT_RUN（`comparison_available=false`,
  `n_comparable_actions=0`, `top1_action=null`, `ranking_available=false`），原因
  `NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE`。

## 4. Exp1B：per-node prediction records（本次实现）

每 model × target × node 一行：

```text
episode_id | decision_node_id | lead_time_minutes | lead_time_source | target
observed_minutes | point_prediction | absolute_error | crps | crps_supported | model_id
```

- targets：`T_IB_A00`（T^{-,IB,0}）、`D_OB`（D^{+,OB}）、`D_TX`（D^{+,TX}）。
- point_prediction = scenario draws 的 weighted median（有限值）；absolute_error = |ŷ−y|。
- crps 仅当 active label + ≥1 finite draw（`crps_supported` 显式）。
- lead_time：T_IB = realized remaining minutes；D_OB/D_TX = realized/planned event horizon，
  `lead_time_source` 显式；不可得时 NA，不插值。
- 本次只物化 HISTORY（M1_V2_GRU_H32）；CURRENT（M^cur）在公平 checkpoint 绑定前输出
  BLOCKED record（原因 `FAIR_CURRENT_ONLY_CHECKPOINT_REQUIRED`），fast NO_HISTORY 只作诊断。

## 5. Gates（human decision required）

- **G1**：Exp1B 公平训练协议（capacity 对齐 H32 vs NO_HISTORY H16；epochs/seeds；是否现在跑）。
- **G2**：M3 non-A00 / M4 production mapping 冻结（comparison/ranking 才可升 principal）。
- **G3**：Development 图表合法后冻结 `PAPER_OUTPUT_SPEC_V1.json`，才进 Test。

所有本次产物带 `DEVELOPMENT_ONLY` / `paper_result=false` / `FINAL_TEST_ACCESS_COUNT=0`。
