# AIR SLOT — Exp1 重构执行指令

## 0. 工作目录与写入边界

项目根目录：

`D:\research\air_slot\code\explore`

本任务只允许修改：

`D:\research\air_slot\code\explore\exp\exp1`

可以只读检查 `model/`、`registries/`、`configs/`、`exp/common/` 和现有测试，以适配最新接口；未经额外授权，不修改这些目录。

不要 commit、不要 push、不要运行正式 Final Test、不要运行 `paper_full`。

---

# 1. 科学任务

重构 Exp1，使其只回答论文中第一层必要性问题：

> Why must decision-relevant information be retained across stages, and why must admissible history remain in the recovery state?

Exp1 现在与 Section 3 的两条信息路径一一对应：

```text
Path 1 — state-mediated retention
E_{<=t} -> h_t -> S_t

Path 2 — direct downstream reuse
current E_t -> action instantiation / decision qualification
```

因此 Exp1 headline 固定为两个子实验：

1. **Exp1A — Direct cross-stage information reuse**
2. **Exp1B — History-mediated state dependence**

Exp1A 回答：

> Is the history-conditioned state/consequence representation alone sufficient, or must current decision-relevant information remain directly reusable downstream?

Exp1B 回答：

> Is the latest admissible snapshot sufficient for state formation, or must admissible history be retained?

Exp1 不负责回答：

- joint/scenario representation 相对 point/marginal 是否必要（Exp2A）；
- 7-component consequence representation 相对 coarse aggregation 是否必要（Exp2B）；
- recommendation 是否应随新信息 rolling refresh、state 是否需时间同步（Exp3）；
- 完整系统预测性能、有效性、跨数据环境与 runtime（Exp4）。

原 `DELAY_ONLY` 不再作为 Exp1A headline，因为它同时改变 episode-specific consequence heterogeneity，容易与 Exp2B 的 consequence representation/granularity 问题混淆。

原 `Shared-state efficiency` 继续保持移出 Exp1 headline，归入 Exp4D Appendix computational diagnostic。

# 2. 执行前必须完成的 preflight audit

开始修改 `exp/exp1` 前，先只读检查最新 `model/`，确认模型已经与论文逻辑同步。

至少确认：

## 2.1 State / rolling information contract

- decision-time cutoff 明确；
- 已发生并在时刻 `t` 可获得的 factual event 能按最新论文合同进入 rolling state；
- 未发生的未来 outcome 不能泄露；
- state-aware history 只使用 `information_cutoff <= decision_time` 的证据；
- rolling grid 与模型正式设置一致。

## 2.2 M1 contract

确认正式 primitive stochastic outputs 与论文一致，并检查实际命名：

- predecessor A00 in-block / remaining-in-block object；
- successor off-block delay；
- successor taxi/excess-taxi delay；
- samplewise derived takeoff delay；
- aligned joint/scenario output；
- history representations 至少可实现 CURRENT 与 full/adaptive history；
- 若 FIXED 30-min history 仍为冻结合法 variant，则复用，不重新选择窗口。

## 2.3 M2 contract

确认当前模型已经使用论文最新版 consequence ontology：

- Flight: `F_continuity`, `F_execution`, `F_propagation`
- Passenger: `P_time`, `P_itinerary`, `P_service`
- Resource: `R_operating`

共 3 channels / 7 components。

确认 turnaround continuity 已按最新论文修复，不再使用旧
`max(0, R_IB - turnaround_reference)`。

应检查当前模型实际实现与论文最终公式一致，例如：

`max(0, R_IB + turnaround_reference - time_to_scheduled_departure)`

或数学等价形式。

确认 native consequence → CU → monetary/RMB 的接口已经同步。

## 2.4 Action contract

确认 recovery library 为 **23 templates including A00**，并且：

- `R` 是 method-level library，不由 Data2 生成；
- episode-specific availability/instantiation 与 `R` 分离；
- response contracts、preparation times、required facts、coverage/support 由 model 正式接口提供；
- Exp1 不自行重新定义动作科学语义。

## 2.5 Support / provenance contract

确认最新模型对：

- factual availability；
- support ceiling；
- action comparability；
- scenario/conditional vs formally supported comparison

有明确接口。

Exp1 不得通过自己伪造 support 或 bypass model contract 获得更多可比较动作。

## 2.6 Gate

如果上述任一项仍与论文冲突：

**停止 Exp1 正式重构，不通过在 `exp/exp1` 中补丁式伪造模型行为来绕过。**

输出 `EXP1_MODEL_CONTRACT_BLOCKED.md`，逐项列出 mismatch。

---

# 3. 当前旧 Exp1 的处理原则

现有 Exp1 是旧 warning/lead-time 定位，当前 headline 包括类似：

- `DecisionWindowGain`
- sustained warning lead time
- warning recall / FPR
- retrospective leakage warning protocol

这些不再承担新 Exp1 的 scientific headline。

执行以下策略：

1. `model.M1.history` 中 CURRENT / FIXED_HISTORY / ADAPTIVE_HISTORY 等合法 history machinery 尽量复用。
2. 旧 warning metrics 若有仓库外部引用，不直接删除；保留 compatibility shim 或 legacy module。
3. 新 `runner.py`、active variants、headline metrics、README、reporting 必须切换到新 Exp1。
4. 先 grep 全仓库对 `exp.exp1.*` 旧函数的引用，再决定是否移动/保留 legacy functions。
5. 不允许旧 `DecisionWindowGain` 继续作为新 Exp1 headline metric。

---

# 4. Exp1A — Direct cross-stage information reuse

## 4.1 科学问题

headline 只比较：

- `NO_DIRECT_REUSE`
- `FULL`

回答：

> After a coherent history-conditioned state and baseline consequence have been formed, is it sufficient to pass only that mediated representation downstream, or must current decision-relevant information remain directly reusable for action formation and comparison?

该设计直接对应 Section 3：

```text
(E_{<=t}) -> S_t
and
current E_t -> F_A / F_D
```

关键边界：

**两个 variant 都必须保留完整 decision chain。**

不能：

- 删除 M2；
- 删除 action-instantiation；
- 直接 state -> action；
- 改 action library；
- 改 support/provenance rule；
- 改 consequence granularity。

这些分别属于 Exp2/Exp3 或模型本身。

---

## 4.2 A-FULL

调用最新正式 model chain，不做信息削减。

保留：

- legal decision-time information；
- history-conditioned M1 state；
- full aligned scenario state；
- full 7-component consequence representation；
- current timing / identity / resource / execution / support information；
- episode-specific action instantiation；
- formal action-response contract；
- formal comparison basis。

---

## 4.3 A-NO_DIRECT_REUSE

目的：

> 保留 state-mediated path，但阻断已经形成 state/consequence 后对非必要 upstream/current information 的再次读取。

流程：

1. M1 正常形成 history-conditioned aligned state；
2. M2 正常形成 full 7-component baseline consequence；
3. downstream comparison 以该 state/consequence representation 为主要输入；
4. 禁止重新读取已经被 state/consequence 吸收、但 method 并未声明必须直接复用的 upstream information；
5. 仅保留 action instantiation、structural feasibility、execution opportunity 和 support qualification 所不可避免的 **minimal current factual information**。

必须建立明确 allowlist。

allowed 至少包括：

```text
baseline consequence
aligned scenario id/weight
action id / target identity
frozen action-response contract
minimal structural/actionability facts
execution-window facts
support/provenance facts required for formal qualification
```

forbidden 至少包括：

```text
upstream hidden/history representation for downstream scoring
raw weather/context reread after it has been mediated through the formal state/consequence
undeclared auxiliary fields
future/realized outcomes
```

注意：

- 不能为了构造 ablation 而使本来合法的 action 无法实例化；
- minimal actionability facts 是 formal chain 必需输入，不算 leakage back to FULL；
- manifest 必须逐字段记录 `DIRECT_REUSE_ALLOWED / BLOCKED / STRUCTURALLY_REQUIRED`。

---

## 4.4 原 DELAY_ONLY 的处理

旧 `DELAY_ONLY` / episode-context neutralization 不再属于 headline。

原因：

- 它同时改变 consequence construction 中的 episode-specific heterogeneity；
- 容易把“跨阶段信息角色”与“consequence mechanism representation”混在一起；
- 与 Exp2B 的 scalar / channel / component comparison 产生解释重叠。

若已有代码需要保留：

```text
EXP1A_CONTEXT_NEUTRALIZED
```

只能标记为：

```text
LEGACY_OR_APPENDIX_DIAGNOSTIC
NOT_HEADLINE
```

不得用它承担论文第一研究问题的主证据。

---

## 4.5 Exp1A 评价

### 主评价量

1. **selected Top-1 action / Top-1 agreement**
2. **ex-post model replay residual-risk `J_post`**

这里的 Top-1 disagreement 回答：

> direct information reuse 是否实际改变了 decision output？

`J_post` 使用：

- variant 自己的信息权限选择 action；
- episode outcome 完成后构造相同合法 realized evaluation basis；
- 相同 frozen action-response specification；
- 相同 evaluation-side replay。

固定措辞：

`ex-post model-implied residual risk under the frozen action-response specification`

不得称为 observed causal treatment effect。

### 统计

- episode 为 cluster；
- 5-min rolling nodes nested within episode；
- paired episode-level comparison；
- episode-cluster bootstrap 95% CI；
- fixed bootstrap seed；
- 不使用 significance stars 作为主表达。

# 5. Exp1B — Historical dependence

## 5.1 科学问题

回答：

> Is the current snapshot sufficient, or does the rolling recovery state benefit from retaining admissible history?

优先复用当前 model 的正式 history representation。

Variant：

- `CURRENT`
- `FIXED_HISTORY_30`（仅当 30-min window 仍是最新 model 中已冻结的合法 variant）
- `ADAPTIVE_HISTORY`

如果最新 model 已取消 FIXED 30 的科学地位，则不自行恢复旧设计，改为：

- CURRENT
- latest official finite-history baseline（如存在）
- ADAPTIVE_HISTORY

不得因 Exp1 重新调历史窗口。

---

## 5.2 控制变量

三个 variant：

- 使用相同 Train/Calibration/Development/Test partition；
- 相同 targets；
- 相同 output semantics；
- 相同 calibration protocol；
- 相同 joint-scenario contract；
- 相同 M2/M3/M4；
- 尽可能使用相同 model class / parameter capacity / output heads；
- **只改变 admissible history representation**。

特别禁止：

- 用正式 `LIGHTGBM_FAST` 直接充当 `CURRENT`，再把 Exp1B 写成 history ablation；
- 这样会同时改变 architecture/model path，并与 Exp4A 的 FAST vs STATE_AWARE benchmark 重叠。

优先实现：

```text
CURRENT = same state-aware architecture with history truncated to current admissible node
ADAPTIVE = same state-aware architecture with full admissible recursive history
```

`FIXED_HISTORY_30` 只有在同一 architecture 下仍是官方合法 variant 时保留。

如果 model contract 无法提供 architecture-controlled CURRENT：

- 明确标记 `HISTORY_ISOLATION_PARTIAL`；
- 不把结果写成纯历史因果归因；
- 不通过另训一个明显更弱模型制造差距。

若模型要求各 history variant 分别训练 checkpoint：

- 只用 Train 训练；
- Calibration 只校准；
- Development 只冻结/选择；
- Final Test 不参与模型选择；
- 记录 checkpoint/hash/seed。

若模型正式支持同一 checkpoint 的 history truncation，则按 model contract 执行，不擅自重新训练。

---

## 5.3 Exp1B 主指标

### 概率预测层

1. **CRPS**
   - 对正式 primitive stochastic targets 分别报告；
   - 不自己发明 joint-CRPS。

2. **Brier score**
   - 主文优先使用一个预注册/正式 principal delay event，例如 `D_TO > 30 min`；
   - 15/30/60 其他 thresholds 可进 appendix。

3. **Calibration**
   - reliability/calibration plot；
   - 不需要再创造 calibration index。

### downstream

4. ex-post replay `J(a)`
5. Top-1 selected action / agreement

不要把旧 warning lead-time / DecisionWindowGain 作为 headline。

---

## 5.4 B 的分层分析

只使用项目已有、运营含义清晰的变量，不创造新指数。

优先：

- turnaround tightness / turnaround margin；
- time to scheduled departure；
- 必要时 delay severity bands。

目的是判断 history 的价值是否集中在：

- tight turnaround；
- 临近 departure；
- 快速演化的运行阶段。

分层边界若需要数值 cutoff：

- 优先使用模型/文献已有 threshold；
- 若没有，使用 Train/Development 冻结的 quantile cut；
- 不看 Test 后再选择 cutoff。

---

# 6. Shared-state efficiency — 移出 Exp1 headline

原 Exp1C 的科学问题：

> If the same decision-time operating state is required downstream, does constructing it once and reusing it improve computational efficiency relative to repeated reconstruction?

该问题保留，但 **不再由 Exp1 承担**。

执行原则：

- Exp1 runner / active variant registry 不再运行 `EXP1C_SHARED_STATE` 与 `EXP1C_RECOMPUTED_STATE`；
- 若旧代码存在外部依赖，允许保留 compatibility shim / legacy helper；
- 不在 Exp1 main figure、main table 或 headline metrics 中报告 runtime；
- Shared vs Recomputed 的正式 runtime/parity protocol 迁移到 **Exp4D Appendix diagnostic**；
- Exp1 只需保证自身不重新引入该 headline。

迁移后的计算实验必须满足：

```text
same legal records
same decision-time cutoff
same model weights
same frozen references
same scenario count
same action contracts
same comparison rule
same random numbers / deterministic seed
```

并要求 scientific outputs parity。任何 decision difference 都说明实现不等价，不能解释为效率收益。

# 7. Data2 与 split discipline

严格继承最新 model 的 Data2 partition。

如果仍为：

- Train: 2019-01--06
- Calibration: 2019-07
- Development: 2019-08--09
- Test: 2019-10--12

则直接复用。

禁止：

- node-level random train/test split；
- 同一 episode 跨 split；
- 用 Test 选择阈值、mask、reference、figure cutoff、history window、bootstrap 设置或 variant；
- 用 posthoc realized events 作为 decision-time inference evidence。

---

# 8. 新 Exp1 代码结构建议

在 `exp/exp1` 内，根据最新接口实现，推荐：

```text
exp/exp1/
├── __init__.py
├── README.md
├── protocol.py
├── variants.py
├── information.py
├── history.py
├── replay.py
├── metrics.py
├── statistics.py
├── reporting.py
├── figures.py
├── runner.py
├── audit.py
└── tests/
    ├── test_exp1_information.py
    ├── test_exp1_history.py
    ├── test_exp1_replay.py
    └── test_exp1_no_leakage.py
```

旧 `efficiency.py` / `test_exp1_efficiency.py` 若被外部代码引用，可以保留 legacy/compatibility wrapper，但不得进入新版 headline runner。

不是要求机械创建所有文件；先审查现有架构，避免重复。

核心原则：

- scientific protocol 与 orchestration 分开；
- masks/variants 不修改 frozen model artifact；
- metrics 不拥有 model logic；
- replay 不回流 inference；
- figures 只消费 frozen result tables。

# 9. Active variant registry

新 active Exp1 至少包含：

```text
EXP1A_NO_DIRECT_REUSE
EXP1A_FULL

EXP1B_CURRENT
EXP1B_FIXED_HISTORY_30      # only if still officially supported
EXP1B_ADAPTIVE_HISTORY
```

原 Exp1A variants：

```text
EXP1A_DELAY_ONLY
EXP1A_CONSEQUENCE_ONLY
```

必须从 headline registry 移除。若因兼容性保留：

```text
EXP1A_CONTEXT_NEUTRALIZED
LEGACY_OR_APPENDIX_DIAGNOSTIC
```

原：

```text
EXP1C_SHARED_STATE
EXP1C_RECOMPUTED_STATE
```

必须从 Exp1 headline registry 移除；如因兼容性保留，只能标记：

```text
LEGACY_COMPUTATIONAL_DIAGNOSTIC
MOVED_TO_EXP4D
```

旧：

```text
empirical
independent_heads
leakage_diagnostic
warning_*
DecisionWindowGain
```

不得继续出现在新 headline protocol 中。

若因兼容性必须保留，只放 legacy namespace / alias，并清楚标记非论文主实验。

# 10. Metrics 输出

不要创造奇怪指标。

## Exp1A
- ex-post model replay residual-risk `J`；
- selected Top-1 action；
- Top-1 agreement；
- 95% CI。

这里的 replay 只能解释为：

`ex-post model replay under the frozen action-response specification`

不能写成 observed causal benefit。

## Exp1B
- CRPS by primitive target；
- Brier score for principal delay event；
- calibration data；
- replay `J`；
- Top-1 action；
- 95% CI。

Appendix 可提供 Top-k / Kendall tau 等标准量，但不是主 headline。

Runtime / Shared-vs-Recomputed 不再属于 Exp1 metrics。

# 11. Main-paper reporting contract

## Figure: one restrained 2-panel figure

### Panel A — Direct cross-stage information reuse
Conditions:
- No direct reuse
- Full

显示：
- ex-post model replay residual risk `J`
- dot + 95% CI
- 不用夸张柱状图

caption 必须明确：两个 variant 都保留完整 decision chain，只改变 current information 是否可在 state/consequence 形成后继续直接供 action formation/comparison 使用。

### Panel B — Historical dependence
Conditions:
- Current
- Fixed 30
- Adaptive

显示：
- primitive-target CRPS（同为分钟单位时可 grouped points）
- calibration/Brier 放 table 或 appendix

caption 必须明确：比较的是 admissible history representation，不是不同质量的下游模型。

绘图风格：

- 面向 TRE/JORS；
- 克制、白底、去除 top/right spines；
- Full/Adaptive 使用一个低饱和强调色；
- baseline 用中性灰；
- 不把 baseline 用红色当“失败方法”；
- 不使用 radar/3D；
- 不任意截断 y-axis 放大差异；
- 输出 PDF vector + 300dpi PNG；
- caption 写清每个 panel 回答的问题，而不是只解释颜色。

# 12. Main table

生成可直接用于论文的 CSV/LaTeX-friendly table source，至少包含：

| Subexperiment | Condition | Metric | Estimate | 95% CI | N episodes |
|---|---|---|---:|---:|---:|

同时保留 raw episode-level summary，方便复算。

---

# 13. 审计产物

每次 Development/smoke run 输出：

1. `exp1_protocol_manifest.json`
2. `exp1_variant_manifest.json`
3. `exp1_information_mask_manifest.json`
4. `exp1_model_contract_snapshot.json`
5. `exp1_split_audit.json`
6. `exp1_leakage_audit.json`
7. `exp1_parity_audit.json`
8. `exp1_metrics.csv`
9. `exp1_summary.json`
10. figure source table(s)

记录：

- git SHA
- scientific config hash
- model/registry hashes
- seeds
- scenario count
- split
- final-test access count
- runtime environment
- variant definition hashes

不要把大 raw/output 文件提交 Git。

---

# 14. Test requirements

至少覆盖：

## Information
- NO_DIRECT_REUSE allowlist 明确且无 hidden upstream reread；
- minimal actionability/support facts 可用但不可被用于额外 scoring；
- Full 不被 mutation；
- 两个 Exp1A variant 都经过同一完整 decision chain；
- legacy context-neutralized variant 不进入 headline runner。

## History
- CURRENT 只有当前 admissible node；
- CURRENT 与 ADAPTIVE 尽可能保持相同 architecture/capacity/output heads；
- CURRENT 不得静默替换成 LIGHTGBM_FAST；
- FIXED_HISTORY 严格 causal；
- ADAPTIVE 从 episode start 到当前；
- 无 future information；
- 同一 episode 不跨 split。

## Replay
- realized outcome 只进入 evaluation/replay；
- 不回流 inference；
- 同一 action-response contract 用于各 variant；
- replay 结果在 artifact/caption 中标记为 model-implied，不写成 observed causal effect。

## Headline isolation
- Exp1 active registry 不包含 Shared/Recomputed；
- Exp1 main figure/table 不包含 runtime headline；
- 若 legacy efficiency helper 保留，其 runner 默认 inactive，并标记 moved-to-Exp4D。

## Reproducibility
- fixed seed；
- repeated dry run deterministic where expected；
- output manifests hashes stable。

# 15. Final-Test gate

本轮编码任务结束时：

```text
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
```

只允许运行：

- unit tests；
- synthetic/small smoke；
- Train/Calibration/Development dry run（若项目当前规则允许）。

不要执行 Final Test。

Formal Test 只有在：

- model contract PASS；
- Exp1 protocol frozen；
- metrics frozen；
- figures/table schema frozen；
- no-leakage PASS；
- parity PASS；
- human authorization

之后才能运行。

---

# 16. 完成后必须输出的状态摘要

结束时给出：

```text
AIR_SLOT_EXP1_REDESIGN

MODEL_CONTRACT_GATE =
EXP1A_DIRECT_REUSE_CONTRACT =
EXP1B_HISTORY_CONTRACT =
EXP1C_HEADLINE_STATUS = REMOVED_TO_EXP4D

LEGACY_WARNING_PROTOCOL_ACTIVE =
LEGACY_EFFICIENCY_HELPER_ACTIVE =
FINAL_TEST_ACCESS_COUNT =
PAPER_FULL_RUN =

FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =

REMAINING_BLOCKERS =
NEXT =
```

并逐项说明：

- 哪些旧 Exp1 文件被复用；
- 哪些旧 warning logic 已降为 legacy；
- Exp1A/Exp1B 分别对应论文哪个 scientific question；
- 原 Shared/Recomputed efficiency 代码是否保留 compatibility helper，以及是否已从 headline runner 移出；
- 是否存在任何需要修改 model 才能解决的问题。

# 17. 最重要的禁止项

1. 不为了让结果“更漂亮”调整 Test cutoff、mask、history window、reference 或 action rules。
2. 不用 Test 选择 plotting range / subgroup cutoff 后再当 confirmatory result。
3. 不通过删掉模型阶段实现 NO_DIRECT_REUSE；Exp1A 必须保持完整 decision chain。
4. 不重新把 Shared/Recomputed efficiency 放回 Exp1 headline；该问题已迁移 Exp4D。
5. 不把 scenario/expert action response 写成真实 causal effect。
6. 不把 realized BTS outcome 作为当时不可获得的 inference evidence。
7. 不重新定义 23-action library。
8. 不修改 model 科学语义来适配实验；若 model 与论文不一致，BLOCK。
9. 不继续使用 `DecisionWindowGain` 作为 headline。
10. 不 commit / push。


# 18. Cross-experiment boundary lock

- Exp1A owns **direct downstream reuse of current information**.
- Exp1B owns **history retention under architecture-controlled state formation**.
- Exp1 does not own uncertainty/dependence representation granularity (Exp2), process refresh/synchronization (Exp3), or predictive benchmark adequacy (Exp4).
- Exp1B must not reproduce the 0--480 min multi-model benchmark that belongs to Exp4A.
