# ROUND2_MODEL_ALIGNMENT_BEFORE — 论文—模型真实执行路径审计（修改前）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `760e490a74e0d4cfdc9563ab5f2c84532f595d05`
- WORKTREE_STATUS: clean（仅 `artifacts/diagnostics/ROUND2_MANUSCRIPT_32_TEXT.txt` 未跟踪，Round 2 诊断文本）
- SCIENTIFIC AUTHORITY: `Airline_Recovery_under_Delayed_Information__Residual_Risk_Control (32)(3).pdf`
  - 提取文本: `artifacts/diagnostics/ROUND2_MANUSCRIPT_32_TEXT.txt`
- 审计方法: 只读扫描真实 execution path（raw/canonical -> PRE -> M1 target/head/sampler -> M2 -> CU -> M3 -> M4 -> ranking），
  不依据 README/alias/旧 reconciliation 报告下结论。本轮尚未修改任何 model/registry/config 文件。
- 状态集合: ALIGNED / CODE_STALE / MANUSCRIPT_AMBIGUOUS / HUMAN_DECISION_REQUIRED / HISTORICAL_ONLY

## 0. 结论摘要

| 阶段 | 核心问题 | 状态 |
|---|---|---|
| PRE | realized event 一律 POSTHOC_ONLY，无 FACTUAL REPLAY 角色；data2 无 availability 规则 | CODE_STALE + HUMAN_DECISION_REQUIRED (GATE A) |
| M1 | 真实训练仍为 R_IB -> DELTA_OB -> T_TX 三头 softmax 分类器；D_OB/D_TX 只是 computed alias | CODE_STALE（最高优先级） |
| M1 | forecast_horizons=[0,15,60] 仅为 metadata，distribution 无 tau 维度 | MANUSCRIPT_AMBIGUOUS (GATE B) |
| M2 | 正式 scope 硬编码 5 分量；P_itin/P_serv 未实现；E_down 是机场级 train median | CODE_STALE + PASSENGER_MAPPING_PARAMETERS_REQUIRED (GATE C) |
| M3 | ActionRegistry/ResponseRegistry 强制 exact 23；I(a) 与 P(a) 混成 precondition UNKNOWN | CODE_STALE |
| M4 | `induced_score_to_cu=0.10` 硬编码；provenance label 直接踢出 FORMAL 比较；RMB omega 缺失 | CODE_STALE + RMB_WEIGHT_DECISION_REQUIRED |
| config | `m1_stochastic_targets=[R_IB,DELTA_OB,T_TX]` 仍以 FROZEN/HUMAN_APPROVED 描述 principal；W30 固定窗口仍冻结 | CONFIG_STALE |

---

## 1. PRE: DECISION-TIME FACTUAL UPDATE

### 1.1 information_cutoff <= decision_time
- 状态: **ALIGNED**
- `model/PRE/contracts/pre_state.py:67` 对 `DecisionNodeRecord` 强制校验；`tests/reconciliation/test_pre_history_schema.py` Test H 覆盖。
- 未发现 `information_cutoff > decision_time` 的合法路径。

### 1.2 future outcome 不得在 availability 前进入 inference state
- 状态: **ALIGNED**（结构上成立）
- `model/PRE/mapping.py`: `_POSTHOC_ROLES = {TRAIN_LABEL, EVAL_OUTCOME}`，POSTHOC 角色在 inference 消费中被排除；
  `AvailabilityBasis.POSTHOC_ONLY` 记录直接 `return None`（不进入 PRE state）。
- `model/PRE/evidence/admissibility.py` `latest_legal` 拒绝未来记录；`tests/unit/test_admissibility.py` 有覆盖。

### 1.3 FACTUAL REPLAY / state contraction
- 状态: **CODE_STALE**
- `registries/scientific_variables.yaml`: `realized_operational_event` = `availability_rule: posthoc_only`、`time_semantics: posthoc`、
  `consumers: [EVALUATION_ONLY]`、data2 `reason_code: POSTHOC_ONLY`。
- `registries/dataset_capabilities.yaml`: data2 `realized_events` = `EVAL_OUTCOME / POSTHOC_ONLY / formal_input_support: UNSUPPORTED`。
- `model/PRE/realized/routing.py`: 事实事件路由只处理 data1 trajectory（`dataset_instance_id != "data1_2019" -> False`），且作为 EVAL label。
- 结论: 全仓库不存在 “realized event 在 decision time 已可获得时替换 stochastic component” 的 FACTUAL REPLAY 角色；
  这与最新 manuscript 的 state contraction 不一致。data1 的 `predecessor_motion`（INFERENCE_EVIDENCE）是唯一的
  decision-time 事实输入，但它不是 successor OB/TO 事实。

### 1.4 Data2 factual replay availability rule (INTERACTION GATE A)
- 状态: **HUMAN_DECISION_REQUIRED**
- 检查过: manuscript、`configs/scientific/foundation.yaml`（只有 weather 的 5-min lag）、registry、已冻结 data rules ——
  均未声明 Data2 realized successor 事件的 availability 规则。不得静默虚构 lag。
- 两个可实现方案:
  - A. `tau_avail = tau_event`（retrospective replay assumption）: 事件一经发生即可作为事实进入后续节点 state；
    优点: 与 manuscript state contraction 语义最直接；风险: 把 archive 存在性当作在线可见性。
  - B. `tau_avail = tau_event + declared_lag`（lag 需 human freeze）: 更保守，但需要 human 指定 lag 数值与依据。
- 影响: scenario 中 observed replacement 的时间边界、M1 条件链中已实现上游替换 stochastic draw 的节点集合、
  PRE/M1 state 的 `information_cutoff` 语义。**不依赖该数值的 contract/code 重构可先行**，freeze 前保持 scientific gate。

### 1.5 NOAA weather replay
- 状态: **ALIGNED**
- `data2_weather_replay_lag_minutes=5` FROZEN（decision `D2-6` 2026-08-16）；`replay_lag_minutes=0`（data1）。
- `model/PRE/canonical/normalization_weather.py` 解析 ISD TMP/DEW/WND/VIS/CIG + REM(QNH/云组)。

### 1.6 T-100 segment/capacity 是否真正进入 downstream
- 状态: **MANUSCRIPT_AMBIGUOUS / 代码路径部分缺失**
- `registries/data_usage_rules.yaml`: `D2-T100` / `D2-T100-CLASS` 声明 `downstream_consumers: [PRE, M2, M3, EVALUATION_ONLY]`，
  canonical variable `segment_reference`，`AIRCRAFT_TYPE_UNVERIFIED`。
- 但 `model/M2/context.py` 只加载 `{turnaround, taxi, downstream_exposure, passenger}` 四类 reference，
  `segment_reference` **未进入 M2 consequence context**。M3 通过 `pre_state.reference_state.entries` 泛化读取（若 PRE 携带该字段则会进入参数）。
- 需要对照 manuscript Tables 3–5 判断 T-100 是 "retained context" 还是 "shared downstream context"；
  若是后者，当前代码静默丢弃 → CODE_STALE。禁止用未验证 aircraft type 制造 live aircraft compatibility（已满足: `AIRCRAFT_TYPE_UNVERIFIED`）。

---

## 2. M1: REBUILD THE REAL ESTIMATOR

### 2.1 真实训练目标
- 状态: **CODE_STALE**
- `model/M1/target_builder.py`: 构建 `R_IB / DELTA_OB / T_TX` 三目标；
- `model/M1/contracts.py:15-16`: `STOCHASTIC_TARGETS = ("R_IB", "DELTA_OB", "T_TX")`；
- `model/M1/cache.py`: `TARGET_NAMES = ("R_IB", "DELTA_OB", "T_TX")`；
- `configs/scientific/foundation.yaml`: `m1_stochastic_targets=[R_IB, DELTA_OB, T_TX]` 仍标 FROZEN/HUMAN_APPROVED。
- 论文语义: predecessor unresolved `T^{-,IB,0}`（离散 hazard）-> `D^{+,OB}`（hurdle-quantile）-> `D^{+,TX}`（hurdle-quantile），
  `D_TO = D_OB + D_TX` 逐 scenario 恒等，`D_TO` 永不作独立 head。

### 2.2 network head 真实实现
- 状态: **CODE_STALE**
- `model/M1/network.py`: `ib_head`(R_IB)、`delta_ob_head`(DELTA_OB)、`tx_head`(T_TX) 均为 `nn.Linear -> log_softmax` 分类头；
  `model/M1/loss.py` 为 interval NLL（分类 logits）。
- 这不是 discrete-hazard（predecessor）也不是 hurdle+quantile（successor）；Round 1 只在 contract 层加了
  `D_OB/D_TX/D_TO` computed alias，未改 estimator —— 正是 spec 禁止的 “public contract 已改但真正训练仍是旧语义”。

### 2.3 D_TX 对隐藏 signed DELTA_OB 的形式依赖
- 状态: **CODE_STALE**
- `model/M1/network.py`: `tx_head = nn.Linear(hidden_size * 3, ...)`，输入 = h + R_IB embedding + **DELTA_OB embedding**，
  即 T_TX 分布条件于含符号的 DELTA_OB 类别。论文要求 D_TX 条件于 formal `D_OB`（非负），
  禁止依赖下游 contract 不可见、且被 `max(0,·)` 截断丢失信息的 signed DELTA_OB。

### 2.4 D_TO 恒等
- 状态: **CODE_STALE**（alias 正确但 estimator 未实现）
- `model/M1/contracts.py:156+` `AlignedScenario` computed fields、`model/M1/semantics.py` 的
  `derived_d_ob/d_tx/d_to` 逐 scenario 满足 `D_TO = D_OB + D_TX`，`tests/reconciliation/test_m1_joint_identity.py` Test A 通过。
- 但 D_OB/D_TX 只是 `max(0, DELTA_OB)` / `max(0, T_TX - taxi_ref)` 的旧语义别名，不是训练 head 的直接输出。

### 2.5 predecessor 参数化: R_IB vs T_IB_A00
- 状态: **MANUSCRIPT_AMBIGUOUS（需在重构中消除）**
- manuscript primitive 是 `T^{-,IB,0}`（event time），`R_IB = [T^{-,IB,0} - t]^+` 为 derived。
- 当前 `target_builder.py` 直接训练 `R_IB = max(0, actual_arrival - decision_time)`；`AlignedScenario` 无
  `t_ib_event_time` 字段，`R_IB` 与 event-time 表示在事件已发生时（R_IB=0）丢失精确时间信息。
- 结论: 新 estimator 直接采用 event-time semantics（T_IB_A00），R_IB 作为 derived；
  scenario 中必须可恢复 `T_IB_A00`，禁止把 R_IB 与 T_IB_A00 混称为同一 quantity。

### 2.6 Data2 input engine
- 状态: **CODE_STALE**
- `model/M1/data.py`: `MOTION_FIELDS = (latitude_deg, longitude_deg, velocity_mps, on_ground, baro_altitude_m,
  geo_altitude_m, heading_deg, vertical_rate_mps)` 作为 principal X 的动态组；data2 `predecessor_motion` 为
  `UNSUPPORTED (NO_TRAJECTORY)`，因此 data2 节点这些字段全部走 missing mask —— 架构仍在“要求 trajectory”。
- 论文 input `u = (X_dyn, Delta X, l, Delta t, M, Q)`，static context 单独保留，且 Data2 必须按真正支持的
  字段重建 11 组输入（含 schedule/timing、turnaround/taxi reference、static route/carrier/aircraft context）。
- 禁止从无关变量推断 live crew/gate/standby/slot/trajectory（当前未发现此类推断，注册表正确标 UNSUPPORTED）。

### 2.7 NOAA weather 是否真正进入 M1
- 状态: **CODE_STALE（部分）**
- PRE canonical 解析 TMP/DEW/WND/VIS/CIG + REM(QNH)。
- `model/M1/data.py` `WEATHER_FIELDS = (temperature_c, dewpoint_c, wind_direction_deg, wind_speed_mps,
  wind_gust_mps, qnh_hpa, visibility_m)` —— TMP/DEW/WND/VIS/QNH 进入 M1；
  **`ceiling_base_m`（CIG）被 PRE 解析但未进入 M1**，需要补入输入组。

### 2.8 full admissible history
- 状态: 代码 **ALIGNED**；config/artifact **CONFIG_STALE**
- `model/M1/preparation.py:24` 主训练数据路径使用 `adaptive_history(prefix)`（episode 内完整因果前缀）；
  `model/M1/history.py` 提供 CURRENT/FIXED/ADAPTIVE 三种表示。
- 但 `configs/scientific/foundation.yaml` 仍把 `m1_fixed_history_window_minutes=30` 冻结为选择结果
  （D3_SIGNED_M1_H_W_REFREEZE），且 `M1_SIGNED_WARNING_MODEL_V1.pt` manifest 记录
  `fixed_history_window_minutes: 30`、`source_checkpoint: W30_H32_seed20260813.pt` —— 冻结 artifact 用固定 30 min 训练。
- 结论: 需把固定窗口降级为 `SENSITIVITY_ONLY`；W30 冻结 artifact 保持 HISTORICAL_ONLY，不再描述为 principal。

### 2.9 FAST path
- 状态: **CODE_STALE**
- `model/M1/fast_path.py`: `LightGBMDistributionalPredictor` 明确是 “LightGBM multiclass per target”、
  `target_semantics = "R_IB_DELTA_OB_T_TX_BIN_CONTRACTS"` —— 与论文要求的 ARX-LightGBM
  hurdle/quantile（与 STATE_AWARE 同 target/output/zero-mass/positive-conditional semantics）不符。
- Round 1 的 FAST 只是 multiclass scaffold + ABSTAIN 状态，不是论文 baseline。

### 2.10 aligned ancestral sampling
- 状态: 结构 **ALIGNED**，目标集 **CODE_STALE**
- `model/M1/scenarios.py`: `ancestral_sample` 按 R_IB -> DELTA_OB -> T_TX 顺序，observed 替换 stochastic draw，
  scenario_id/weight/episode_id/decision_node_id 保留；`warning.py` RNG lineage 按 target keyed uniforms。
- 新目标语义（T_IB -> D_OB -> D_TX -> D_TO derived）确定后，抽样顺序/条件链需同步迁移。

### 2.11 forecast horizons（INTERACTION GATE B）
- 状态: **MANUSCRIPT_AMBIGUOUS / HORIZON_SEMANTICS_DECISION_REQUIRED**
- manuscript Eq. (18): `F_{i,t,tau}(y) = Pr(Y_{i,t+tau} <= y | E_{i,<=t})`，`T = {0, 15, 60}`。
- 当前实现: `forecast_horizons_minutes=[0,15,60]` 只是 metadata（`M1Forecast` 字段 + `semantics.py` 常量）；
  distribution/scenario **没有 tau 维度**；label 定义是 decision-time 条件（非 `t+tau` 条件）；
  `summaries.horizon_summaries` 期望 `scenarios_by_horizon` dict，但 `model/M1/pipeline.py` 没有按 tau 生成 scenario 的 producer。
- 现有 `M1_HORIZON_ACCURACY_QUICK_20260818` 诊断把 “horizon” 定义为 realized lead time（30..480），
  与 Eq. (18) 的预测 horizon（0/15/60）不是同一 semantics —— 不能作为实现依据。
- 两种实现:
  - (a) 每 tau 一个分布: label 改为 `t+tau` 时刻目标状态，需重新定义 label/architecture/training objective（工作量大，语义新）。
  - (b) Eq. (18) 解释为决策节点条件 CDF，tau 仅作评估网格语义: 保留单时点分布，horizon 用于评价/分组。
  - 推荐: 若无 manuscript 更多细节，倾向 (b) 并把 (a) 作为论文扩展；但必须先由 human 解析。
- **在本决议前不写任何 “复制同一分布三次冒充多 horizon” 的测试（spec Test AE）。**

---

## 3. M2: SEVEN-COMPONENT CONSEQUENCE MODEL

### 3.1 正式 scope
- 状态: **CODE_STALE**
- `model/M2/contracts.py`: `COMPONENTS` 来自 `consequence_ontology.CONSEQUENCE_COMPONENTS` = 7 分量，
  `M2ComponentVector` 强制 exact seven rows —— contract 层已 7 分量。
- 但 principal formal scope 仍 5 分量: `model/M2/context.py` `_EXP2_FIXED_SCOPE`（5）+ `M2_FROZEN_SCOPE_NOT_FIVE_COMPONENT_FIXED`；
  `model/M2/freeze.py` `FORMAL_SCOPE=5`、`OUTSIDE_SCOPE=("P_itinerary","P_service")`；
  `registries/m2_data2_formal_cu_v1.json` `formal_scope` 5 分量。
- 论文 ontology: Flight(F_continuity/F_execution/F_propagation) + Passenger(P_time/P_itinerary/P_service) + Resource(R_operating) = 7。

### 3.2 native quantities
- 状态: **CODE_STALE**（V1 registry 定义旧语义；drivers 已消费 formal fields）
- V1 定义（历史 artifact）: `F_execution = max(0, DELTA_OB)`、`F_propagation = max(0, DELTA_OB + T_TX - taxi_ref) * expected_n(origin)`、
  `P_time = V_pax * max(0, DELTA_OB + T_TX - taxi_ref)`、`R_operating = max(0, T_TX - taxi_ref)`。
- 论文: `F_continuity=[R_IB - T_turn_ref]^+`、`F_execution=[D_OB]^+`、`F_propagation=[D_TO]^+ * E_down_{i,t}`、
  `P_time=V_pax_OD*[D_TO]^+`、`P_itin=V_pax*g_itin(D_TO)`、`P_serv=V_pax*g_serv(D_TO)`、`R_operating=[D_TX]^+`。
- `model/M2/drivers.py` 已改为只消费 formal `d_ob/d_tx/d_to`（注释明确禁止从 DELTA_OB/T_TX/taxi_reference 重建）—— 方向正确，
  但 `F_propagation` 仍乘 `expected_downstream_exposure`（机场 median，见 3.4）。

### 3.3 P_itinerary / P_service（INTERACTION GATE C）
- 状态: **CODE_STALE + PASSENGER_MAPPING_PARAMETERS_REQUIRED**
- 未实现；V1 列为 `outside_principal_scope`。论文要求 `LITERATURE_PARAMETERIZED` mapping `g_itin/g_serv`
  （delay-band/threshold basis + theta_lit + source refs + parameter version + freeze id + interpretation scope）。
- repo/manuscript 均无系数（Bratu & Barnhart 2006 / Arikan et al 2016 / Ball et al 2010 / Cook & Tanner 2015 仅引用）。
- 实现 contract + gate，不填系数。所需清单: 每个 P_itin/P_serv 的 basis function、theta 向量、单位、
  source/provenance、freeze artifact schema。

### 3.4 E_down_{i,t}
- 状态: **CODE_STALE**
- `model/PRE/reference/exposure_data2.py` (`DATA2_DOWNSTREAM_EXPOSURE@1.0.0`, D2-5 option A):
  统计量 = **connection airport 的 train-period MEDIAN**，fallback AIRPORT_CELL -> GLOBAL，min cell 50，零覆盖 ABSTAIN。
- 论文 `E_down_{i,t}` = 当前 episode/node 的 decision-visible、same-aircraft、scheduled downstream departures within 360 min
  的 schedule chain —— 是节点/航班特定值，不是机场级历史 median。
- 需重构: current schedule chain + aircraft identity + current decision node + 360-min frozen window；
  只能使用 schedule-visible 信息，不得读取 downstream realized outcomes；规则可 frozen，具体值不得用 median 代替。

### 3.5 CU normalization
- 状态: 机制 **ALIGNED**；registry 版本 **CODE_STALE（需 V2）**
- `model/common/cu_normalization.py`: `C_k^CU = q_k / c_k^CU`，`c_k^CU` = positive Train-period median，Train only，
  无 Test，无 monetary 依赖；V1 `train_scale_artifact` 为正数 median —— 机制正确。
- 但 V1 registry 为 5 分量且 native definitions 基于旧 DELTA_OB/T_TX/taxi_reference 语义 → 保留为 HISTORICAL_ONLY，
  新建七分量 V2（formal D_OB/D_TX/D_TO 语义、新 hash、provenance 记录 migration reason）。

---

## 4. M3: EXTENSIBLE ACTION CONTRACT

### 4.1 ActionRegistry / ResponseRegistry 封闭 23
- 状态: **CODE_STALE**
- `model/M3/registry.py`: `enforce_principal_ids: bool = True`，`exact_principal_registry` 要求 `ids == principal(23)`；
- `model/M3/response_registry.py:120`: `if ids != PRINCIPAL_IDS: raise` —— response registry 同样 exact 23。
- 论文: 23 templates 是 current library，`R+ = R U {a*}` 允许；新 action 需满足完整 Gamma_a contract；
  response registry 应允许未 frozen response contract 的 structural action 进入 candidate library
  （但不能进入需要 frozen response 的 comparison set）。

### 4.2 I(a) vs P(a)
- 状态: **CODE_STALE**
- `model/M3/instantiate.py:19`: `precondition = "FALSE" if any(value is False...) else "UNKNOWN" if any(value is None...) else "TRUE"`
  —— missing parameter（None）与 unknown structural fact 合并成同一个 UNKNOWN。
- 规则: required target/parameter missing -> `I(a)=0`（不进入 A）；structural FALSE -> `I(a)=1, P(a)=FALSE`（排除）；
  structural UNKNOWN -> `I(a)=1, P(a)=UNKNOWN`（保留 candidate，后续 qualification）。
- 与 Data2 缺少 crew/gate/standby/slot live state 直接相关：不得把 unsupported live object 悄悄生成 True/False。

### 4.3 Gamma_a 字段
- 状态: **ALIGNED（实质）**（需 typed 文档化映射）
- `model/M3/contracts.py` `ActionTemplate`: `required_facts/required_parameters`（iota_a、P_a）、
  `response_model/response_parameters`（theta_a）、`family/name`（l_a）、`mitigation/induced`（K_a^-/K_a^+）、
  `coverage` + `ActionMaterialCoverageContract`（G_a）、`response_provenance/response_support`（Pi_a，含
  evidence_bases/source_refs/support_state/freeze_id/parameter_version/interpretation_scope/hybrid）。
- 无需机械改名，但需保证科学含义完整且 typed（新增文档映射即可）。

### 4.4 response model
- 状态: **ALIGNED**
- `model/M3/response.py`: `Z ~ Bernoulli(p_a)`、`B|Z=1 ~ Beta(alpha,beta)`、`rho = ZB`；RNG lineage 含
  seed/episode/node/scenario/action/registry hash/sensitivity（`response_draw` 调用链在 `model/M4/post_action.py`）。

---

## 5. M4: MONETARY COMPARISON

### 5.1 raw-CU ranking 禁止
- 状态: **ALIGNED**
- `model/M4/decision.py`: 无 frozen monetary mapping 时 `MonetaryMappingRegistry.not_frozen()`，无 raw-CU fallback；
  `model/M4/ranking.py` 在 monetary 不 frozen 时 `AUTHORITATIVE_DECISION_UNAVAILABLE`；
  `tests/reconciliation/test_cu_money_ranking.py` Test G 覆盖。

### 5.2 RMB mapping
- 状态: **HUMAN_DECISION_REQUIRED（RMB_WEIGHT_DECISION_REQUIRED）**
- `model/common/monetary_system.py`: `MonetaryMappingRegistry`（RMB, NOT_FROZEN, 无 weights）schema 存在，
  `to_money()` 在未 frozen 时返回 None；但全 repo **无 omega_k^RMB 数值、无 registry 文件、无 freeze lineage**。
- 需完成: RMB registry schema（已有）/loading/lineage/validation/blocking/tests，保持 `MONETARY_MAPPING_NOT_FROZEN`
  直到 human freeze；列出七个分量所需 omega。禁止编造。

### 5.3 gamma 硬编码
- 状态: **CODE_STALE**
- `model/M4/post_action.py:106`: `action_post_consequences(..., induced_score_to_cu=0.10, ...)` —— 硬编码科学参数。
- 论文/registry 要求 gamma 单一 source of truth（frozen response/action registry -> typed request -> transformation）。

### 5.4 A00 与 scenario lineage
- 状态: **ALIGNED**
- A00 直接 `post_cu = values`（samplewise identity）；weighted mean/CVaR 使用 scenario_weight；
  `lambda=0.25, alpha=0.90` 冻结于 `configs/scientific/foundation.yaml`。重构后需重验 identity。

### 5.5 provenance lane 语义
- 状态: **CODE_STALE**
- `model/M4/lanes.py:37-40`: `PURE_SCENARIO / STRUCTURAL_BOUNDED_SCENARIO / UNSUPPORTED` provenance -> 直接返回 SCENARIO
  （被踢出 formal/model comparison）。
- 论文: provenance 限制 interpretation，不自动禁止 model-based comparison；需区分
  (A) COMPARISON ELIGIBILITY（response contract/frozen params/structural facts/opportunity/coverage/monetary basis）
  与 (B) INTERPRETATION/EVIDENCE STATUS。`lane="FORMAL"` 应代表 formal model comparability，interpretation class 单独携带。

---

## 6. CONFIG / REGISTRY MIGRATION

- `configs/scientific/foundation.yaml`
  - `m1_stochastic_targets=[R_IB, DELTA_OB, T_TX]` — **CONFIG_STALE**；降级为 LEGACY_V1/AUXILIARY，
    新 principal config 反映真实 estimator（T_IB_A00/D_OB/D_TX）。
  - `m1_formal_output_contract=[R_IB, D_OB, D_TX, D_TO]` — supersede：D_OB/D_TX 必须成为真实 head 输出。
  - `m1_fixed_history_window_minutes=30` — **CONFIG_STALE**；降级 SENSITIVITY_ONLY。
  - `m1_hidden_size=32` — **ALIGNED**（H=32 是 manuscript frozen choice）。
- `registries/m2_data2_formal_cu_v1.json` — **HISTORICAL_ONLY**（5 分量、旧定义）；新建 `M2_DATA2_FORMAL_CU_V2`。
- `registries/action_templates.yaml` + `model/M3/registry.py`/`response_registry.py` — **CODE_STALE**（exact 23）。
- 冻结 artifact（`M1_SIGNED_WARNING_MODEL_V1.pt`、`M2_DATA2_TRAIN_SCALES_V1.json`、`DATA2_*_TRAIN_FROZEN_V1.json`、
  `M2_DATA2_FORMAL_CU_V1`、`registries/registry_manifest.json`）— 全部保留原 hash，不原地篡改；
  新版本（`M1_*_V2`、`M2_DATA2_FORMAL_CU_V2`、`M3_*_V2`）带新 hash + migration provenance。
- `FINAL_TEST_ACCESS_COUNT = 0`、`PAPER_FULL_RUN = FALSE` 保持。

---

## 7. TESTS（spec §12 A–AE 对照）

Round 1 已有 focused tests（`tests/reconciliation/`）:
- `test_m1_joint_identity.py` — Test A（D_TO 恒等，但基于 alias 语义）；
- `test_cu_money_ranking.py` — Test E/F/G（CU-money 分离、RMB ranking、NOT_FROZEN 无 raw-CU fallback）；
- `test_pre_history_schema.py` — Test H/I/J（information_cutoff、adaptive history、FAST/STATE schema 一致性）；
- `test_lineage_and_m2.py`、`test_m2_smoke_contract.py`、`test_fast_path.py` — 部分覆盖。

缺口（本轮需新增）:
- PRE A–D: factual replay / availability / lineage-preserving contraction / no final-outcome leakage — 缺失。
- M1 E–N: 新 estimator 语义、非负、恒等、conditional path 不用 signed DELTA_OB、zero-mass、quantile 单调性、
  FAST/STATE 共享 formal contract、full adaptive history、Data2 无 trajectory 要求 — 缺失（E/F/G/H 目前基于 alias）。
- M2 O–T: exact seven-component、P_itin/P_serv provenance、episode/node-specific E_down、M2 不重建 D_TO、
  CU 七分量 registry、CU monetary-invariant — 缺失。
- M3 U–Y: principal-23 subset、missing param -> I=0、structural UNKNOWN distinct、extensible without upstream change、
  provenance 不自动 block comparison — 缺失。
- M4 Z–AD: RMB 未 frozen 无 ranking（已有 G）、frozen RMB ranking（部分）、gamma registry（缺失）、
  scenario lineage M1->M2->M4（部分）、A00 exact identity（部分）。
- Horizon AE: 在 GATE B 决议前不写 fake duplicate-distribution 测试。

---

## 8. EXPERIMENT IMPACT（exp1–exp4）

- 用户明确: exp1–exp4 本轮不管，后续整体重写。
- 依赖旧语义的代码（预计迁移后 EXPECTED_EXPERIMENT_STALE）:
  - `exp/exp234/scenario_artifact.py` — 直接读写旧 `R_IB/DELTA_OB/T_TX` observed/active/support 字段与 `pipeline.bins`；
  - `exp/exp1/...` — FIXED_HISTORY 变体与 W30 选择链（`exp1.yaml` variants/headline）；
  - `exp/exp2..4` — 消费 M2 5 分量 CU / 旧 scenario contract 的实验脚本。
- 只写入 `ROUND2_EXPERIMENT_IMPACT_MEMO.md`，不因兼容旧实验而污染新 model scientific contract。

---

## 9. GATES / HUMAN DECISIONS

| Gate | 内容 | 状态 |
|---|---|---|
| INTERACTION GATE A | Data2 factual-event replay availability rule（tau_avail = tau_event 或 + declared lag） | HUMAN_DECISION_REQUIRED |
| INTERACTION GATE B | Eq. (18) horizon semantics（tau 维度实现 vs 评估网格语义） | HORIZON_SEMANTICS_DECISION_REQUIRED |
| INTERACTION GATE C | P_itinerary / P_service literature coefficients | PASSENGER_MAPPING_PARAMETERS_REQUIRED |
| RMB | 七分量 omega_k^RMB + freeze lineage | RMB_WEIGHT_DECISION_REQUIRED |
| 其他 | T-100 按 manuscript Tables 3–5 判断 retained vs shared downstream context | MANUSCRIPT_AMBIGUOUS（随文档核对闭合） |

不依赖上述数值即可完成的 CODE_STALE 重构先行；真正缺失的 scientific choice 保持 gate。
