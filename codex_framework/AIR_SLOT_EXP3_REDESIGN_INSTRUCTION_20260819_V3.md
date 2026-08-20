# AIR SLOT — Exp3 重构执行指令

## 0. 工作目录与写入边界

项目根目录：

`D:\research\air_slot\code\explore`

本任务只允许修改：

`D:\research\air_slot\code\explore\exp\exp3`

可以只读检查：

- `model/`
- `registries/`
- `configs/`
- `exp/common/`
- `exp/exp1/`
- `exp/exp2/`
- tests / validation / reporting

未经额外授权，不修改这些目录。

不要 commit、不要 push、不要运行正式 Final Test、不要运行 `paper_full`。

---

# 1. Exp3 的论文定位

Exp3 只回答：

> **Given an already rolling airline-recovery setting, how should a fixed decision technology use newly admissible information and a time-aligned operating state?**

不要把 Exp3 写成 module benchmark，也不要训练/建立新的 M1/M2/M3/M4。

不要从头求解一个新的全局 airline recovery optimization problem。

特别强调：

> **Rolling recovery itself is not claimed as the paper's novelty.**

动态恢复、rolling update、信息逐步揭示在既有航空恢复研究中已经存在。Exp3 的任务是检验本文固定 decision chain 的一个具体 methodological implication：

```text
new admissible information arrives
-> recommendation should be refreshed through the same frozen chain

current decision time changes
-> downstream comparison should receive a state synchronized to that time
```

Exp3 的统一约束：

```text
same frozen M1
same frozen consequence model
same 23-action library including A00
same action-response contracts
same provenance/support rules
same risk criterion J
same Data2 episodes
same monetary interface
```

只改变 decision process。

新版 headline subexperiments：

1. **Exp3A — Decision refresh**
   - ONE_SHOT
   - ROLLING

2. **Exp3B — State synchronization**
   - SYNC
   - STATE_LAG_5
   - STATE_LAG_10

论文实验总逻辑：

```text
Exp1: Why share?
Exp2: In what representation?
Exp3: How should the fixed chain use evolving information?
Exp4: Does the complete system perform adequately?
```

# 2. Exp3 不回答什么

以下不是新版 Exp3 headline：

- 替换 M1；
- 替换 M2；
- 替换 M3；
- 删除某一个 module 看性能；
- direct state -> action baseline；
- frozen action library vs dynamic action library；
- no evidence distinction；
- no material coverage gate；
- no induced consequence；
- risk neutral vs risk sensitive；
- LLM operational reasonableness audit。

旧 support/provenance/risk ablations 可以保留为 Appendix / diagnostics，但不能再定义 Section 4.3 主故事。

---


# 2.1 Cross-experiment isolation lock

Exp3 只改变 **decision process in time**。

固定：

```text
information-role contract from Exp1
representation contract from Exp2
full/adaptive history state
full JOINT scenarios
full 7-component consequence basis
same action library/support rules
```

因此：

- Exp3A 不重新比较 direct reuse / no-direct-reuse；
- Exp3B 不重新比较 point/marginal/joint；
- Exp3B 不改变 consequence granularity；
- Exp3 不承担完整模型 predictive benchmark；
- Exp3 不审计“当前时刻刚发出的 recommendation 是否合法”，该问题属于 Exp4B。

Exp3A 中的 executability 指标专门指：

> **a recommendation that was valid when issued at \(t_0\), whether it remains executable/comparable as it ages.**

这与 Exp4B 的：

> **whether a recommendation is valid/admissible at the time it is issued**

必须严格区分。

# 3. 执行前 Preflight Model Audit

开始改 `exp/exp3` 前，只读审查最新 `model/`。

若关键合同不满足，生成：

`EXP3_MODEL_CONTRACT_BLOCKED.md`

并停止正式 Exp3 实现。

禁止在 `exp/exp3` 中伪造 model 语义。

## 3.1 Rolling state contract

确认：

- decision-time information cutoff 正确；
- rolling nodes 正式间隔仍为 5 min；
- 10 min 仍是已冻结 sensitivity interval；
- resolved event 在合法 availability time 后能进入 factual state；
- unresolved quantities 保持 scenario representation；
- historical hidden state / scenario artifact 可以按 node/version 读取；
- 可以读取过去合法 node 的 state artifact，而不重新训练 M1。

## 3.2 Consequence / action / comparison

确认：

- current 3-channel / 7-component consequence model 已正式同步；
- 23 templates including A00；
- action availability / execution opportunity 可按当前 node 计算；
- formal comparison/support gate 已冻结；
- `J(a)` 可对当前 formally comparable action 调用；
- action response 仍是 frozen scenario-response model，而非 causal effect estimate。

## 3.3 Ex-post replay

确认 model/evaluation layer 能在 realized outcome 可得后构造统一 evaluation basis，并对一个在决策时刻选出的 action 应用同一 frozen action-response specification。

如果没有正式 replay API：

- Exp3 可以在 `exp/exp3` 内实现 evaluation-only adapter；
- 但 adapter 只能调用 model 已有 consequence/action-response semantics；
- 不得重新定义 action effect；
- realized outcomes 绝不回流 inference。

## 3.4 Formal multi-action cohort

统计 Development 中：

```text
nodes with >= 2 formally comparable actions
episodes with >= 1 such node
episodes with repeated such nodes
```

Exp3A/3B 主分析要求至少有足够 formal multi-action coverage。

如果不足：

- 不放宽 support gate；
- 不把 scenario-only actions 偷升 formal；
- 标记 `EXP3_FORMAL_COHORT_BLOCKED`；
- Development 可保留 conditional/scenario exploratory evidence，但不能冒充 paper evidence。

---

# 4. 旧 Exp3 的处理

当前旧 Exp3 原则：

> ablations are transformed copies of frozen artifacts; they do not retrain or mutate formal inputs.

这个原则保留。

## 可保留

- immutable artifact copying；
- hash audit；
- support/provenance feasibility audit；
- old LLM audit as auxiliary only；
- old no-induced/no-evidence/no-coverage/risk-neutral diagnostics if external code depends on them。

## headline 降级

以下不再是主指标：

```text
FormalCoverage
InvalidatedTop1Rate
FormalDecisionLeadTime
```

它们可以成为 support-boundary appendix table，但不承担“为什么按照当前 decision process 运行”的主回答。

---

# 5. Exp3A — ONE_SHOT vs ROLLING

## 5.1 科学问题

回答：

> Once the first valid recovery recommendation has been formed, does newly admissible information need to be propagated through the same fixed decision chain to refresh that recommendation?

不是：

```text
static recovery literature vs dynamic recovery literature
```

也不是：

```text
static model vs dynamic model
```

而是：

```text
same frozen decision technology
same scientific objects
different recommendation-refresh process
```

因此 Exp3A 只能支撑：

> continued refresh is operationally useful under evolving information on the evaluated cohort

不能支撑：

> rolling recovery is a new contribution of this paper.

# 6. Exp3A anchor t0

对 episode i，定义：

\[
t_i^0 =
\min\{t: |A_{i,t}^{cmp}| \ge 2
\text{ and at least one non-A00 action is formally comparable}\}.
\]

解释：

> the first rolling node at which the system can make a genuine formal recovery choice.

必须记录：

- anchor rule；
- anchor node；
- number of formally comparable actions；
- non-A00 count；
- support state。

如果最新 model 有更正式的 `first_decision_eligible_node` contract，优先复用。

不能用 Test 后挑一个“效果最好”的 t0。

---

# 7. EXP3A_ONE_SHOT

在 t0 正常运行完整正式链：

```text
E_t0
 -> S_t0
 -> C_t0
 -> A_cmp_t0
 -> rank under J_t0
 -> selected action a_one
```

之后不刷新 recommendation：

```text
displayed / retained recommendation = a_one
```

但不要声称该 action 已经在 t0 被真实执行。

因为当前 public data / scenario-response model 不识别一个 action 执行后如何因果改变后续真实状态。

ONE_SHOT 的解释：

> the control process continues to retain the first valid recovery recommendation instead of recomputing the recommendation when new information arrives.

---

# 8. EXP3A_ROLLING

在每个合法 rolling node t：

```text
E_t
 -> S_t
 -> C_t
 -> A_cmp_t
 -> rank under same frozen J
 -> a_roll(t)
```

这里是：

`rolling re-evaluation / rolling re-ranking`

不是：

`reoptimization from scratch`

M1 参数、M2 参数、action contracts、J 全部不变。

---

# 9. Exp3A 评价必须分两部分

旧 recommendation 在后续节点可能已不可执行/不可正式比较。

不能给这种 action 人工赋：

```text
J = infinity
```

或任意大 penalty。

因此分为：

## 9.1 Operational validity / feasibility outcome

对每个后续正式 decision node t，检查：

```text
a_one in A_cmp(i,t)?
execution opportunity open?
structural conditions still valid?
```

主文直接报告标准比例：

### `Recommendation still executable/comparable (%)`

若 formal comparability 混合了 evidence support 与 physical execution，可同时拆开：

- `execution opportunity open (%)`
- `formally comparable (%)`

这是比例，不创造新 score。

---

## 9.2 Common-support outcome comparison

仅在：

```text
a_one and a_roll(t)
both belong to the same current formal comparison support
```

的 paired nodes 上做 quantitative outcome comparison。

两个 selected actions 等 episode realized outcome 可合法用于 evaluation 后，都放回同一个 full evaluation basis：

```text
J_post(a_one)
J_post(a_roll)
```

其中：

`J_post`

固定解释为：

> ex-post model-implied residual risk under the frozen action-response specification.

不能称为 observed causal benefit。

---

# 10. Exp3A 指标选择

指标选择原则：

1. 航空/OR/运营管理读者能直接理解；
2. 直接回答 retained recommendation 是否会随信息演化而失效/改变；
3. 清楚区分 operational validity 与 model-implied comparison；
4. 不创造奇怪新指数。

## Tier 1 — operational headline

### A. Recommendation remains executable (%)

直接体现旧 recovery recommendation 是否还能落地。

若 formal comparability 与 physical execution 可以区分，同时报告：

- execution opportunity open (%)；
- formally comparable (%)。

推荐将该结果作为 Exp3A 最直接的 operational headline。

## Tier 2 — controlled model-implied process outcome

### B. Ex-post common-support model replay `J_post`

报告：

```text
ONE_SHOT
ROLLING
paired difference in RMB
relative difference (%)
95% CI
```

`J_post` 只能固定解释为：

> ex-post model-implied residual risk under the frozen action-response specification.

不能称为 observed causal savings，也不能单独用于声称 rolling 在现实中“更有效”。

不要只报告百分比，必须保留绝对 RMB/episode（或当前 monetary unit）结果。

## Operational / industry-facing supplementary outputs

### C. Flight-delay consequence

如果 model formal replay 能输出 comparable post-action flight-delay minutes，则报告：

- successor takeoff delay minutes；
- 或 flight-operation delay minutes。

优先复用 model 已有 delay quantity，不新造 KPI。

### D. Passenger-delay consequence

如果正式 replay 支持：

- passenger-minutes of delay

则作为 passenger-facing KPI。

不要把不存在的 individual passenger realization 当 observed fact。

### E. Recovery action composition — supplementary only

Exp2B 已把 action-family composition 作为 representation-mechanism headline，因此 Exp3 不重复占主图。

Exp3 仅在 supplementary table / Appendix 报告 selected action family shares：

- timing；
- capacity；
- passenger；
- ground；
- aircraft；
- crew；
- network/cancellation；
- A00。

特别可单列：

- aircraft swap share；
- cancellation/truncation share；

因为这些是航空 recovery 文献/实践中容易解释的高强度 recovery actions。

# 11. Exp3A diagnostics

以下是 diagnostics，不是 headline：

- Top-1 agreement；
- number of nodes with recommendation change；
- current-time `J_t` difference。

不要创造：

- Decision Churn Index；
- Adaptation Score；
- Rolling Value Index。

---

# 12. Exp3A recommendation-age analysis

定义自然时间量：

\[
age = t - t_0.
\]

按 5-min bins 报告：

- retained recommendation still executable (%);
- retained recommendation still formally comparable (%);
- Top-1 agreement with current rolling recommendation；
- common-support ex-post J difference。

不要创建“recommendation freshness score”。

Development 阶段冻结最大 age window。

若 episode 长度不足，不外推。

---

# 13. Exp3A heterogeneity

只做少量、业务含义强的分层。

优先：

1. turnaround flexibility；
2. downstream exposure；
3. information-update type。

不要机场×航司×时段×航线大规模切片。

### turnaround

tight / moderate / loose。

cutoff：

- 优先 model/文献已冻结 threshold；
- 否则 Train/Development quantiles；
- Test 不参与。

### expected interpretive pattern

不是要求 Rolling 到处换动作。

更可信的模式是：

```text
stable / flexible states:
ONE_SHOT ≈ ROLLING

tight / evolving states:
ONE_SHOT recommendation ages faster
ROLLING changes recommendation when new information materially changes state
```

只有数据支持时才写。

---

# 14. Exp3B — SYNC / STATE_LAG_5 / STATE_LAG_10

## 14.1 科学问题

回答：

> If the decision is refreshed, must the history-conditioned operating state handed downstream also be synchronized with the current decision time?

formal chain：

\[
D_{i,t}=F_D(E_{i,t},S_{i,t},A_{i,t}).
\]

Exp3B 只改变 state vintage：

\[
D_{i,t}^{lag}
=
F_D(E_{i,t},S_{i,t-\delta},A_{i,t}).
\]

---

# 15. EXP3B_SYNC

正式流程：

```text
current E_t
current S_t
current consequence derived from S_t
current A_cmp_t
current J contract
```

---

# 16. EXP3B_STATE_LAG_5

使用：

```text
current E_t
state artifact from t-5
current action domain A_cmp_t
same consequence transformation
same response contract
same risk criterion
```

具体实现：

```text
S_(t-5)
  -> apply same current consequence function
     with allowed current direct information E_t
  -> lagged-state consequence
  -> evaluate current A_cmp_t
```

禁止直接复制一个 arbitrary old action ranking。

---

# 17. EXP3B_STATE_LAG_10

同理：

```text
S_(t-10)
 + current direct information
 + current A_cmp_t
 -> same downstream chain
```

5 min 来自 principal rolling interval；
10 min 来自既有 roll sensitivity。

不增加 Test-driven 15/20/30-min lag 主实验。

如 Development 认为需要更长 lag，只能预注册到 Appendix sensitivity，Test 前冻结。

---

# 18. Exp3B 最重要的控制

三组必须使用完全相同的：

```text
current action set A_cmp_t
current structural/execution facts
current direct information E_t
same consequence model
same action-response parameters
same support/provenance gate
same J
```

唯一改变：

```text
state vintage
```

如果 action set 因 variant 改变：

`EXP3B_PROCESS_ISOLATION_FAIL`

不能把结果解释成 synchronization effect。

---

# 19. Exp3B principal evaluation

三组分别在 decision time 选择：

```text
a_sync(t)
a_lag5(t)
a_lag10(t)
```

主评价不能使用 `J_sync,t` 直接证明 SYNC 更好，因为 SYNC 本来就在该 objective 下最小化。

必须用统一 ex-post model replay：

```text
J_post(a_sync)
J_post(a_lag5)
J_post(a_lag10)
```

全部使用：

- same realized evaluation basis；
- same full current/formal consequence scope；
- same frozen action-response specification。

---

# 20. Exp3B 指标

## Headline

### A. Ex-post common-replay residual risk / recovery cost

```text
SYNC
LAG_5
LAG_10
```

报告：

- absolute RMB；
- paired RMB difference；
- relative difference；
- 95% CI。

## Operational outputs

### B. Flight delay minutes

如果 formal replay 支持，报告 model-implied post-action delay minutes。

### C. Passenger delay minutes

如果正式支持，报告 passenger-minutes。

### D. Selected action / action family

报告：

- Top-1 agreement；
- action-family distribution；
- cancellation/swap shares if sample supports。

Top-1 是 decision diagnostic，不是新的 utility metric。

---

# 21. Exp3B information-update strata

这一组最重要的 mechanism analysis 不是随机 demographic subgroup，而是：

## 21.1 No substantive new operating information

作为 negative-control-like stratum。

预期 SYNC / LAG_5 差异应小。

## 21.2 New weather information

最新合法 weather observation 在两个 nodes 之间进入。

## 21.3 Resolved factual operating event

例如 upstream unresolved event becomes factual。

如果最新 model 能区分：

- predecessor in-block factualization；
- successor off-block factualization；

分别报告 Appendix，主文可合并为 factual-event update。

## 21.4 State-change type 来源

必须来自 PRE / evidence ledger / variable lineage / event availability logs。

禁止根据 Test outcome 事后人工标注“important update”。

---

# 22. Exp3B turnaround-flexibility interaction

主文建议保留一个管理分层：

```text
SYNC / LAG5 / LAG10
×
tight / moderate / loose turnaround
```

这直接连接：

- state freshness；
- remaining recovery flexibility。

不要再加入多个交互项。

只有数据支持时写：

> stale state propagation has larger operational consequences when recovery flexibility is limited.

---

# 23. 统计协议

## Unit

episode 为 cluster。

5-min nodes nested in episode。

## Paired comparison

所有 variant 尽量在完全相同 episode/node 上比较。

## CI

episode-cluster bootstrap 95% CI。

建议：

```text
2000 replicates
fixed bootstrap seed
paired resampling
```

如果项目 common statistics 已有统一设置，复用。

主文优先：

- estimate；
- absolute paired difference；
- relative difference；
- 95% CI。

不使用 significance-star-heavy presentation。

---

# 24. “业界认 + 能说明问题 + 展示效果好”指标层级

最终不要把几十个指标都画出来。

## Tier 1 — paper headline

1. **Recovery cost / residual-risk RMB (`J_post`)**
2. **Flight delay minutes**（仅当正式 replay 支持）
3. **Passenger delay minutes**（仅当正式 replay 支持）

这些最贴近 airline recovery 常用 total cost / flight delay / passenger delay。

## Tier 2 — process mechanism

4. **Recommendation still executable (%)** — Exp3A
5. **Top-1 action agreement (%)**
6. **selected action-family shares** — supplementary/descriptive
7. **cancellation / aircraft-swap share**（样本够时；supplementary）

## Tier 3 — appendix diagnostics

8. current-time J difference
9. formal coverage/support rates
10. ranking@k / Kendall tau
11. old Exp3 support ablation metrics
12. DeepSeek operational-reasonableness audit

不得创造新的 composite score。

---

# 25. Figure strategy — migrate figures4papers, do not copy its domain style

从 `ChenLiu-1996/figures4papers` 迁移：

- minimal top/right spines；
- consistent typography；
- consistent semantic mapping across panels；
- trend lines for temporal processes；
- multi-panel narrative；
- direct labels / restrained legends；
- print-safe distinction；
- PDF/SVG vector export；
- 300dpi PNG；
- panel-level consistency。

不要机械迁移：

- AI benchmark leaderboard bars；
- huge font / ultra-wide canvas；
- radar；
- 3D；
- aggressive red-vs-blue method rhetoric；
- manually tight y-axis that exaggerates differences；
- dozens of annotated numbers above bars。

TRE/JORS 版本应该更接近 operations/transportation figure：

- compact；
- uncertainty visible；
- units explicit；
- actual values and effect sizes both recoverable；
- neutral baselines；
- one restrained highlight for formal process。

---

# 26. Main Figure — 推荐 2×2

## Panel A — Aging of the initial recommendation

x-axis：

`recommendation age (min)`

y-axis：

`recommendation still executable (%)`

可再用不同线型显示：

- executable；
- formally comparable；

如果两者过于拥挤，只主图保留 executable，formal comparability 放 appendix。

line + bootstrap CI band。

这应成为 Exp3A 最直接的主图，因为它不依赖内部 objective 的机械最小性质。

## Panel B — Controlled refresh comparison

显示：

```text
ONE_SHOT
ROLLING
```

y-axis：

`ex-post model-implied J_post`，单位 RMB/episode 或当前正式货币单位。

形式：

- dot + 95% CI；
- paired difference 可用 inset / direct annotation；
- 不用厚重 bar。

caption 必须写出：

`under the frozen action-response specification`

不得把 panel 标成 observed recovery savings。

## Panel C — State-vintage lag

x-axis：

```text
0
5
10 min
```

y-axis：

`ex-post model-implied J_post`

dot/line + 95% CI。

表现 state-vintage sensitivity，而不是宣称 universal lag penalty。

## Panel D — Lag × turnaround flexibility

x-axis：

```text
0 / 5 / 10 min lag
```

y-axis：

`ex-post model-implied J_post`

三条：

```text
tight
moderate
loose
```

只在样本充足时画三条；
否则只 tight vs non-tight。

若 Panel D 样本不足，优先替换为：

- SYNC / LAG5 / LAG10 的 Top-1 agreement / action-family change，

不要为了凑 2×2 强行画不稳定交互。

# 27. Secondary figure / case trajectory

可选择一个 **Development-predefined selection rule** 的 representative episode。

不能 Test 后手挑“最好看的”。

selection rule 可按：

```text
factual event arrives
AND rolling vs one-shot differs
AND formal support complete
AND no missing replay output
```

若有多个，按固定规则（例如最大的 pre-registered absolute J_post difference，或 deterministic episode id）选择。

时间轴可显示：

```text
decision time
new information/event
turnaround margin
selected action under ONE_SHOT
selected action under ROLLING
selected action under LAG5
selected action under SYNC
```

下方可配：

- major consequence components；
- open execution opportunity。

这个 case 是 explanation，不替代 aggregate statistics。

---

# 28. Main tables

## Table A — Exp3A

至少：

| Process | J_post | Flight delay min | Passenger delay min | Recommendation executable % | Top-1 agreement | N episodes |
|---|---:|---:|---:|---:|---:|---:|

不支持的 operational metric 显示 `—`，不要伪造。

## Table B — Exp3B

| State vintage | J_post | Flight delay min | Passenger delay min | Top-1 agreement | N episodes |
|---|---:|---:|---:|---:|---:|

补：

- absolute paired difference；
- 95% CI。

---

# 29. 建议代码结构

在当前 `exp/exp3` 基础上审查后重构，避免机械创建无用文件。

推荐职责：

```text
exp/exp3/
├── __init__.py
├── README.md
├── protocol.py
├── decision_refresh.py
├── state_vintage.py
├── replay.py
├── metrics.py
├── statistics.py
├── stratification.py
├── trajectory_case.py
├── reporting.py
├── figures.py
├── audit.py
├── runner.py
├── legacy/
└── tests/
```

如果旧 imports 被仓库其他位置依赖：

- 保留 compatibility shim；
- 不直接破坏 public import。

---

# 30. Active variant registry

主实验：

```text
EXP3A_ONE_SHOT
EXP3A_ROLLING

EXP3B_SYNC
EXP3B_STATE_LAG_5
EXP3B_STATE_LAG_10
```

旧：

```text
FULL_CONTRACT
NO_EVIDENCE_DISTINCTION
NO_MATERIAL_COVERAGE_GATE
NO_INDUCED_CONSEQUENCE
RISK_NEUTRAL
mean_only
mean_cvar
```

降级为：

`LEGACY_DIAGNOSTIC`

不得继续作为新版 headline variants。

---

# 31. 审计产物

每次 smoke / Development run 至少输出：

1. `exp3_protocol_manifest.json`
2. `exp3_model_contract_snapshot.json`
3. `exp3_variant_manifest.json`
4. `exp3_anchor_audit.json`
5. `exp3_decision_refresh_audit.json`
6. `exp3_state_vintage_audit.json`
7. `exp3_common_support_audit.json`
8. `exp3_replay_manifest.json`
9. `exp3_split_audit.json`
10. `exp3_leakage_audit.json`
11. `exp3_metrics.csv`
12. `exp3_action_family.csv`
13. `exp3_summary.json`
14. figure source tables

记录：

- git SHA；
- scientific config hash；
- model/registry hashes；
- anchor definition；
- roll interval；
- lag values；
- seeds；
- scenario count；
- episode/node cohort；
- support status；
- final-test access count。

---

# 32. 必须测试

## Exp3A

- t0 deterministic；
- t0 has >=2 formal actions and >=1 non-A00；
- ONE_SHOT action frozen after t0；
- ROLLING refreshes only when normal model contract says to；
- no retraining；
- no model mutation；
- old recommendation feasibility checked with current facts；
- invalid old action not assigned artificial infinite J；
- common-support replay only compares valid paired actions。

## Exp3B

- SYNC uses S_t；
- LAG5 uses exactly previous 5-min legal state artifact；
- LAG10 uses exactly previous 10-min legal state artifact；
- current E_t identical across variants；
- current A_cmp_t identical across variants；
- same consequence/action-response evaluator；
- no hidden current S_t leaks into lag variant；
- unavailable past state => node excluded/explicitly unavailable, never silently fallback to SYNC。

## Replay

- realized outcome only evaluation-side；
- same replay basis across compared actions；
- no causal-effect wording in artifacts；
- deterministic under fixed random numbers where expected。

## Statistics

- cluster by episode；
- paired resampling；
- reproducible CI。

---

# 33. Formal interpretation / claims

Exp3 总体只支持：

> How an already rolling recovery setting should propagate newly admissible information through the paper's fixed decision chain.

Exp3A only supports:

> Whether continued recommendation refresh under evolving information is operationally useful on the evaluated cohort.

Exp3B only supports:

> Whether downstream use of a time-aligned recovery state matters for current recovery comparison.

必须明确区分：

```text
established context:
dynamic / rolling airline recovery already exists

paper-specific implication tested here:
new information must be propagated through the same chain
and the downstream state should remain synchronized
```

Do not claim:

- rolling recovery itself is novel；
- globally optimal recovery；
- observed causal savings from unexecuted actions；
- actual airline controller behavior；
- universal optimal 5-min refresh frequency；
- universal causal penalty of a 5/10-min state lag；
- all modules must always recompute from scratch。

任何 `J_post` / delay / passenger-delay replay output 都是：

`model-implied under the frozen action-response specification`

除非未来有独立、合法的 causal/action-outcome identification，不得升级措辞。

# 34. Final-Test gate

本轮只允许运行：

- unit tests；
- synthetic/small smoke；
- Train/Calibration/Development dry run（若项目规则允许）。

结束：

```text
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
```

正式 Test 只有以下全部 PASS 后才允许：

- model contract frozen；
- Exp3 t0 anchor frozen；
- Exp3A process contract frozen；
- Exp3B lag contract frozen；
- common-support rule frozen；
- replay evaluator frozen；
- metrics frozen；
- stratification frozen；
- figure/table schema frozen；
- no-leakage PASS；
- human authorization。

---

# 35. 完成状态输出

完成后输出：

```text
AIR_SLOT_EXP3_REDESIGN

MODEL_CONTRACT_GATE =
FORMAL_MULTI_ACTION_COHORT =
EXP3A_ANCHOR_CONTRACT =
EXP3A_REFRESH_CONTRACT =
EXP3A_COMMON_SUPPORT_GATE =
EXP3B_STATE_VINTAGE_CONTRACT =
EXP3B_ACTION_SET_PARITY =
COMMON_REPLAY_GATE =
METRIC_CONTRACT =
FIGURE_SCHEMA =

LEGACY_SUPPORT_ABLATIONS_ACTIVE =
LLM_AUDIT_ROLE =
FINAL_TEST_ACCESS_COUNT =
PAPER_FULL_RUN =

FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =

REMAINING_BLOCKERS =
NEXT =
```

并说明：

- 哪些旧 Exp3 code 被复用；
- 哪些旧 headline 被降级；
- formal multi-action coverage 是否足够；
- ONE_SHOT invalid/infeasible recommendations 如何处理；
- lag variants 是否实现严格 action-set parity；
- 是否存在必须回 model 修正的问题。

---

# 36. 禁止项

1. 不重新训练 M1/M2/M3/M4。
2. 不重新设计 23-action library。
3. 不从头优化一套新的 recovery plan。
4. 不用不同 model quality 构造 baseline。
5. 不用当前 `J_t` 的机械最小性质冒充 Rolling/SYNC 的实证优势。
6. 不给 invalid one-shot action 人工赋无穷大 loss。
7. 不绕过 formal support/provenance gate 增加样本。
8. 不让 Exp3B action set 随 lag variant 变化。
9. 不让 lag variant 偷读 current S_t。
10. 不用 Test 选择 t0、lag、strata cutoff、case episode。
11. 不创造 Decision Churn / Sync Score / Freshness Value 等 composite score。
12. 不把 scenario action-response 写成 observed causal effect。
13. 不把 DeepSeek audit 当 model validation。
14. 不 commit / push。


# 37. Cross-experiment boundary lock

- Exp3A owns recommendation refresh/aging, not validity-at-issuance.
- Exp3B owns state-vintage synchronization, with current action set/information fixed.
- Exp4B owns current-output admissibility at issuance.
- Action-family composition in Exp3 is supplementary because Exp2B owns it as a representation-mechanism headline.
