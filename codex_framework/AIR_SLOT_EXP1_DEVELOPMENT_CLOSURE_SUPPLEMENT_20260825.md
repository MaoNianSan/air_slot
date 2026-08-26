# AIR SLOT — Exp1 Development Evidence Closure 补充执行指令（2026-08-25 晚）

> 本文件是对用户已执行基线 `docs/experiment/DEVELOPMENT_CLOSURE_EXECUTION_20260825.md`
> 的**补充执行指令**：不动基线，不进入 Final Test。
> 本文件取代 `codex_framework/AIR_SLOT_EXP1_REDESIGN_INSTRUCTION_20260825_V4.md`；
> 冲突处以本文件为准。项目根目录：`D:\research\air_slot\code\explore`。

## 0. 三条用户决定（本指令的全部约束来源）

1. Exp1A **完全停止 M2 接口改造**；改为在**冻结输出**上做
   “状态驱动量 vs context-conditioned consequence”的**排序分析**；
   所有统计只在**共同 supported observations**上进行。
2. Exp1B 新增 **H32 Current-only Development comparator**，与现有
   **H32 History-conditioned** 完全**同预算、同校准路径**
   （= 对基线 G1 的回答：现在跑，协议如下文 §4）。
3. Final Test 继续禁止：`FINAL_TEST_ACCESS_COUNT = 0`、`PAPER_FULL_RUN = FALSE`。

## 1. 稿子原文依据（`Rolling_Airline_Recovery_v2/sections/05_experiment.tex`）

- Exp1A（`subsubsec:exp_direct_reuse`）：“whether the state and baseline
  consequence provide sufficient context for recovery comparison, or whether
  declared current operational information must also remain directly reusable
  when actions are formed, qualified, and compared … The No-Direct-Reuse
  variant blocks downstream rereads of upstream hidden history and raw weather
  context, while retaining the baseline consequence, aligned scenario identity
  and weight, action identity, minimum actionability facts, execution-window
  information, and support provenance.”
- Exp1B（`subsubsec:exp_history`）：“whether the current legal node is
  sufficient … Both variants reuse the same train-frozen state-aware
  architecture and checkpoint. The hidden dimension, prediction heads, targets,
  feature schema, calibration policy, scenario seed, support contract, and
  downstream procedures remain unchanged.”

## 2. 冻结输入（全部只读；hash 不符即 BLOCK，不重算不猜测）

| 输入 | 路径 | hash |
| --- | --- | --- |
| M1 HISTORY 场景（442,250 行=1,769 节点×250） | `artifacts/experiments/exp1/full_development_scenarios_v1/M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet` | `sha256:2ce9650a…` |
| M2 后果（同键） | `artifacts/experiments/exp2/full_development_v1/M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet` | `sha256:b4e8cc76…` |
| 标签（3 targets × 1,769） | `artifacts/experiment/full_development_inputs_v1/M1_V2_FULL_DEVELOPMENT_LABELS.json` | `sha256:47cba5d7…` |
| 推理输入（1769 节点，含 `encoded_adaptive_prefix`） | `artifacts/experiment/full_development_inputs_v1/M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json` | `sha256:6a5898e1…` |
| H32 History checkpoint | `artifacts/experiment/m1_v2_tuning_stage1_fast/GRU_H32/M1_V2_FAST_TRAIN_MODE.pt` | `sha256:e3401c76…` |
| B2 cache（+manifest） | `artifacts/diagnostics/m1_v2_feature_gate_b2/M1_V2_DEVELOPMENT_BASE_CACHE_B2.npz` | `sha256:157c0d55…` |
| 其余 frozen hashes | feature `1f4b886a…` / support `a8eea186…` / cohort `1dd88948…` | 与基线一致 |

## 3. Exp1A 执行契约（基线 §3 + 排序诊断；不碰 M2）

### 3.1 paper-facing per-node records（基线 §3 字段，逐行落地）

`episode_id | decision_node_id | variant(EXP1A_FULL/EXP1A_REDUCED) |
consequence_available | action_instantiation_available | comparison_available |
n_instantiated_actions | n_comparable_actions | F_consequence |
P_consequence | R_consequence | top1_action | ranking_available`

- consequence：从冻结 M2 行按 channel 重新聚合（F=F_cont+F_exec+F_prop；
  P=P_time（P_itin/P_serv 货币未锚定，记 event counts、不进 P 聚合）；
  R=R_operating），scenario 加权平均取节点值；`consequence_available=true`
  当且仅当该节点存在 `FORMAL_AVAILABLE` 的五分量 scenario。
- FULL/REDUCED 两行都必须由代码生成：REDUCED 只允许
  {scenario state, identity, timing, action structural required_facts,
  support provenance}。因 M2 冻结输入合同只消费 {S_t, identity,
  train-frozen references, assumption-frozen references}（基线事实 #4），
  REDUCED 的 consequence 与 FULL 数值相同是**计算结果**，记录
  `consequence_invariant_to_reduced_context=true`，不是复制行的捷径。
- action：用 `model/M3/instantiate.instantiate_candidates`（只读）分别算
  FULL/REDUCED；M3 只消费 template `required_facts/required_parameters`
  （基线事实 #5），记录 `action_instantiation_invariant_to_reduced_context`
  与 `n_instantiated_actions`。
- comparison/top1/ranking：M4 gate 前恒为
  `comparison_available=false, n_comparable_actions=0, top1_action=null,
  ranking_available=false`，reason=`NOT_RUN_SHARED_M4_MAPPING_AND_REPLAY_GATE`。

### 3.2 排序诊断（用户决定 1 的直接落地）

- `q_state(i)`：共同 supported 集 `S_i` 上 `D_TO` 的 scenario 加权均值（状态驱动量）。
- `q_ctx(i)`：同一 `S_i` 上 `formal_five_component_value_cu` 的 scenario
  加权均值（context-conditioned consequence）。
- `S_i = {s : D_TO_{i,s} 有限 ∧ five_component_status_{i,s}=FORMAL_AVAILABLE}`；
  权重在 `S_i` 内显式重归一，`support_fraction_i=|S_i|/250` 必须逐节点记录。
- 节点入主分析 ⇔ `support_fraction_i ≥ 0.90`；敏感性用 `≥ 0.50`；
  排除节点按原因计数（`EXCLUDED_M1_NONFINITE` /
  `EXCLUDED_M2_NOT_AVAILABLE` / `EXCLUDED_SUPPORT_BELOW_THRESHOLD`）。
  禁止零填充、跨节点插补、静默归一化。
- 统计：Spearman rho、Kendall tau、top-10%/top-20% 重叠率、
  十分位背离率（|decile(q_state)−decile(q_ctx)| ≥ 3）；
  episode-cluster bootstrap（2000 次、seed `20260825`、percentile 95% CI）；
  次要看板：`operational_stage` 分层、p90 D_TO 敏感性（只报告不进 headline）。
- 主张范围：`DEVELOPMENT_CONDITIONAL_DIAGNOSTIC`（非因果/非最优/非
  authoritative ranking）；稿件 Top-1/ex-post 端点仍 NOT_RUN（M4 gate）。

## 4. Exp1B 执行契约（基线 §4 + G1 已由用户决定回答）

### 4.1 参照（H32 History-conditioned，必须逐项复刻）

`M1_V2_GRU_H32`（hidden 32，`FULL_ADAPTIVE_CAUSAL_PREFIX`）：
Adam，lr=0.001，weight_decay=0.0，epochs=2，batch_size=64，seed=20260821，
max_train_examples=128，max_development_examples=128，FAST_TRAIN_MODE，
full_run=false，paper_result=false；校准路径：同一 B2 cache/feature/support，
loss=`TARGET_SPECIFIC_EPISODE_BALANCED`，train [2019-01-01,2019-06-30]、
development [2019-08-01,2019-09-30]，calibration 存在但
`calibration_role=DO_NOT_USE_FOR_SELECTION`；128/128 子集规则 =
按 `(episode_date, episode_id)` 排序取前 128。

### 4.2 comparator

- `variant=EXP1B_CURRENT_ONLY_H32`，`model_id=M1_V2_GRU_H32_CURRENT_ONLY`。
- 架构与 H32 History 完全相同（同一 `M1V2GRU` H32、heads、r_fast/c_static）；
  唯一改变因子 = history 输入：`cache.partition(split,
  representation="CURRENT")`（单当前合法节点序列，决策 D0E）。
- budget/校准路径与 4.1 逐项相同；不读 calibration 数据、不读 Final Test。
- 记录 `budget_identical_to_reference=true`、`calibration_path_identical_to_reference=true`
  （与参照 record 的 `training_config` 逐项 diff 为空）。

### 4.3 场景物化

- 新 parquet：`EXP1B_CURRENT_ONLY_TYPED_SCENARIOS.parquet`，S=250、同一
  `SCENARIO_SEED`（复用 `exp.workflows.m1_v2_current_stage_scenario_envelope`
  常量）；输入取冻结推理输入的 `encoded_adaptive_prefix[-1]`（只读切片）。
- manifest 标注 `DEVELOPMENT_COMPARATOR_ONLY`、`paper_result=false`。

### 4.4 per-node prediction records（基线 §4 字段，HISTORY + CURRENT 两套）

`episode_id | decision_node_id | lead_time_minutes | lead_time_source |
target | observed_minutes | point_prediction | absolute_error | crps |
crps_supported | model_id`

- targets：`T_IB_A00`、`D_OB`、`D_TX`；point=scenario weighted median（有限值）；
  crps 仅当 active label + ≥1 有限 draw（`crps_supported` 显式）。
- lead_time：T_IB=realized remaining minutes；D_OB/D_TX=schedule reference
  的 planned event horizon，`lead_time_source` 显式；不可得=NA，不插值。
- HISTORY 行从冻结场景+标签直接生成（不重新推理）；CURRENT 行用新 checkpoint。

### 4.5 配对汇总

- 共同 supported 节点上 MAE/CRPS（History vs Current-only），
  episode bootstrap 2000/percentile CI；ΔMAE(ℓ) 曲线表格只填有节点支持的
  lead-time bin，缺 NA，不插值。

### 4.6 主张范围

`DEVELOPMENT_COMPARATOR_ONLY`；`PAPER_FULL_RUN=FALSE`。

## 5. 统一统计层（全 Exp1 输出共用）

episode 内先聚合再跨 episode bootstrap（2000 次、seed `20260825`、percentile
95% CI）；不发明指标；NA 不插值；排除节点/场景按原因计数写入 manifest；
所有产物带 `DEVELOPMENT_ONLY`。

## 6. 写边界与产物

- 可改：`exp/exp1/**`、`tests/experiments/exp1/**`、
  `docs/experiment/EXP1_PROTOCOL.md`、`docs/HUMAN_DECISION_LOG.md`、
  `codex_framework/`（本补充）。
- 禁改：`model/**`、`registries/**`、`configs/**`、基线 closure 文档。
- 产物根：`artifacts/experiment/exp1_full_development/exp1_closure_20260825/`
  （records CSV/parquet + manifests + summary + interpretation；文件名含
  `DEVELOPMENT_ONLY`）。
- 不 commit、不 push、不跑 Final Test、不跑 paper_full。

## 7. 保留的人类 gates（本次不动）

- G2：M3 non-A00 / M4 production mapping 冻结（comparison/ranking 才升级）。
- G3：Development 图表合法后冻结 `PAPER_OUTPUT_SPEC_V1.json`，之后才允许 Test。

## 8. 完成状态块（执行结束必须输出）

```text
AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT
EXP1A_M2_INTERFACE_CHANGES = NONE
EXP1A_PER_NODE_RECORDS = <MATERIALIZED|BLOCKED:reason>
EXP1A_FROZEN_SORTING = <MATERIALIZED|BLOCKED:reason>
EXP1B_CURRENT_ONLY_COMPARATOR = <MATERIALIZED|BLOCKED:reason>
EXP1B_BUDGET_IDENTICAL = <TRUE|FALSE:diff>
EXP1B_CALIBRATION_IDENTICAL = <TRUE|FALSE:diff>
EXP1B_PREDICTION_RECORDS = <HISTORY/CURRENT:MATERIALIZED|BLOCKED:reason>
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =
REMAINING_BLOCKERS =
NEXT =
```
