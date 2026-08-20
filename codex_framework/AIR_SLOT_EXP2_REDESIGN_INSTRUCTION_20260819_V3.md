# AIR SLOT — Exp2 重构执行指令

## 0. 工作目录与写入边界

项目根目录：

`D:\research\air_slot\code\explore`

本任务只允许修改：

`D:\research\air_slot\code\explore\exp\exp2`

可以只读检查：

- `model/`
- `registries/`
- `configs/`
- `exp/common/`
- `exp/exp1/`
- 现有 tests / validation / reporting

未经额外授权，不修改上述目录。

不要 commit、不要 push、不要运行正式 Final Test、不要运行 `paper_full`。

---

# 1. Exp2 的科学定位

Exp2 只回答：

> **Why should cross-stage information sharing and state dependence take the particular representational form used in the framework?**

它不是：

- Exp1：“为什么需要跨阶段信息共享和状态依赖？”
- Exp3：“为什么必须按照 information → state → consequence → intervention → comparison 的流程？”
- Exp4：“全模型的一般性能、稳健性、跨数据环境表现如何？”

新版 Exp2 只包含两个 headline subexperiments：

1. **Exp2A — Representation of uncertainty and dependence**
2. **Exp2B — Representation of operational consequence**

固定逻辑：

```text
Exp2A:
POINT
    -> MARGINAL
    -> JOINT

Exp2B:
SCALAR / AGGREGATE
    -> 3-CHANNEL
    -> 7-COMPONENT HIERARCHY
```

不新增 `STATE_ONLY vs DUAL_PATH` headline experiment，除非后续有独立科学理由和公平 baseline；当前不做。

---

# 2. 论文逻辑对应

Exp2A 对应的方法主张：

- point state 会丢失 threshold/tail uncertainty；
- separate marginals 可以保留每个变量自己的 uncertainty，但不保留 unresolved quantities 之间的 dependence；
- formal model 必须让同一个 scenario identity 贯穿 state → consequence → action evaluation。

Exp2B 对应的方法主张：

- aggregate loss 太早聚合会丢失 action-relevant mechanism；
- broad cost categories 仍可能隐藏同一 channel 内的不同 operating mechanism；
- formal model 在 action response 前保留 3 channels / 7 components，使 action footprint 作用于具体 consequence components，再统一聚合。

禁止把“直接 state → action”作为 Exp2B baseline；那是 Exp3 的流程必要性实验。

---


# 2.1 Cross-experiment isolation lock

Exp2 的所有 headline variant 必须从同一个 **FULL / ADAPTIVE history-conditioned formal artifact** 向下派生。

因此：

```text
Exp2A changes representation of the same unresolved state.
Exp2B changes representation granularity of the same consequence basis.
```

Exp2 不允许同时改变：

- admissible history window；
- direct downstream information permissions；
- rolling refresh process；
- state vintage；
- action set；
- support/provenance gate。

对应边界：

- `CURRENT vs ADAPTIVE` 属于 Exp1B；
- `NO_DIRECT_REUSE vs FULL` 属于 Exp1A；
- `ONE_SHOT vs ROLLING`、`SYNC vs LAG` 属于 Exp3；
- observed-outcome benchmark / portability / runtime 属于 Exp4。

这样 Exp2 的结果才能解释为 **representation effect**，而不是 information quantity/process effect。

# 3. Preflight model-contract audit

开始重构 `exp/exp2` 前，只读检查最新版 `model/`。

若下面任何关键项不满足，停止正式实现并生成：

`EXP2_MODEL_CONTRACT_BLOCKED.md`

不得在 `exp/exp2` 中伪造缺失模型语义。

## 3.1 M1

确认：

- primitive stochastic outputs 与论文一致；
- total takeoff delay 是 samplewise derived；
- formal Joint representation 有稳定 scenario identity / scenario weight；
- scenario artifact 可只读复用；
- decision-time information boundary 已按最新版 model 正确实现；
- final-test artifact 未被访问。

## 3.2 M2 / consequence

确认最新版模型已经正式实现：

```text
Flight:
  F_continuity
  F_execution
  F_propagation

Passenger:
  P_time
  P_itinerary
  P_service

Resource:
  R_operating
```

共 3 channels / 7 components。

确认：

- continuity 公式是最新版；
- native consequence → CU → RMB/monetary interface 与论文一致；
- action transformations 使用最新版 component contract；
- A00 是 samplewise identity；
- 7-component consequence 可以作为 common replay evaluator 的完整 basis。

## 3.3 M3/M4

确认：

- 23 templates including A00；
- action instantiation / comparability 与 library 分离；
- action-response parameters / provenance 已冻结；
- common risk criterion `J(a)` 已正式可调用；
- formal comparison coverage/support 已冻结或至少 Development 可合法计算。

如果 authoritative ranking 仍被正式 coverage/support gate 阻断：

- 不绕过 gate；
- Development 可以输出 `SCENARIO_CONDITIONED / NON_AUTHORITATIVE` 结果；
- formal Test ranking 继续 BLOCKED。

---

# 4. 当前旧 Exp2 的处理策略

当前仓库旧 Exp2 已有：

- point collapse；
- lineage shuffle / corruption；
- consequence distortion；
- action-gap distortion；
- pairwise reversal；
- top1 disagreement；
- reference-objective selection penalty。

新版处理原则：

## 可复用

- frozen M1 scenario artifact reuse；
- immutable/deep-copy transformation；
- source hash / output hash audit；
- point-collapse machinery；
- scenario-lineage permutation machinery；
- common RNG infrastructure；
- common reference evaluator 的底层思想。

## 降级为 diagnostics / legacy

以下不能再做 headline：

- `ActionGapDistortion`
- `PairwiseRankingReversalRate`
- `ReferenceObjectiveSelectionPenalty`
- `NormalizedReferenceObjectiveSelectionPenalty`
- lineage-corruption grid 作为主实验

它们可以保留为 appendix / diagnostic，只要没有破坏兼容性。

## 必须新增/重构

- formal `POINT / MARGINAL / JOINT` protocol；
- CRPS / Brier / calibration parity output；
- multivariate dependence score；
- complete-reference `J_ref(a*)` internal diagnostic（secondary / non-independent evidence）；
- 3-channel / 1-scalar consequence coarsening；
- action-family composition reporting；
- episode-cluster bootstrap；
- TRE/JORS style figures。

---

# 5. Exp2A — POINT / MARGINAL / JOINT

## 5.1 科学问题

回答：

> Is preserving uncertainty sufficient, or must dependencies among unresolved operating quantities also be preserved for recovery decisions?

三个 variant 应从 **同一个正式 Joint M1 artifact** 派生。

禁止分别训练三个能力不同的模型后比较。

---

# 6. Exp2A-JOINT

正式模型输出，不做任何表示降级。

保留：

- original scenario ids；
- original scenario weights；
- original aligned target tuples；
- full downstream consequence/action chain。

记为：

`EXP2A_JOINT`

---

# 7. Exp2A-MARGINAL

## 7.1 目标

保留所有 target marginals **完全相同**，只破坏 cross-target scenario dependence。

## 7.2 principal construction

从同一个 Joint scenario artifact：

```text
(T_IB_s, D_OB_s, D_TX_s)
```

对 primitive target columns 分别做独立 permutation：

```text
T_IB_{pi1(s)}
D_OB_{pi2(s)}
D_TX_{pi3(s)}
```

要求：

- 每个 marginal empirical distribution 完全不变；
- scenario count 不变；
- scenario weights 处理必须与 model contract 一致；
- derived quantities（如 D_TO）必须在 permutation 后按新 tuple **重新 samplewise 派生**；
- 不允许继续沿用旧 aligned D_TO，否则会泄漏原 dependence；
- M1 frozen artifact 不得 mutation；
- transformation output 带 source hash / seed / permutation audit。

principal condition：

`q = 1.0` full independent lineage shuffle。

可选 appendix sensitivity：

```text
q = 0.25, 0.50, 0.75, 1.00
```

但 q-grid 不作为 main headline，不利用 Test 选择“最好看的 q”。

## 7.3 hard parity assertions

对于每个 primitive target：

- sorted sample values identical；
- weighted marginal CDF identical within tolerance；
- marginal quantiles identical；
- CRPS identical within numerical tolerance；
- marginal calibration identical within tolerance。

如果 Marginal 与 Joint 的 marginal forecast quality 明显不一致：

**实验构造失败，不能解释为 dependence effect。**

---

# 8. Exp2A-POINT

## 8.1 目标

去掉 distributional uncertainty，同时尽量保留一个公平、物理一致的代表 operating state。

## 8.2 principal point rule

优先复用/适配当前已有的：

`WEIGHTED_JOINT_SCENARIO_MEDOID`

即从 Joint scenario artifact 中选择一个代表性 coherent scenario，而不是独立拼接三个 component means。

原因：

- 保证 point baseline 本身是一个合法 joint operating realization；
- 不额外惩罚 point model 的“物理不一致”；
- 让 Point vs Marginal 主要检验 uncertainty，而不是 coherence bug。

将该 coherent point scenario 复制为 downstream 所需的 degenerate scenario representation：

```text
same representative tuple repeated / represented with unit probability
```

权重归一。

如果最新版 model 已有正式 point-query semantics（如 joint conditional median/medoid），优先使用 model 正式接口。

### sensitivity only

可以在 Appendix 增加 marginal median vector point forecast，但不能在 Test 后根据结果选择 principal point rule。

---

# 9. Exp2A 的评价指标

指标必须同时满足：

1. 领域已有认知基础；
2. 直接回答实验问题；
3. 能形成清楚、非冗余的数据；
4. 明确区分 **外部可检验 representation evidence** 与 **内部 decision-consistency diagnostic**。

## 9.1 Marginal probabilistic quality

### CRPS

对每个正式 primitive stochastic target 分别计算。

用途：

- 证明 `MARGINAL` 与 `JOINT` marginal predictive quality 相同；
- 检查正式 Joint M1 的概率预测质量。

不创造 joint-CRPS。

## 9.2 Operational event probability

### Brier score

使用 model 已冻结的 principal delay event。

如果最新版 scientific config 仍将：

`D_TO > 30 min`

作为 principal warning / operational event，则主文保留该 event。

其他 15/30/60 thresholds 放 appendix。

不要为了“行业更熟悉 15min”擅自修改已冻结 scientific event。

## 9.3 Dependence quality

### Variogram Score

实现标准 proper multivariate Variogram Score。

principal：

`VS_p`，p 必须在 Development 前冻结。

推荐优先检查文献常用 `p = 0.5`；如果 model/项目已有正式设置，则服从已有设置。

不要自行创造 dependence index。

可选 appendix：

- Energy Score

但主文不要同时堆多个 multivariate score。

## 9.4 Decision relevance — headline descriptive evidence

三个 representation 分别选出：

```text
a*_POINT
a*_MARGINAL
a*_JOINT
```

主文用于回答 representation 是否会改变 downstream decision：

- selected Top-1 action；
- Top-1 agreement with JOINT；
- equivalently, Top-1 disagreement rate；
- selected action-family composition；
- pre-registered operational strata 下的 disagreement / composition change。

这里 **JOINT 不是 ground truth action**。Agreement 只表示“粗化 representation 是否改变了正式完整 representation 下的 recommendation”，不得称为 action accuracy。

Top-k / Kendall tau 可 Appendix。

## 9.5 Common-reference `J_ref` — internal diagnostic only

允许将三个 selected actions 放回：

**同一个 full JOINT + full 7-component + same frozen action-contract reference evaluator**

计算：

```text
J_ref(a*_POINT)
J_ref(a*_MARGINAL)
J_ref(a*_JOINT)
```

但必须明确：

> This is an internal decision-consistency diagnostic under the complete frozen reference representation, not independent empirical evidence that JOINT is superior.

原因：

- JOINT 本身就是在 complete representation 下选择动作；
- 再用同一个 complete representation 的 `J_ref` 评价，可能产生部分构造性优势；
- 因此不能把 `J_ref(a*_JOINT)` 较低写成独立实证验证或真实 action effectiveness。

命名建议：

```text
complete-reference model-implied residual risk (diagnostic)
```

不要继续用 `common-replay residual risk` 作为 Exp2A headline，也不要使用 `ReferenceObjectiveSelectionPenalty`。

若未来项目获得独立、可识别的 action-outcome/counterfactual evaluation contract，可另行升级；当前 public-data/scenario-response 设定下不做这种 claim。

# 10. Exp2A 的预注册分层

不要 Test 后寻找“最显著场景”。

使用项目已有业务变量：

1. turnaround margin / tightness；
2. time to successor scheduled departure；
3. downstream exposure。

cutoff 规则：

- 优先使用 model/文献已有 operational thresholds；
- 否则使用 Train/Development 冻结 quantiles；
- Test 不参与 cutoff 决策。

目的：

检验 Joint representation 的价值是否集中在：

- tight turnaround；
- near execution deadline；
- high downstream exposure。

这是 heterogeneity analysis，不新造“complexity score”。

---

# 11. Exp2A 预期科学判别模式

不要求 Joint 在所有指标上全面胜出。

最有说服力的数据结构是：

```text
CRPS(MARGINAL) ≈ CRPS(JOINT)
Brier(MARGINAL) ≈ Brier(JOINT)  [视 derived event 是否受 dependence 影响，不强制]
VS(MARGINAL) > VS(JOINT)
Top-1(MARGINAL) differs from Top-1(JOINT) on a non-trivial subset
and/or action-family composition changes in operationally interpretable strata
```

`J_ref` 若同时显示差异，只能作为 complete-reference model-implied diagnostic 补充，不属于独立证据链。

核心 claim 只有数据支持时才能写：

> Marginal predictive accuracy does not guarantee preservation of a decision-relevant joint operating-state representation.

不能写：

> JOINT is empirically proven to select better actions

除非存在独立于 formal selection objective 的合法 action-outcome evaluation。

Point vs Marginal 主要回答 uncertainty；
Marginal vs Joint 主要回答 dependence。

# 12. Exp2B — SCALAR / 3-CHANNEL / 7-COMPONENT

## 12.1 科学问题

回答：

> Does aggregate recovery cost suffice, or must the mechanisms generating that cost remain identifiable until action evaluation?

三个 variant 必须从同一个 formal 7-component consequence/action contract **向下 coarsen**。

禁止重新设计三个不同 quality 的 cost models。

---

# 13. Exp2B-7COMP

正式论文模型：

```text
F_continuity
F_execution
F_propagation
P_time
P_itinerary
P_service
R_operating
```

action response 在 component footprint 上作用，然后 aggregate。

记为：

`EXP2B_7_COMPONENT`

---

# 14. Exp2B-3CHANNEL

## 14.1 representation

聚合成：

```text
Flight
Passenger
Resource
```

即：

```text
L_F = sum flight components
L_P = sum passenger components
L_R = resource component
```

coarse representation 在 action evaluation 时不能再读取 7-component composition。

## 14.2 strong/fair channel-level action contract

不要手工设置“某动作减少 Flight 30%”。

从 formal 7-component action model 在 **Train only** 上生成 channel-level coarse response approximation。

推荐方法：

### Train-only moment-matched / response-averaged coarsening

对每个 action `a`、每个 channel `g`：

1. 使用正式 7-component action transform 在 Train scenario 上计算：
   - baseline channel consequence；
   - action-conditioned channel consequence。
2. 从 Train 估计一个冻结的 channel-level response mapping/parameter，使粗粒度模型尽量匹配 formal model 的 **平均 channel response**。
3. Development 只检查稳定性/冻结，不用 Test 调参。
4. Test 时 B2 只能看到 channel totals + frozen channel-level action response，不得访问 within-channel 7-component composition。

这样 B2 是对 formal model 的强 coarse approximation，不是 strawman。

如果最新版 model 已提供正式 coarsening API，优先使用。

---

# 15. Exp2B-SCALAR

进一步把 3 channels 聚合成 total recovery consequence：

```text
L_total = L_F + L_P + L_R
```

同样从 Train-only formal response 中拟合/矩匹配一个 action-level scalar coarse response。

Test 时只允许看到：

- total baseline loss / consequence；
- frozen scalar action response；
- minimal actionability/execution facts。

不得通过 hidden field 读取 channel/component composition。

记为：

`EXP2B_SCALAR`

---

# 16. Exp2B 公平性要求

三个 variant：

- same episodes；
- same decision-time cutoff；
- same M1 FULL/ADAPTIVE JOINT state；
- same direct-current-information permissions；
- same 23-action library；
- same action availability / execution opportunity；
- same support/provenance gate；
- same monetary system / risk criterion；
- only consequence representation granularity differs。

不允许：

- SCALAR 少几个动作；
- 3CHANNEL 关闭 passenger actions；
- 7COMP 获得更多 actionability 信息；
- 为 coarse baseline 选择更差的 response parameters。

如果 representation 导致无法表达某个 action footprint：

必须通过 Train-frozen coarsening contract表达；
不能简单删动作，除非 method contract 本身明确无法实例化。

---

# 17. Exp2B 的 evaluation hierarchy

三个 representation 各自选择：

```text
a*_SCALAR
a*_3CHANNEL
a*_7COMP
```

## 17.1 Headline evidence: representation-induced decision difference

主文首先比较：

- selected Top-1 action；
- Top-1 agreement with 7-component representation；
- action-family composition；
- matched-case mechanism differences。

这里 7-component representation 是 **complete formal representation reference**，不是 observed ground-truth action。

核心问题是：

> Does earlier aggregation erase mechanism distinctions that materially change the intervention selected by the same fixed decision technology?

## 17.2 Complete-reference `J_ref`: internal diagnostic only

可以把三个 selected actions 放回：

**full JOINT state + formal 7-component consequence + formal action-response + formal J evaluator**

得到：

```text
J_ref(a*_SCALAR)
J_ref(a*_3CHANNEL)
J_ref(a*_7COMP)
```

其公平性规则仍是：

> different representation chooses; same complete evaluator judges.

但解释必须降级为：

> complete-reference model-implied decision-consistency diagnostic.

不能把：

```text
J_ref(a*_7COMP) <= J_ref(a*_SCALAR)
```

单独解释为 7-component representation 的独立 empirical superiority，因为 7-component action 本身由相同 complete representation/objective 选出，存在 self-reference。

该 diagnostic 可以：

- 检查 coarse representation 是否导致与 complete model objective 明显冲突的选择；
- 支撑 matched-case explanation；
- 进入 Appendix / secondary table；

但不得成为 Exp2B 唯一或首要“性能胜负”证据。

# 18. Exp2B 主指标 / 业务输出

## 18.1 headline decision-relevance output

- Top-1 selected action；
- Top-1 agreement with 7-component representation；
- Top-1 disagreement proportion；
- paired episode-cluster 95% CI。

不要把 7-component 称为 ground truth action；agreement/disagreement 只是 representation sensitivity。

## 18.2 industry/managerial output

不要新造 score。

直接输出：

### selected action family composition

按现有 action families 汇总，例如：

- timing / timing-passenger；
- capacity coordination；
- passenger recovery/service；
- ground recovery；
- aircraft recovery；
- crew recovery；
- network/cancellation；
- A00/no additional action。

输出每种 representation 下 selected actions 的 family share。

这用于回答：

> representation granularity 是否改变 recovery strategy composition？

### channel consequence reporting

必要时报告 model 已有的：

- Flight consequence；
- Passenger consequence；
- Resource consequence；

不要把不同原生物理单位强行相加成新“operational score”。

## 18.3 secondary internal diagnostic

允许报告：

```text
complete-reference model-implied J_ref(a*)
```

但必须在列名、caption、README 中显式标记：

```text
INTERNAL_DIAGNOSTIC
NOT_INDEPENDENT_ACTION_EFFECT_EVIDENCE
```

主文若篇幅紧张，`J_ref` 优先进入 Appendix。

# 19. Exp2B matched-case protocol

为了产生可解释而非纯平均数的结果，预注册 matched-case analysis。

候选 episode pairs 需要满足：

1. disruption severity similar；
2. aggregate recovery consequence similar；
3. underlying dominant mechanism different。

示例 Development-frozen matching rule：

```text
|D_TO_i - D_TO_j| <= 5 minutes
relative difference in aggregate baseline RMB loss <= 10%
```

5 min / 10% 只是推荐起点。

最终 cutoff 必须：

- 在 Development 冻结；
- 在 Test 前固定；
- 不能看 Test 后调整。

dominant mechanism 直接基于 formal 7-component decomposition，不创建新 index。

matched cases 用于 qualitative/illustrative figure，不取代 aggregate statistics。

---

# 20. Exp2B 预期判别模式

不要求 7-component 在每个 episode 都选不同动作。

最有解释力的数据模式是：

```text
aggregate delay/cost nearly similar
but mechanism composition differs
=> selected action differs under fine representation
=> action-family choice follows the exposed mechanism difference
```

matched-case 中可以进一步报告 complete-reference `J_ref`，但只能作为 model-implied consistency diagnostic。

只有数据支持时才能写：

> Similar aggregate disruption cost can imply different recovery interventions when the underlying consequence mechanisms differ.

不能仅凭 `J_ref(a*_7COMP)` 更低写：

> the 7-component representation is empirically more effective.

当前实验没有独立识别真实 counterfactual action effectiveness。

# 21. 统计协议

## Statistical unit

episode 为 cluster。

同一 episode 的多个 5-minute nodes 不当作独立 observations。

## Main uncertainty

paired episode-cluster bootstrap 95% CI。

建议：

- 2000 replicates；
- fixed bootstrap seed；
- same resampled episode set across compared variants。

## Report

优先：

- estimate；
- paired difference；
- 95% CI。

不把 significance stars 作为主表达。

---

# 22. Figures — TRE/JORS 风格

可以借 `ChenLiu-1996/figures4papers` 的：

- multi-panel hierarchy；
- consistent semantic colors；
- direct labels；
- compact legends；
- vector export；
- composition bars。

不要照搬：

- AI leaderboard 式十几根 bars；
- radar；
- 大字号；
- baseline 红 vs proposed 蓝 的强对抗审美；
- 人为收紧 y-axis；
- 只展示百分比提升不展示原始量和 CI。

---

# 23. Main Figure 推荐 2×2

## Panel A — Dependence representation quality

POINT / MARGINAL / JOINT：

- principal `Variogram Score`
- dot + 95% CI

注意：
POINT 若 VS 定义上可计算则展示；
否则重点比较 MARGINAL vs JOINT，并在 caption 说明。

## Panel B — State representation and selected action

POINT / MARGINAL / JOINT：

- Top-1 agreement with JOINT，或等价的 disagreement proportion；
- proportion + episode-cluster 95% CI。

caption 明确：这是 decision sensitivity，不是 action accuracy。

## Panel C — Consequence granularity and selected action

SCALAR / 3-CHANNEL / 7-COMPONENT：

- Top-1 agreement with 7-component representation，或 disagreement proportion；
- proportion + 95% CI。

## Panel D — Recovery strategy composition

SCALAR / 3-CHANNEL / 7-COMPONENT：

- 100% stacked selected-action family share。

`J_ref` 不再占主图 panel；作为 internal diagnostic 放 secondary table / Appendix，除非后续存在独立 action-outcome evaluation。

风格：

- Joint / 7-component：一个低饱和强调色；
- intermediate representations：深灰；
- point/scalar：浅灰；
- 不使用危险红；
- 白底；
- 去除 top/right spines；
- vector PDF + 300dpi PNG。

# 24. Main Table

输出 LaTeX-friendly / CSV source。

推荐：

| Subexperiment | Variant | CRPS | Variogram Score | Brier | Top-1 agreement | Action-family share/source | N episodes |
|---|---|---:|---:|---:|---:|---|---:|

规则：

- 2A 填 CRPS / VS / Brier / Top1；
- 2B 的 CRPS / VS / Brier 填 `—`，不要伪造意义；
- action-family composition 可用独立 source table，不必把所有 family 塞入主表；
- 每个 estimate 配 95% CI；
- 主文不塞一堆 p-value。

另生成 secondary diagnostic table：

| Subexperiment | Variant | Complete-reference model-implied `J_ref` | 95% CI | Diagnostic status |
|---|---|---:|---:|---|

其中 `Diagnostic status` 固定标记：

`INTERNAL / NOT INDEPENDENT ACTION-EFFECT EVIDENCE`。

# 25. Appendix outputs

允许：

## Exp2A
- CRPS by all primitive targets/horizons；
- Brier for 15/30/60；
- calibration curves；
- Energy Score；
- q-corruption sensitivity；
- Top-k / Kendall tau；
- subgroup tables。

## Exp2B
- channel-level consequences；
- detailed action-family table；
- pairwise ranking reversal；
- full matched-case appendix；
- coarse-response Train fitting diagnostics。

旧：

- ActionGapDistortion；
- PairwiseRankingReversalRate；
- ReferenceObjectiveSelectionPenalty

如果保留，只放 diagnostics/appendix，不作为 headline。

---

# 26. 建议的新代码结构

在现有 `exp/exp2` 基础上审查后实现，避免机械创建无用文件。

推荐职责：

```text
exp/exp2/
├── __init__.py
├── README.md
├── protocol.py
├── representations.py       # point / marginal / joint
├── consequence_coarsening.py
├── common_replay.py
├── metrics.py
├── statistics.py
├── stratification.py
├── matched_cases.py
├── reporting.py
├── figures.py
├── audit.py
├── runner.py
└── tests/
```

关键原则：

- representation transform 不拥有 model logic；
- consequence coarsening 只用 Train-frozen formal outputs/parameters；
- replay 只做 evaluation，不回流 decision construction；
- metrics 不重定义 scientific quantities；
- figures 只消费 frozen result tables；
- old public imports 如被仓库其他模块依赖，要保留 compatibility shims。

---

# 27. Active variant registry

新版 headline variants：

```text
EXP2A_POINT
EXP2A_MARGINAL
EXP2A_JOINT

EXP2B_SCALAR
EXP2B_3CHANNEL
EXP2B_7COMP
```

旧 aliases 如必须兼容，可以保留，但：

```text
point_flight
point_full
distributional_flight
distributional_full
shuffled_lineage
P-F
P-C
D-F
D-C
LINEAGE_CORRUPTION
```

不得继续作为新主论文 protocol 的正式命名。

---

# 28. 审计产物

每次 smoke / Development run 至少输出：

1. `exp2_protocol_manifest.json`
2. `exp2_model_contract_snapshot.json`
3. `exp2_variant_manifest.json`
4. `exp2_representation_audit.json`
5. `exp2_marginal_parity_audit.json`
6. `exp2_consequence_coarsening_manifest.json`
7. `exp2_common_replay_manifest.json`
8. `exp2_split_audit.json`
9. `exp2_leakage_audit.json`
10. `exp2_metrics.csv`
11. `exp2_summary.json`
12. action-family composition source table
13. figure source table(s)

manifest 记录：

- git SHA；
- scientific config hash；
- model/registry hashes；
- source M1 scenario artifact hash；
- seeds；
- permutation seeds；
- scenario count；
- split；
- coarsening Train population/hash；
- final-test access count；
- code/version hash。

---

# 29. 必须测试

## 2A representation tests

- POINT 来源于同一 frozen JOINT artifact；
- JOINT source artifact 不 mutation；
- MARGINAL 每个 primitive marginal 精确保存；
- D_TO 等 derived quantities 在 permutation 后重新派生；
- q=0 exactly equals JOINT；
- q=1 deterministic under seed；
- no future/Test info in representation construction。

## 2A metric tests

- CRPS known toy cases；
- Brier known toy cases；
- Variogram Score toy/reference calculation；
- common-replay evaluator 对同一 selected action给出同值；
- episode-cluster bootstrap reproducible。

## 2B coarsening tests

- 3-channel sums formal components correctly；
- scalar sums channels correctly；
- Train-only response coarsening；
- no Test rows in coarse-parameter fit；
- 3-channel/scalar evaluator cannot access hidden fine components；
- same action set / feasibility / opportunity across B variants；
- A00 identity preserved。

## replay / leakage

- realized outcomes只用于 evaluation；
- reference evaluator 不回流 variant action selection；
- common replay uses identical full basis for all selected actions；
- final-test count remains zero。

---

# 30. Final-Test gate

本轮只运行：

- unit tests；
- synthetic/small smoke；
- Train/Calibration/Development dry run（若项目规则允许）。

结束必须：

```text
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
```

只有以下全部 PASS 后才允许未来授权 Final Test：

- model contract frozen；
- Exp2 protocol frozen；
- Point/Marginal/Joint transforms frozen；
- marginal parity PASS；
- consequence coarsening frozen；
- common replay PASS；
- metrics frozen；
- figure/table schema frozen；
- leakage audit PASS；
- human authorization。

---

# 31. 完成状态输出

执行完成后必须报告：

```text
AIR_SLOT_EXP2_REDESIGN

MODEL_CONTRACT_GATE =
EXP2A_REPRESENTATION_CONTRACT =
EXP2A_MARGINAL_PARITY =
EXP2B_COARSENING_CONTRACT =
COMMON_REFERENCE_DIAGNOSTIC_GATE =
STATISTICAL_PROTOCOL =
FIGURE_SCHEMA =

LEGACY_PROTOCOL_ACTIVE =
FINAL_TEST_ACCESS_COUNT =
PAPER_FULL_RUN =

FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =

REMAINING_BLOCKERS =
NEXT =
```

并说明：

- 当前旧 point-collapse 是否复用；
- lineage shuffle 如何重构成 MARGINAL；
- 哪些旧 metrics 降级为 diagnostic；
- 2B coarse action response 如何从 Train formal model 冻结；
- 是否有任何需要修改 model 才能解决的问题。

---

# 32. 禁止项

1. 不分别训练一个弱 point model、弱 marginal model 来制造差距。
2. 不改变 MARGINAL 的 primitive marginal distributions。
3. 不用 Test 选择 corruption intensity。
4. 不把 independent marginals 误称为“错误预测模型”；它是 dependence-ablation representation。
5. 不把 point baseline 故意构造成不物理一致的 state。
6. 不把“直接决策/跳过 consequence”塞进 Exp2；留给 Exp3。
7. 不为 SCALAR / 3CHANNEL 删除动作来制造差距。
8. 不用 Test 拟合 coarse response。
9. 不让 coarse variants 偷看 7-component hidden composition。
10. 不把 action-response scenario model 写成真实 causal treatment effect。
11. 不创造新的奇怪 information/decomposition scores。
12. 不继续使用 ActionGapDistortion / ReferenceObjectiveSelectionPenalty 作为 headline。
13. 不把 complete-reference `J_ref` 当成独立 empirical proof；它只能是 internal model-consistency diagnostic。
14. 不通过 bypass support/provenance gate 获得更多 ranking samples。
15. 不修改 model 科学语义来适配实验；有 mismatch 就 BLOCK。
16. 不 commit / push。


# 33. Cross-experiment boundary lock

- Exp2A owns uncertainty/dependence representation only.
- Exp2B owns consequence representation granularity only.
- No Exp2 variant may alter history length, direct-information reuse, refresh cadence, state vintage, action availability, or support gate.
- Action-family composition is headline mechanism evidence in Exp2B; other experiments may report it only descriptively/secondarily.
