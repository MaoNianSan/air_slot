# AIR SLOT — Exp4 全面重构执行指令（最终 Adequacy / Robustness 版本）

## 0. 项目目录与写入边界

项目根目录：

`D:\research\air_slot\code\explore`

本任务只允许修改：

`D:\research\air_slot\code\explore\exp\exp4`

允许只读检查：

- `model/`
- `registries/`
- `configs/`
- `data1/`
- `data2/`
- `exp/common/`
- `exp/exp1/`
- `exp/exp2/`
- `exp/exp3/`
- `docs/results/`
- tests / validation / reporting

未经额外授权：

- 不修改 `model/`
- 不修改 Exp1–Exp3
- 不 commit
- 不 push
- 不运行正式 Final Test
- 不运行 `paper_full`

如果最新版 `model/` 与本文实验合同冲突，Exp4 必须 BLOCK，并生成明确的 mismatch report；不得在 Exp4 中偷偷补模型逻辑。

---

# 1. Exp4 的论文定位

最新版论文的研究对象是：

```text
evolving decision-time information
 -> history-conditioned operating state
 -> state-consistent consequence
 -> current recovery action
 -> supported comparison
```

Exp1–Exp3 已分别承担：

```text
Exp1: Why is cross-stage information/state dependence needed?
Exp2: In what representation should information/state be retained?
Exp3: How should the fixed decision technology operate?
```

因此 Exp4 不再承担新的 methodological novelty claim。

Exp4 的唯一任务是：

> **Is the complete frozen decision chain empirically adequate, operationally admissible, portable across evidence environments, and computationally usable?**

最终冻结为四个子实验：

```text
Exp4A — Predictive adequacy across the operational lead-time window
Exp4B — Decision-output validity and auxiliary operational plausibility
Exp4C — Cross-data robustness and support portability
Exp4D — End-to-end computational adequacy
```

核心证据结构：

```text
observed outcomes
+ hard operational/evidential rules
+ auxiliary external LLM audit
+ second evidence environment
+ measured wall-clock runtime
```

新版 Exp4 主实验 **不使用内部 J 作为最终性能真值**。

`J` 可以继续存在于 Exp1–Exp3 的 controlled methodology comparisons 或 Appendix diagnostics，但 Exp4 不得用：

```text
framework selects with J
 -> framework evaluated with same J
 -> conclude framework is empirically effective
```

这种 self-confirming loop。

---


# 1.1 Cross-experiment isolation lock

Exp4 evaluates the **complete frozen chain**. It does not re-open the methodological ablations in Exp1--Exp3.

## Exp4A vs Exp1B

Exp1B owns the controlled question:

```text
same state-aware architecture
CURRENT history vs ADAPTIVE history
```

Exp4A owns the adequacy benchmark:

```text
Historical
LIGHTGBM_FAST
Random Forest
STATE_AWARE_FULL
across 0--480 min operational lead time
```

Therefore：

- Exp4A does not call FAST vs FULL a pure "history effect"；
- Exp1B does not reproduce the full 0--480 multi-model benchmark；
- `CURRENT` in Exp1B must not silently equal `LIGHTGBM_FAST`.

## Exp4B vs Exp3A

Exp4B asks：

> Is a recommendation operationally/evidentially admissible **when issued**?

Exp3A asks：

> Does an initially valid recommendation remain executable/comparable **as it ages without refresh**?

Denominators, labels, figures and claims must preserve this distinction.

## Exp4B action composition

Overall action-family composition is descriptive system characterization only.

Because Exp2B owns action-family composition as representation-mechanism evidence, Exp4B should place overall composition in a secondary table/Appendix unless it is needed to characterize the evaluated cohort.

# 2. Preflight — 最新 Model Contract 审计

执行任何 Exp4 重构前，先对最新版 `model/` 进行只读 contract audit。

若任何 critical contract 不满足，输出：

`EXP4_MODEL_CONTRACT_BLOCKED.md`

然后停止正式实现。

## 2.1 M1

确认：

- formal state-aware path；
- FAST / LightGBM path；
- primitive stochastic targets；
- derived total takeoff delay；
- rolling interval；
- decision-time feature admissibility；
- scenario/distribution output；
- Train/Calibration/Development/Test 时间切分；
- episode-level split；
- final target/outcome timestamps。

确认：

\[
D^{+,TO}_{s}
=
D^{+,OB}_{s}
+
D^{+,TX}_{s}
\]

仍是 samplewise derived quantity。

## 2.2 Lead-time observability

确认可以在每个合法 historical decision node 定义：

```text
prediction lead time = time remaining to the target operational event
```

Lead time 不是正式 M1 horizon `T={0,15,60}` 的替代。

必须区分：

```text
forecast horizon tau
vs
evaluation lead time ell
```

如果目标 event 的 anchor 在最新版 model 已重新定义，服从 model 正式定义。

## 2.3 Action / support / recommendation

确认最新版 model 能明确识别：

- formal comparison lane；
- baseline-only formal state；
- conditional/scenario-only lane；
- excluded/unsupported/abstain；
- structural prerequisite；
- execution opportunity；
- evidence/provenance support；
- current factual state；
- decision-time information cutoff；
- selected action family；
- action id。

## 2.4 Data1/Data2 semantic mapping

确认 Data1 和 Data2：

- target semantics；
- timing anchors；
- lead-time semantics；
- evidence availability；
- input semantic mapping；

哪些是：

```text
SEMANTICALLY_EQUIVALENT
DEGRADED_BUT_VALID
UNSUPPORTED
```

不得使用 silent proxy。

不得为了扩大 Data1 cohort：

```text
schedule_like
turnaround_like
proxy_as_schedule
```

等语义重定义。

## 2.5 LLM audit

只读检查现有 Exp3 DeepSeek V2 audit：

- prompt/schema；
- input state；
- output classes；
- pilot validation；
- repetition logic；
- hash/provenance；
- no model feedback。

Exp4 可以复用其 scientific audit contract，但：

- 不修改 Exp3；
- 不让 LLM 输出回流 model；
- 不把 LLM judgement 当 ground truth。

---

# 3. 旧 Exp4 的处理原则

当前旧 Exp4 包含：

```text
hidden size 16/32
roll 5/10
M2 low/base/high
M3 low/base/high
lambda
alpha
MC 250/500/1000/2000
operational strata
Data1 portability
latency
```

新版处理：

## 保留/升级

- Data1 portability semantic gates；
- support-transition logic；
- latency percentile code；
- end-to-end deployment measurement infrastructure；
- any reusable bootstrapping/statistics utilities；
- provenance/manifests。

## 降级 Appendix

- hidden size sensitivity；
- roll 5/10 sensitivity；
- lambda/alpha grid；
- MC scenario count grid；
- valuation sensitivity；
- response-parameter sensitivity。

## 删除 headline 身份

这些 sensitivity 不再定义 4.4 主故事。

旧 runner 中：

```text
RISK_POLICY_SENSITIVITY
NORMATIVE_VALUATION_SENSITIVITY
SCENARIO_RESPONSE_SENSITIVITY
ROLL_SENSITIVITY
MONTE_CARLO_CONVERGENCE
```

改为：

`APPENDIX_DIAGNOSTIC`

除非外部代码依赖，不得继续作为 principal Exp4 variants。

---

# 4. Exp4A — Predictive Adequacy

## 4.1 科学问题

回答：

> Does the operating-state prediction entering the decision chain remain sufficiently accurate and probabilistically informative across the practical decision window?

它是 Exp4 中证据最硬的一层，因为评价使用真实 observed outcomes。

---

# 5. Exp4A Lead-time grid

Principal grid：

\[
\ell \in
\{0,30,60,120,180,240,300,360,420,480\}\ {\rm min}.
\]

定义：

> time remaining from the historical decision node to the formally defined target operational event.

注意：

```text
ell = evaluation lead time
tau = model forecast horizon
```

二者不得混淆。

不要修改 model 的正式：

```text
forecast_horizons_minutes = [0, 15, 60]
```

只是从滚动节点中按 `ell` 形成 performance cohort。

允许 tolerance matching，例如：

```text
lead_time bin ell ± 2.5 min
```

前提是原始 node grid 为 5 min。

如果实际 node grid 正好命中 anchor，则优先 exact match。

所有 binning 规则 Development 前冻结。

---

# 6. Exp4A Principal target

主文：

\[
\boxed{D^{+,TO}}
\]

即 successor total takeoff delay。

理由：

- 对 AOCC/airline recovery 最容易解释；
- 直接单位 min；
- 是 successor departure/movement consequence 的核心 state output；
- 由 formal joint primitive samples samplewise 得到。

Appendix：

- predecessor A00 in-block time/error；
- successor off-block delay；
- successor excess taxi delay。

不得只展示 derived total target 而从不审计 primitive targets；primitive 结果至少进 Appendix table。

---

# 7. Exp4A Benchmarks

主文只比较：

```text
B0 HISTORICAL
B1 LIGHTGBM_FAST
B2 RANDOM_FOREST
FULL STATE_AWARE
```

不要再加入：

- LSTM
- Transformer
- TCN
- MLP
- SVR
- XGBoost
- 其他大量 ML methods

论文不是 forecasting-architecture benchmark paper。

---

# 8. HISTORICAL baseline

Historical baseline 必须 Train-only。

优先原则：

1. 使用 airline/airport/time-of-day 等正式可在 decision time 已知的低频 operational descriptors；
2. 不使用 dynamic day-of-operation evidence；
3. 使用 empirical historical distribution，而不是只给一个 arbitrary zero-delay baseline；
4. fallback hierarchy 必须冻结；
5. Calibration/Test 不参与估计。

Data2 可采用正式支持的 conditioning，例如：

```text
origin airport
× carrier (if formally available)
× local time-of-day bucket
× optional weekday/weekend
```

但必须设置 minimum support。

推荐：

```text
min_group_n >= 50
```

不足时逐级 fallback：

```text
airport × time-of-day
 -> airport
 -> global
```

最终精确 hierarchy 以 model/data schema 审计为准。

Historical point forecast：

```text
conditional median
```

Historical probabilistic forecast：

```text
empirical conditional distribution
```

因此可合法计算 MAE 和 CRPS。

禁止使用未来 Test empirical distribution。

---

# 9. LIGHTGBM_FAST baseline

优先直接复用正式 M1 FAST path。

必须：

- 同 target；
- 同 decision-time feature contract；
- 同 split；
- 同 calibration discipline；
- 同 node/episode cohort。

如果正式 FAST path 已是 distributional LightGBM/Hazard/Hurdle，则直接使用其 distribution output。

不另外训练一个更弱的 LightGBM。

---

# 10. RANDOM_FOREST baseline

使用成熟 tabular nonlinear ensemble baseline。

Point prediction：

```text
RandomForestRegressor / project-approved equivalent
```

如果项目环境已经有合法 Quantile Random Forest / empirical tree-distribution interface：

- 可输出 probabilistic forecast；
- 计算 CRPS。

如果没有：

- RF 只参与 MAE/RMSE point benchmark；
- CRPS cell 显示 `—`；
- 不为了凑 CRPS 自创未经验证的 pseudo-distribution。

不要增加额外 deep model。

Hyperparameters：

- 只在 Train/Development 调整；
- 使用一个小的、预先定义的 grid；
- 不访问 Final Test；
- 不为了 beat Full 做大规模 AutoML。

建议初始候选：

```yaml
n_estimators: [300, 500]
max_depth: [None, 12, 20]
min_samples_leaf: [1, 5, 10]
max_features: ["sqrt", 0.5, 1.0]
```

Development 后冻结。

---

# 11. STATE_AWARE Full

直接复用正式 M1 state-aware path。

不得为了 Exp4 重新训练一个不同版本。

必须记录：

- model hash；
- hidden size；
- calibration version；
- feature contract；
- training split；
- scenario count；
- model path。

---

# 12. Exp4A 公平性

B1/B2/FULL 主比较必须共享：

```text
same target
same decision-time cutoff
same admissible features available to their architecture
same training/calibration/test dates
same episode split
same lead-time cohorts
same observed outcome definition
same missing-data cohort rule
```

尤其：

- Full 不得看 baseline 看不到的 future fields；
- baseline 不能因为 architecture simple 而被剥夺本来合法可用的 current static information；
- RF/LGBM 不得随机 train-test split；
- snapshot weight不能导致长 episode 过度贡献。

如果同一 episode 有多个 lead-time nodes，统计 cluster 仍是 episode。

---

# 13. Exp4A 指标

## Headline 1 — MAE

\[
MAE(\ell)
=
N_\ell^{-1}
\sum_i
|\hat D^{TO}_{i,\ell}
-
D^{TO,obs}_i|.
\]

单位：

```text
minutes
```

主图第一指标。

优点：

- airline/operations reader 直接理解；
- 不依赖新 metric；
- 便于 0–480 min trend 展示。

## Headline 2 — CRPS

对提供 predictive distribution 的方法：

\[
CRPS(\ell).
\]

主图第二指标。

用途：

- distributional quality；
- calibration + sharpness overall；
- 与全文 probabilistic-state representation 一致。

## Secondary

Appendix / table：

```text
RMSE
Brier score for frozen principal delay event
calibration/reliability
90% prediction interval coverage
```

不得正文同时塞 8–10 个预测指标。

---

# 14. Exp4A 统计

- unit of clustering = episode/flight chain；
- paired episode-cluster bootstrap；
- 2000 replicates；
- 95% CI；
- same bootstrap resample across methods per lead time；
- fixed seed；
- no p-value star grid。

必须输出每个 lead-time/method：

```text
N episodes
point estimate
95% CI
```

---

# 15. Exp4A 结果解释边界

允许：

> State-aware prediction becomes more/less advantageous as operational evidence accumulates.

不允许：

> Better MAE proves better recovery actions.

特别审计：

如果 Full 在 360–480 min 就出现异常巨大优势，优先触发：

```text
LEAKAGE_AUDIT_REQUIRED
```

而不是直接当好结果。

---

# 16. Exp4B — Decision-output Validity

## 16.1 科学问题

回答：

> When the complete chain emits a formal recovery recommendation, is that output operationally and evidentially admissible under information available at that decision time?

这里不用 J 评价“好不好”。

只检查：

```text
can the recommendation legitimately be issued?
```

---

# 17. Exp4B Analysis cohort

定义所有 structurally eligible rolling decision nodes。

具体 denominator 必须从最新版 model 正式 eligibility contract 读取。

不要用：

```text
only nodes where model already gave a recommendation
```

作为 availability denominator。

对每个 node 记录最终 decision-support state。

优先沿用 model 已有 lanes，不自行改名。

---

# 18. Exp4B Decision availability

Principal：

\[
\boxed{
Formal\ Recovery\ Recommendation\ Availability
}
\]

直接报告 proportion：

```text
nodes with >=2 formally comparable actions
and >=1 formal non-A00 recovery action
/
structurally eligible rolling decision nodes
```

如果 model 正式 formal-decision 定义不同，服从 model contract。

同时报告：

```text
baseline-only formal %
conditional/scenario-only %
abstain %
unsupported/excluded %
```

这些是 descriptive status proportions，不创造 composite score。

---

# 19. Exp4B Lead-time status profile

把 decision-support status 也沿 lead time 展示。

为避免 10 个 stacked bars 太密，主图可用 frozen bands：

```text
EARLY:       300–480 min
TACTICAL:    120–240 min
NEAR-TERM:    30–60 min
IMMEDIATE:     0 min
```

具体 band boundary 在 Development 前冻结。

主结果显示：

```text
FORMAL RECOVERY
BASELINE ONLY
NON-FORMAL / CONDITIONAL
ABSTAIN / UNSUPPORTED
```

如果 model lanes 不适合合并，则保留 exact lanes。

不得通过合并掩盖 unsupported。

---

# 20. Exp4B Hard operational/evidential audit

仅针对输出的 formal recommendation。

逐 recommendation 检查：

## Factual consistency

```text
known factual event contradiction?
identity mismatch?
resolved event treated as unresolved?
```

Headline：

`Factual contradiction rate (%)`

## Execution feasibility

```text
execution opportunity open?
preparation-time condition satisfied?
timing window still valid?
```

Headline：

`Execution-feasible recommendation rate (%)`

## Structural feasibility

```text
declared action target exists?
required decision object exists?
action contract instantiated legally?
```

Headline：

`Structural-feasibility rate (%)`

## Evidential admissibility

```text
formal support actually satisfied?
scenario/conditional action promoted to formal?
coverage missing?
provenance silently strengthened?
```

Headline：

`Unsupported formal recommendation rate (%)`

## Leakage

```text
any field with availability_time > decision_time?
realized outcome used upstream?
```

Headline：

`Decision-time leakage rate (%)`

不要把这些合成一个：

```text
Decision Validity Score
```

---

# 21. Exp4B Action composition

作为 managerial descriptive cohort characterization，不是 performance metric，也不是 representation-mechanism evidence。

默认位置：

```text
secondary table / Appendix
```

Exp2B 已承担 action-family composition 的主要机制解释，因此 Exp4B 不重复占用主图。

报告 formal selected actions by existing action-family registry。

优先复用正式 family names。

可适当汇总：

```text
A00 / no additional action
timing
capacity coordination
passenger/service
ground
aircraft
crew
network/cancellation
```

不要人为新建与 23-action registry 不对应的分类。

样本足够时特别报告：

```text
aircraft swap share
cancellation/truncation share
```

---

# 22. Exp4B LLM Auxiliary Audit

现有 DeepSeek audit 只作为：

```text
AUXILIARY_OPERATIONAL_PLAUSIBILITY_AUDIT
```

绝不作为 ground truth。

默认论文位置：

```text
APPENDIX
```

只有在 Development 阶段以下条件都足够稳定时，才允许主文放一个简短 table / secondary panel：

- schema/parse gate PASS；
- unsupported-fact assertion rate 足够低；
- known-false prerequisite error 可接受；
- repeat agreement 可解释；
- Fleiss' kappa 可解释。

即使进入主文，其证据层级仍低于：

```text
observed outcomes
hard operational/evidential rules
```

绝不允许：

```text
LLM validates the model
LLM confirms decision accuracy
LLM simulates real causal outcome
```

LLM audit 的最合理用途是：

> surface missing-information boundaries and obvious operational plausibility concerns that hard coded rules may not enumerate.

# 23. LLM audit sample

Principal：

```text
128 episodes
3 independent judgments / episode
```

继续沿用既有 V2 scale，除非新 formal cohort不足。

抽样在 Development 冻结。

至少覆盖：

- major selected action families；
- tight vs non-tight turnaround；
- different evidence-support situations；
- different lead-time bands。

如果某 family 样本少：

- 如实报告；
- 不通过 Test 后 oversample 调整结果。

---

# 24. LLM input

只提供 decision-time legitimate context：

```text
current observable state summary
relevant predicted state/consequence summary
selected action
known prerequisites
known execution facts
declared missing/unknown information
```

不要提供：

- future realized outcome；
- paper claim；
- “our model selected this”；
- desired answer；
- internal result labels。

---

# 25. LLM output schema

固定：

```text
ACCEPT
ACCEPT_WITH_RESERVATIONS
REJECT
INSUFFICIENT_INFORMATION
```

同时结构化输出：

```text
reason
missing_information
factual_concern
prerequisite_concern
unsupported_fact_assertion
confidence
```

保留 exact schema/prompt hashes。

---

# 26. LLM reliability

主报告：

```text
category proportion
exact 3-repeat agreement
Fleiss' kappa (nominal)
unsupported-fact assertion rate
known-false prerequisite error rate
unknown-prerequisite asserted-true rate
```

如果 κ / repeat agreement 较低：

- 自动降级 LLM evidence；
- 不删除坏结果；
- 不重写 prompt 后继续 Test 直到好看。

Prompt refinement 只允许 Development。

---

# 27. LLM pilot gates

正式 audit 前：

```text
schema pass rate >= 0.95
parse failure <= 0.05
unsupported-fact assertion acceptably low
known-false prerequisite error = 0 preferred
unknown prerequisite must not be asserted true
```

阈值必须在 Development 冻结。

如果 fail：

`LLM_AUDIT_NOT_PAPER_ELIGIBLE`

但 Exp4 其余部分继续。

---

# 28. LLM missing-information analysis

重点输出 frequent missing-information categories。

类别必须从 LLM free-text 经预定义 coding dictionary 映射，或由 Development 先冻结 taxonomy。

可能类别：

```text
live crew status
replacement aircraft availability
passenger connection detail
gate/stand/resource status
maintenance constraints
airport/network approval
other
```

如果实际输入不支持某类别，不硬加。

这个结果用于讨论：

> public-data decision support 的 evidence boundary。

---

# 29. Blind pairwise LLM audit

默认 Appendix-only。

若 Development 下：

```text
repeat agreement / Fleiss kappa
```

达到可接受稳定性，再允许：

```text
framework-selected action
vs
highest-ranked non-selected formal alternative
```

匿名随机成 Option A/B。

主文不依赖该结果。

---

# 30. Exp4C — Cross-data Robustness and Support Portability

### 30.1 科学问题

回答：

> Are the main predictive and decision-support patterns specific to the richer Data2 evidence environment, or do they remain identifiable under the weaker Data1 observability envelope?

不是：

```text
external generalization to another airline
```

也不是：

```text
Data1 performance should equal Data2
```

---

# 31. Exp4C datasets

Primary:

```text
Data2
```

Portability environment:

```text
Data1
```

必须清楚记录两者：

- observability；
- available variables；
- missing decision objects；
- semantic support；
- episode construction；
- target support。

---

# 32. Exp4C common lead-time support

先计算：

\[
\mathcal L_{common}
=
\mathcal L_{Data2}
\cap
\mathcal L_{Data1}
\]

其中 lead time 必须同时满足：

```text
same target semantics
same time-anchor meaning
sufficient observed outcomes
valid decision-time inputs
```

主文只在 common support 上做直接 cross-data comparison。

Data2-only extended 0–480 curve仍可保留在 4A。

Data1 不支持的 lead time：

```text
UNSUPPORTED
```

不得插值或 proxy 强行补齐。

---

# 33. Exp4C model comparison

主文只保留：

```text
LIGHTGBM_FAST
STATE_AWARE_FULL
```

Historical 可以 table/appendix。

RF 不再承担 4C 主比较。

原因：

4C 问的是：

> Full relative to a strong non-sequential baseline 的 pattern 是否跨 evidence environment 保留？

不是重新做 benchmark contest。

---

# 34. Exp4C predictive metrics

主：

```text
MAE (minutes)
CRPS
```

### Principal inferential contrast

Exp4C 不以：

```text
MAE_Data1 - MAE_Data2
```

作为 portability 的主要证据，因为两个 evidence environments 的观测范围、population composition 与可用输入可能不同。

主判断改为每个数据环境内部的 paired method contrast：

```text
Delta_MAE_d = MAE_FULL,d - MAE_LIGHTGBM,d
Delta_CRPS_d = CRPS_FULL,d - CRPS_LIGHTGBM,d
```

其中 `d in {Data1, Data2}`。

然后判断：

> Full relative to the same strong non-sequential baseline 的方向和 lead-time pattern 是否在两个合法 evidence environments 中 broadly retained。

Raw Data1/Data2 absolute MAE/CRPS 仍然完整报告，但只能描述：

- predictive difficulty；
- observability difference；
- evaluated population difference；

不能单独解释成 portability gain/loss。

首选图形：

small multiples

```text
Data2 panel: Full vs LightGBM
Data1 panel: Full vs LightGBM
```

必须：

- same x scale；
- same y scale；
- same method colors；
- same lead-time support；
- 95% CI。

可在 table 报：

```text
MAE difference vs LightGBM (minutes)
```

不要新命名为 gain score。

---

# 35. Exp4C decision-support portability

Data2/Data1 分别报告：

```text
formal recommendation availability
baseline-only rate
conditional/scenario-only rate
abstain rate
unsupported rate
```

继续使用旧 portability contract：

```text
PRESERVED
DEGRADED
ABSTAIN
UNSUPPORTED
```

保留：

```text
SilentSubstitutionCount = 0
DownstreamSemanticRedefinitionCount = 0
```

作为 hard gate。

---

# 36. Exp4C hard-validity check

Data1/Data2 都跑，但主文只保留：

```text
Factual contradiction rate
Unsupported formal recommendation rate
```

目的：

验证 Data1 较弱 observability 下：

```text
decision authority contracts
```

而不是：

```text
rules are silently relaxed.
```

---

# 37. Exp4C 允许的解释

如果出现：

```text
Data1 MAE worse
Data1 CRPS worse
Data1 formal availability lower
Data1 abstention higher
```

并不代表 failure，也不能仅据此归因于“数据更差”或“模型 portability 下降”。

应先区分：

```text
absolute environment difficulty
vs
within-environment Full-vs-LightGBM pattern
vs
decision-authority contraction under weaker support
```

若同时：

```text
Full vs LightGBM pattern remains broadly consistent
hard-rule violation does not increase
```

可写：

> Reduced observability degrades predictive precision and contracts decision authority rather than forcing unsupported recommendations.

不得写：

> proves universal generalization.

---

# 38. Exp4D — End-to-end Computational Adequacy

## 38.1 科学问题

回答：

> Can the complete rolling decision chain produce its next decision artifact within the operational update budget?

---

# 39. Principal computational configuration

使用正式：

```text
roll = 5 min
S = 1000 aligned scenarios
```

除非最新版 model 已冻结不同值。

主文不扫 scenario count。

MC sensitivity：

```text
500 / 1000 / 2000
```

仅 Appendix。

---

# 40. Computational paths

比较系统已有：

```text
STATE_AWARE
FAST
```

目的：

```text
normal operating path
vs
low-latency fallback path
```

不是 accuracy contest。

---

# 41. End-to-end timer

计时起点：

```text
latest admissible evidence accepted into current rolling node
```

计时终点：

```text
formal decision/recommendation artifact or explicit abstention artifact emitted
```

必须包含当前实际 pipeline：

```text
PRE
M1
consequence/state translation
action instantiation
eligibility/support evaluation
ranking/output serialization
```

如果某 stage 不在当前 model，则按真实 pipeline。

不能只测 GRU inference。

---

# 42. Exp4D 主指标

Headline：

```text
p50 E2E latency
p95 E2E latency
p99 E2E latency
```

单位：

```text
seconds
```

另报告：

```text
% <= 60 sec
% <= 120 sec
% <= 300 sec
```

其中：

```text
300 sec = formal hard budget
```

因为：

```text
roll = 5 min
```

60/120 sec 只是航空 recovery literature-friendly descriptive references，不是 hard pass requirement。

---

# 43. Exp4D Stage latency

按真实 stage 分解 absolute wall-clock：

```text
PRE
M1
CONSEQUENCE
ACTION
RANKING/OUTPUT
```

主图可以用 stacked absolute seconds。

不要只画 100% share，因为 absolute budget 才重要。

同时输出 percentage share 到 table/appendix。

---

## 43.1 Appendix diagnostic — Shared-state reuse efficiency

原 Exp1C `SHARED vs RECOMPUTED` 迁移到这里，作为 **computational mechanism diagnostic**，不作为新的 methodological novelty claim。

科学问题：

> Given the same decision-time operating state and the same frozen decision chain, does constructing the state once and reusing it reduce repeated computation relative to equivalent reconstruction?

variants：

```text
EXP4D_SHARED_STATE
EXP4D_RECOMPUTED_STATE
```

### SHARED

```text
construct PRE/current state once
construct aligned M1 scenario/state artifact once
reuse immutable/read-only artifacts downstream
```

### RECOMPUTED

对 downstream consumers 重复执行语义等价的 state/scenario reconstruction。

必须保持：

```text
same legal records
same cutoff
same model weights
same frozen references
same scenario count
same action contracts
same comparison rule
common random numbers / deterministic seed
```

### mandatory parity gate

这不是 scientific outcome comparison。两条路径必须输出等价结果：

- Top-1 action identical；
- ranking/score within tolerance；
- `J(a)` max absolute difference <= tolerance；
- scenario/consequence hashes identical where design permits。

若 parity FAIL：

```text
SHARED_STATE_REUSE_DIAGNOSTIC = INVALID
```

不能把 output difference 当 efficiency result。

### runtime metrics

只使用标准系统指标：

```text
wall-clock runtime per rolling node:
median
IQR
p95
```

可选 Appendix：

- peak memory（仅在可靠可测时）。

measurement rules：

- `time.perf_counter_ns()` 或项目统一高精度 timer；
- same hardware；
- fixed thread settings；
- warm-up excluded；
- execution order randomized/alternated；
- one-time import/model load 不进入 steady-state runtime；
- repeat count 在 Development 冻结。

这个 diagnostic 用来解释完整 chain 的工程可用性，不回流 Exp1 scientific necessity。

# 44. Exp4D Deployment gate

正式：

```text
E2E p95 < 300 sec
```

并报告：

```text
within_300_sec_rate
```

如果 p95 >= 300：

`OPERATIONAL_CYCLE_GATE = FAIL`

不能只展示 FAST path 而隐藏 State-aware fail。

---

# 45. Exp4 统计协议总览

## 4A

- episode-cluster bootstrap；
- paired across methods；
- 2000 reps；
- 95% CI。

## 4B hard rates

- episode-cluster bootstrap for node-level proportions；
- report N episodes + N nodes；
- no significance stars。

## 4B LLM

- episode as sampling unit；
- 128 episodes；
- 3 repetitions；
- category proportions；
- exact agreement；
- Fleiss κ；
- CI where appropriate。

## 4C

- same cluster bootstrap；
- same lead-time cohorts；
- no invalid direct cross-dataset significance test if semantics differ。

## 4D

- repeated measured runs on fixed hardware；
- warm-up runs excluded and documented；
- report run count；
- p50/p95/p99；
- no bootstrap required unless useful;
- machine/software specification recorded.

---

# 46. figures4papers skill — 迁移规则

参考：

`ChenLiu-1996/figures4papers/scientific-figure-making`

迁移：

- minimalist spines；
- consistent typography；
- multi-panel narrative；
- trend plots；
- composition breakdown；
- uncertainty bands；
- print-safe distinction；
- vector export；
- stable figure-generation API；
- consistent semantic color mapping。

不要迁移：

- AI leaderboard aesthetic；
- extremely wide 28–45 inch figures；
- radar；
- 3D；
- heavy bar-value annotation；
- aggressive red=bad / blue=ours rhetoric；
- dynamically tightened y-axis that visually exaggerates small effects；
- 24–36pt CS-poster typography。

TRE/JORS figure target：

```text
compact
neutral
unit-explicit
CI-visible
print-safe
scientific rather than promotional
```

---

# 47. Exp4 visual palette semantics

统一：

```text
Full / formal process: restrained blue
LightGBM: dark gray
Random Forest: medium gray
Historical: light gray
```

不要 baseline 用红色。

Decision-support statuses：

```text
FORMAL: restrained blue
BASELINE ONLY: medium gray
CONDITIONAL/SCENARIO: light gray + hatch
ABSTAIN/UNSUPPORTED: neutral/hatch/outline
```

Data2/Data1 small multiples：

- method color保持一致；
- dataset通过 panel 区分，不通过 method color 区分。

---


# 47.1 Main-text visual budget

为避免实验章节呈现为 benchmark catalogue，Exp4 主文最多建议 **2 张主图**。

## Exp4 Figure A — Predictive adequacy

保留原 Figure 4A 的 1×2：

- MAE vs lead time；
- CRPS vs lead time。

## Exp4 Figure B — Operational adequacy

建议 2×2：

- Panel A: decision-support status / formal availability；
- Panel B: hard validity proportions；
- Panel C: Data1/Data2 within-environment Full-vs-LightGBM contrast 或 support portability；
- Panel D: E2E latency / 300-s budget。

原独立 Figure 4C / Figure 4D 的详细 small multiples、stage latency breakdown、support-transition composition 可放 Appendix 或 secondary figure。

原则：

> main paper uses figures to answer four adequacy questions, Appendix carries diagnostic completeness.

# 48. Figure 4A — Prediction Performance

建议独立一张 1×2：

## Panel A
MAE vs lead time

```text
Historical
LightGBM
Random Forest
State-aware Full
```

## Panel B
CRPS vs lead time

只显示有合法 distribution 的方法。

x-axis 推荐从：

```text
480 -> 0 min before target
```

按读者“接近事件”的方向展示。

可以 normal x-order 0→480，但全文统一。

使用 line + marker + 95% CI band。

不得 bar chart。

---

# 49. Figure 4B — Decision-output Adequacy

建议 1×2 或 2×2，视版面。

## Panel A
100% stacked decision-support status across lead-time bands。

## Panel B
horizontal dot/proportion plot：

```text
Execution feasible
Structural feasible
Factual consistency
Evidence supported
No decision-time leakage
```

注意 label 用正向百分比时统一方向，例如：

```text
Factually consistent (%)
```

而 table 可以另报 violation rate。

这样图全部“越高越好”，视觉读取更顺。

## Optional Panel C
action-family composition。

LLM 不强制进入主图。

---

# 50. Figure 4C — Cross-data Robustness

主图 small multiples：

## Left
Data2:

```text
LightGBM
Full
```

MAE vs common lead time。

## Right
Data1:

同两条曲线。

强制相同 y-limits。

Secondary：

100% stacked support-transition composition：

```text
PRESERVED
DEGRADED
ABSTAIN
UNSUPPORTED
```

可做独立小图或 table。

---

# 51. Figure 4D — Computational Adequacy

## Panel A
horizontal point-range：

```text
FAST
STATE_AWARE
```

显示：

```text
p50 marker
p95 whisker
p99 outer marker
```

vertical reference lines：

```text
60 sec
120 sec
300 sec (hard budget)
```

300 sec 更明显，但不使用危险红色。

## Panel B
stacked absolute seconds by pipeline stage。

---

# 52. LLM audit figure

默认：

Appendix。

如果 Development 后：

```text
schema stable
low unsupported-fact rate
repeat agreement reasonable
Fleiss kappa interpretable
```

可在主文放一个简单 100% stacked：

```text
ACCEPT
WITH RESERVATIONS
REJECT
INSUFFICIENT
```

否则只 table + discussion。

不要为了版面硬提升 LLM evidence。

---

# 53. Figure export

必须：

```text
PDF vector
PNG 300 dpi
```

若项目已有 SVG pipeline，可同时 SVG。

要求：

- top/right spines off；
- legend frame off；
- compact font；
- text editable in vector if possible；
- white background；
- consistent figure basename；
- source-data CSV accompanying each figure。

不要依赖外部字体文件。

---

# 54. 建议代码结构

在现有 `exp/exp4` 上重构，不机械新建所有文件。

建议职责：

```text
exp/exp4/
├── __init__.py
├── README.md
├── protocol.py
├── predictive_benchmarks.py
├── lead_time.py
├── decision_validity.py
├── llm_audit.py
├── portability.py
├── runtime.py
├── metrics.py
├── statistics.py
├── reporting.py
├── figures.py
├── audit.py
├── runner.py
├── legacy/
└── tests/
```

如果旧 imports 被仓库其他位置依赖：

- 保留 compatibility shim；
- 不破坏已有 import contract。

---

# 55. Active Exp4 protocols

新版 principal：

```text
EXP4A_PREDICTIVE_ADEQUACY
EXP4B_DECISION_OUTPUT_VALIDITY
EXP4B_LLM_AUXILIARY_AUDIT
EXP4C_DATA1_DATA2_PORTABILITY
EXP4D_END_TO_END_RUNTIME
```

Exp4D Appendix computational diagnostic：

```text
EXP4D_SHARED_STATE
EXP4D_RECOMPUTED_STATE
```

必须标记：

```text
APPENDIX_COMPUTATIONAL_DIAGNOSTIC
NOT_MAJOR_NOVELTY
```

旧：

```text
RISK_POLICY_SENSITIVITY
NORMATIVE_VALUATION_SENSITIVITY
SCENARIO_RESPONSE_SENSITIVITY
ROLL_SENSITIVITY
MONTE_CARLO_CONVERGENCE
```

改为：

```text
APPENDIX_DIAGNOSTIC
```

# 56. Exp4 Main Metrics Registry

不要强行一套 metric 横跨 4A–4D。

## 4A

```text
MAE_minutes
CRPS
```

secondary:

```text
RMSE
Brier
Coverage90
Calibration
```

## 4B

```text
FormalRecommendationAvailability
ExecutionFeasibleRate
StructuralFeasibleRate
FactualConsistencyRate
EvidenceSupportedRate
DecisionTimeLeakageRate
```

LLM:

```text
AuditCategoryShare
ExactRepeatAgreement
FleissKappa
UnsupportedFactAssertionRate
```

## 4C

```text
MAE_minutes
CRPS
FormalRecommendationAvailability
SupportTransitionShare
FactualContradictionRate
UnsupportedFormalRecommendationRate
```

## 4D

```text
E2E_p50_seconds
E2E_p95_seconds
E2E_p99_seconds
Within60sRate
Within120sRate
Within300sRate
StageLatencySeconds
```

Appendix shared-state diagnostic：

```text
SharedState_runtime_median
SharedState_runtime_IQR
SharedState_runtime_p95
SharedState_output_parity
```

不创造：

```text
OverallPerformanceScore
DecisionValidityIndex
PortabilityScore
DeploymentScore
LLMReasonablenessScore
```

---

# 57. Required tables

## Table A — Predictive benchmark

Representative lead times：

```text
60
180
480
```

或者根据 common support 冻结。

列：

```text
Model
MAE
CRPS
N
```

完整 curve 在 figure/appendix source。

## Table B — Decision-output adequacy

```text
Formal availability
Execution feasible
Structural feasible
Factual contradiction
Unsupported formal recommendation
Leakage
N episodes
N nodes
```

## Table C — Data1/Data2

```text
Dataset
MAE @ representative leads
CRPS
Formal availability
Abstain
Unsupported
Factual contradiction
```

## Table D — Runtime

```text
Path
p50
p95
p99
<=60s
<=120s
<=300s
```

## LLM table

```text
ACCEPT
WITH_RESERVATIONS
REJECT
INSUFFICIENT
repeat agreement
Fleiss kappa
unsupported-fact assertion
```

---

# 58. Required audit artifacts

每次 smoke / Development run 至少输出：

1. `exp4_protocol_manifest.json`
2. `exp4_model_contract_snapshot.json`
3. `exp4_split_audit.json`
4. `exp4_lead_time_manifest.json`
5. `exp4_benchmark_manifest.json`
6. `exp4_feature_parity_audit.json`
7. `exp4_predictive_metrics.csv`
8. `exp4_decision_status.csv`
9. `exp4_decision_validity_audit.json`
10. `exp4_llm_audit_manifest.json`
11. `exp4_llm_audit_results.csv`
12. `exp4_data_portability_manifest.json`
13. `exp4_support_transition.csv`
14. `exp4_runtime_manifest.json`
15. `exp4_runtime_metrics.csv`
16. `exp4_shared_state_efficiency_audit.json`
17. `exp4_figure_sources/`
18. `exp4_summary.json`
19. `exp4_leakage_audit.json`

记录：

- git SHA；
- model hashes；
- registry hashes；
- data hashes；
- split；
- lead-time bins；
- baseline params；
- LLM prompt/schema/model version；
- hardware/software runtime spec；
- seeds；
- bootstrap config；
- Final Test access count。

---

# 59. 必须测试 — 4A

- lead-time calculation exact；
- no target leakage；
- no future feature at earlier lead；
- episode split preserved；
- Historical Train-only；
- LightGBM uses formal FAST path；
- RF does not access future fields；
- Full artifact reused；
- same observed target across methods；
- bootstrap clusters by episode；
- MAE toy test；
- CRPS toy/reference test；
- derived D_TO consistency；
- lead-time bins deterministic。

---

# 60. 必须测试 — 4B

- recommendation status exhaustive or explicitly unresolved；
- formal availability denominator correct；
- formal recommendation has valid action id；
- execution-window audit；
- structural precondition audit；
- factual contradiction detection；
- evidence/support promotion detection；
- availability_time > decision_time leakage detection；
- realized outcomes never enter decision construction；
- action-family mapping matches registry。

---

# 61. 必须测试 — LLM

- JSON/schema parse；
- prompt hash stable；
- model/version recorded；
- random ordering stable by seed；
- unsupported fact detection；
- known false prerequisite test；
- unknown prerequisite not asserted true；
- no model feedback；
- no Test labels in prompt；
- 3 repetitions independently seeded；
- Fleiss kappa unit test；
- Development-only until audit contract frozen。

---

# 62. 必须测试 — 4C

- Data1/Data2 target semantic contract；
- common lead-time intersection；
- no silent substitution；
- no downstream semantic redefinition；
- unsupported stays unsupported；
- same method color/figure scale not scientific test but plotting test；
- formal availability denominators dataset-specific but semantically comparable；
- hard validity rules not weakened for Data1。

---

# 63. 必须测试 — 4D

- timer starts/ends at correct pipeline points；
- all required stages included；
- warm-up excluded and documented；
- multiple repeated timings；
- p50/p95/p99 known-case test；
- 300s gate；
- FAST/STATE_AWARE path labels；
- stage latencies sum to E2E within overhead tolerance；
- hardware metadata recorded；
- Shared/Recomputed 使用完全相同 scientific inputs；
- Shared/Recomputed common random numbers；
- Shared/Recomputed Top-1/ranking/`J(a)` output parity；
- shared-state timer 不包含一次性 import/load；
- shared-state diagnostic 默认 Appendix-only。

---

# 64. Final-Test gate

本轮只运行：

```text
unit tests
synthetic smoke
small development smoke
Train/Calibration/Development execution where permitted
```

必须保持：

```text
FINAL_TEST_ACCESS_COUNT = 0
PAPER_FULL_RUN = FALSE
```

正式 Final Test 前必须冻结：

```text
model contract
lead-time grid
target
Historical baseline rule
RF hyperparameters
4A metrics
4B denominator/status rules
hard validity rules
LLM prompt/schema/sample contract
Data1/Data2 common-support contract
runtime instrumentation
figure/table schema
statistics
```

之后需要 human authorization。

---

# 65. Development 不允许的行为

1. 看 Test 后修改 Historical conditioning。
2. 看 Test 后换 RF hyperparameters。
3. 看 Test 后删“难看”lead times。
4. 看 Test 后把 480 改成 420 以改善图。
5. 看 LLM Test audit 后重写 prompt。
6. 因 Data1 表现弱而添加 silent proxy。
7. 因 abstain 高而降低 support gate。
8. 只报告 Full 优势 lead-time。
9. 只报告 Data2 不报告 Data1 unsupported。
10. latency fail 后只展示 FAST。
11. 用内部 J 替代 observed outcome。
12. 把 LLM audit 写成 expert validation。
13. 将 action-response scenario model 写成 causal effect。
14. 从头重新训练/设计整条 model 以适配 Exp4。

---

# 66. Exp4 Claim Scope

## 4A

允许：

> The state representation provides empirically evaluated rolling prediction performance across the operational lead-time window.

不允许：

> Prediction accuracy proves recovery effectiveness.

## 4B

允许：

> Formal recommendations satisfy the specified decision-time operational and evidential contracts on the evaluated cohort.

不允许：

> The recommendations are causally optimal/effective.

LLM：

> auxiliary operational plausibility audit only.

## 4C

允许：

> The principal predictive/support patterns remain observable or degrade in identifiable ways under a second evidence environment.

不允许：

> universal external generalization.

## 4D

允许：

> The evaluated implementation meets/does not meet the designated 5-minute rolling budget on the reported hardware.

不允许：

> universally production-ready.

---

# 67. 完成状态输出

完成 Exp4 重构后必须输出：

```text
AIR_SLOT_EXP4_REDESIGN

MODEL_CONTRACT_GATE =
LEAD_TIME_CONTRACT =
PREDICTIVE_BENCHMARK_CONTRACT =
FEATURE_PARITY_GATE =
DECISION_VALIDITY_CONTRACT =
LLM_AUDIT_ELIGIBILITY =
DATA1_DATA2_SEMANTIC_GATE =
PORTABILITY_GATE =
RUNTIME_INSTRUMENTATION_GATE =
SHARED_STATE_REUSE_DIAGNOSTIC =
FIGURE_SCHEMA =
STATISTICAL_PROTOCOL =

OLD_EXP4_HEADLINE_SENSITIVITIES =
FINAL_TEST_ACCESS_COUNT =
PAPER_FULL_RUN =

FILES_CHANGED =
TESTS_RUN =
TEST_RESULTS =

REMAINING_BLOCKERS =
NEXT =
```

另需明确回答：

```text
1. Historical baseline 最终规则是什么？
2. RF 是否只做 point benchmark，还是有合法 distribution interface？
3. Data1/Data2 共同 lead-time 支持是什么？
4. Data1 哪些 decision objects 退化/不支持？
5. formal recommendation availability 的 denominator 是什么？
6. LLM audit 是否通过 paper-eligibility gate？
7. p95 E2E 是否低于 300 s？
8. 是否发现任何必须回 model 修正的问题？
```

---

# 68. 最终实验逻辑核对

新版实验章节应形成：

```text
Exp1 — Necessity
Why are complete cross-stage information roles and admissible history needed?

Exp2 — Representation
Why joint uncertainty and mechanism-preserving consequence representation?

Exp3 — Process
Given an already rolling setting, how should newly admissible information and
time-aligned state be propagated through the fixed chain?

Exp4 — Adequacy
Is the complete frozen decision chain empirically credible, operationally admissible,
portable across evidence environments, and computationally usable?
```

其中：

```text
Shared-state construct-once/reuse vs repeated reconstruction
```

不再属于 Exp1 scientific headline，而作为 Exp4D Appendix computational diagnostic。

Exp4 不承担新的 major novelty claim。

它负责把全文从：

```text
methodological necessity
```

落到：

```text
credible operational methodology
```

而不虚构真实 counterfactual action effectiveness。


# 69. Cross-experiment boundary lock

- Exp4A owns full predictive adequacy/benchmark across lead time; it does not estimate the pure history effect.
- Exp4B owns validity/admissibility at recommendation issuance; Exp3A owns aging of an initially valid recommendation.
- Exp4C owns evidence-environment portability, not universal external generalization.
- Exp4D owns deployment/runtime adequacy and the shared-state reuse diagnostic.
- Overall action-family composition in Exp4B is descriptive/secondary; Exp2B owns it as mechanism evidence.
