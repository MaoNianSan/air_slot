# AIR SLOT — Exp1 执行指令 V4（2026-08-25）

> SUPERSEDED by codex_framework/AIR_SLOT_EXP1_DEVELOPMENT_CLOSURE_SUPPLEMENT_20260825.md.

> 本文件是 `AIR_SLOT_EXP1_REDESIGN_INSTRUCTION_20260819_V3.md` 的更新指令。
> 未覆盖的条目（信息边界、审计产物、Final-Test gate、禁改项）继续以 V3 为准；
> 与本文件冲突处，以本文件为准。
> 项目根目录：`D:\research\air_slot\code\explore`。

## 0. 用户决定（不可偏离）

- Exp1A：**完全停止 M2 接口改造**。改为在**冻结输出**上做
  “状态驱动量 vs context-conditioned consequence”的**排序分析**；
  所有统计只在**共同 supported observations**上进行。
- Exp1B：新增 **H32 Current-only Development comparator**，与现有
  **H32 History-conditioned**（FULL_ADAPTIVE_CAUSAL_PREFIX）**完全同预算、
  同校准路径**。
- Final Test 继续禁止：`FINAL_TEST_ACCESS_COUNT = 0`、`PAPER_FULL_RUN = FALSE`。

## 1. 稿子原文依据（逐字引用，`Rolling_Airline_Recovery_v2/sections/05_experiment.tex`）

Exp1A（`subsubsec:exp_direct_reuse`）：

> The first comparison asks whether the state and baseline consequence provide
> sufficient context for recovery comparison, or whether declared current
> operational information must also remain directly reusable when actions are
> formed, qualified, and compared. Both variants preserve the complete PRE--M4
> chain. The Full variant permits the declared direct reuse of current
> information. The No-Direct-Reuse variant blocks downstream rereads of
> upstream hidden history and raw weather context, while retaining the baseline
> consequence, aligned scenario identity and weight, action identity, minimum
> actionability facts, execution-window information, and support provenance.

Exp1B（`subsubsec:exp_history`）：

> The second comparison asks whether the current legal node is sufficient to
> represent the unresolved airline operating condition. The Current variant
> retains only that node, whereas the Adaptive-History variant retains the
> complete admissible prefix from the same episode ... Both variants reuse the
> same train-frozen state-aware architecture and checkpoint. The hidden
> dimension, prediction heads, targets, feature schema, calibration policy,
> scenario seed, support contract, and downstream procedures remain unchanged.
> A closed 30-minute history window on the five-minute grid is retained only as
> a sensitivity variant and is excluded from the principal Exp1B comparison.

实现层面说明（保持诚实边界）：

- Exp1A 的 Full/No-Direct-Reuse 掩码实现需要改造 M2 接口，**本次不执行**。
  本阶段用冻结输出上的排序分析作为 Development 条件诊断替身
  （`EXP1A_FROZEN_OUTPUT_SORTING`），不产生因果、最优或 authoritative ranking 主张。
  稿子的决策级端点（Top-1 disagreement、ex-post model-implied residual risk）
  仍声明为 M4 gate 前的 `NOT_RUN`，本阶段不假装完成。
- Exp1B 的 Current-only comparator 严格按稿子公式
  `H_cur = {E_{i,t}}`、`S_cur = F_S(H_cur)` 实现：同一 H32 GRU，
  序列只含当前合法节点 `t`（决策 D0E `CURRENT_NODE_ONLY`）。

## 2. 写边界

允许修改：

- `exp/exp1/**`
- `tests/experiments/exp1/**`
- `docs/experiment/EXP1_PROTOCOL.md`、`docs/HUMAN_DECISION_LOG.md`
- `codex_framework/`（本指令文件）

禁止修改：

- `model/**`（含 M1/M2/M3/M4、PRE）、`registries/**`、`configs/**`
- 不 commit、不 push、不跑 Final Test、不跑 `paper_full`

## 3. Exp1A —— 冻结输出排序分析契约

### 3.1 输入（全部只读、已冻结）

| 输入 | 路径 | 内容 |
| --- | --- | --- |
| 状态场景 | `artifacts/experiments/exp2/full_development_scenarios_v1/M1_V2_FULL_DEVELOPMENT_TYPED_SCENARIOS.parquet` | 1769 nodes x 250 scenarios；`D_TO` |
| 后果输出 | `artifacts/experiments/exp2/full_development_v1/M2_FULL_DEVELOPMENT_CONSEQUENCES.parquet` | 同键；`formal_five_component_value_cu`、`formal_five_component_status` |
| 输入绑定 | `artifacts/experiment/full_development_inputs_v1/FULL_DEVELOPMENT_INPUT_MANIFEST.json` | 冻结 hash、Development cohort |

两 parquet 必须逐键一致：`(episode_id, decision_node_id, scenario_id,
scenario_weight)`；键集合、行数（442,250）不一致即 BLOCK，不做对齐猜测。

### 3.2 两个量

- `q_state(i)`（状态驱动量）= 对 `D_TO` 有限且后果 `FORMAL_AVAILABLE` 的共同
  supported scenario 集合 `S_i` 做 scenario 加权平均（权重在 `S_i` 内显式重归一）。
- `q_ctx(i)`（context-conditioned consequence）= 对**同一个** `S_i` 的
  `formal_five_component_value_cu` 做 scenario 加权平均。

禁止：零填充、跨节点插补、把 unsupported scenario 的权重静默摊给其他
scenario。每个节点必须记录 `support_fraction_i = |S_i| / 250`。

### 3.3 共同 supported 规则

- scenario `s` 属于 `S_i` 当且仅当：`D_TO_{i,s}` 有限 且
  `formal_five_component_status_{i,s} == FORMAL_AVAILABLE`。
- 节点进入主分析当且仅当 `support_fraction_i >= 0.90`（主阈值，
  支持质量下限，不是按结果挑选的阈值）；敏感性分析用 `>= 0.50`。
- 被排除的节点按原因计数报告（`EXCLUDED_M1_NONFINITE`、
  `EXCLUDED_M2_NOT_AVAILABLE`、`EXCLUDED_SUPPORT_FRACTION_BELOW_THRESHOLD`）。

### 3.4 排序与统计（只算共同 supported 节点）

- 排序：节点按 `q_state` 与 `q_ctx` 分别排名（升序），同分取平均名次。
- 主指标：Spearman rho、Kendall tau、top-10% 与 top-20% 集合重叠率、
  十分位严重背离率（|decile(q_state) - decile(q_ctx)| >= 3 的节点占比）。
- 不确定性：episode-cluster bootstrap（2000 次、seed `20260825`），
  episode 内节点不拆散；同时保存逐 episode 统计。
- 次要看板：按 `operational_stage` 分层（PRE_IB / POST_IB_PRE_OB /
  POST_OB_PRE_TO）；`q_state` 的 p90 D_TO 敏感性（只报告，不进 headline）。

### 3.5 主张范围

`CLAIM_SCOPE = DEVELOPMENT_CONDITIONAL_DIAGNOSTIC`。输出 Interpretation
必须写明：这是 Development 排序一致性诊断，不构成 causal effect、
optimality、authoritative ranking 或 formal recommendation 主张。

## 4. Exp1B —— H32 Current-only comparator 契约

### 4.1 参照对象（已冻结 H32 History-conditioned）

`artifacts/experiment/m1_v2_tuning_stage1_fast/M1_V2_FAST_TUNING_MANIFEST.json`
中的 `M1_V2_GRU_H32`（hidden=32，`FULL_ADAPTIVE_CAUSAL_PREFIX`）：

- budget：Adam，lr=0.001，weight_decay=0.0，epochs=2，batch_size=64，
  seed=20260821，max_train_examples=128，max_development_examples=128，
  FAST_TRAIN_MODE，full_run=false，paper_result=false。
- 校准路径：同一冻结 B2 cache（`sha256:157c0d55...`），同一 feature schema
  （`sha256:1f4b886a...`），同一 support（T_IB 360 / D_OB 210 / D_TX 60 /
  bin 5），同一 loss `TARGET_SPECIFIC_EPISODE_BALANCED`；train
  [2019-01-01, 2019-06-30]、development [2019-08-01, 2019-09-30]；
  calibration [2019-07-01, 2019-07-31] 存在但
  `calibration_role = DO_NOT_USE_FOR_SELECTION`（两模型一致）。
- 唯一改变因子：history 表示（完整因果前缀 vs 单当前节点序列）。

### 4.2 新 comparator

- `variant = EXP1B_CURRENT_ONLY_H32`，`model_id = M1_V2_GRU_H32_CURRENT_ONLY`。
- 架构：与 H32 History 完全相同的 `M1V2GRU`（hidden 32、相同 heads、
  相同 r_fast/c_static 分支），history_mode 仍为
  `FULL_ADAPTIVE_CAUSAL_PREFIX`；只把每个训练样例的序列截成
  `values[-1:]`（当前合法节点，等价于 cache 的 `representation="CURRENT"`）。
- budget/校准路径与 4.1 逐项相同（不得换 seed、epoch、lr、batch、子集规则）。
- 训练只读同一 B2 cache 的 train/development 分区，不读 calibration、
  不读 Final Test；128/128 子集规则与 H32 History 一致
  （按 `(episode_date, episode_id)` 排序取前 128）。

### 4.3 产出物

1. checkpoint：`artifacts/experiment/exp1_full_development/h32_current_only_development/M1_V2_FAST_TRAIN_MODE.pt`
   （含 roundtrip 校验）。
2. 训练指标与 manifest（schema 与 FAST tuning record 一致，另加
   `history_representation = CURRENT_NODE_ONLY`、`comparator_of = M1_V2_GRU_H32`、
   `budget_identical_to_reference = true`、`calibration_path_identical_to_reference = true`）。
3. 全 Development 场景（S=250、同一 scenario seed）：
   `EXP1B_CURRENT_ONLY_TYPED_SCENARIOS.parquet` + manifest；
   从冻结 `M1_V2_FULL_DEVELOPMENT_INFERENCE_INPUTS.json` 取
   `encoded_adaptive_prefix[-1]` 作为当前节点编码（只读切片，不改输入）。
4. 配对 CRPS：Current-only vs History（冻结 exp2 场景 parquet）在同一批节点、
   同一标签（`M1_V2_FULL_DEVELOPMENT_LABELS.json`）上算
   R_IB（T_IB_A00）、DeltaOB（D_OB）、T_TX（D_TX）、D_TO；
   episode-cluster bootstrap（2000、seed `20260825`）。
5. 共同 supported 规则同上：scenario 双方量有限 + 标签 finite 才入统计；
   排除计数写入 manifest；不零填充。

### 4.4 主张范围

`CLAIM_SCOPE = DEVELOPMENT_COMPARATOR_ONLY`。不产生 Final Test、paper 或
scientific evidence 主张；`PAPER_FULL_RUN = FALSE`。

## 5. 完成状态摘要（结束后必须输出）

```text
AIR_SLOT_EXP1_REDESIGN_V4
EXP1A_M2_INTERFACE_CHANGES = NONE
EXP1A_FROZEN_SORTING = <MATERIALIZED|BLOCKED:reason>
EXP1B_CURRENT_ONLY_COMPARATOR = <MATERIALIZED|BLOCKED:reason>
EXP1B_BUDGET_IDENTICAL = <TRUE|FALSE:diff>
EXP1B_CALIBRATION_IDENTICAL = <TRUE|FALSE:diff>
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =
REMAINING_BLOCKERS =
NEXT =
```

