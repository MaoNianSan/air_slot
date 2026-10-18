# ROUND2_M1_V2_MIGRATION — M1 V2 真实估计器重建（Tranche 2）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `dc41d21d64eb58277cda73a7fea7bfa3680f9521`
- WORKTREE_STATUS: dirty（本 tranche 全部改动未提交；无 commit/push）
- 规格: `AIR_SLOT_ROUND2_EMPIRICAL_MODEL_ALIGNMENT` Tranche 2（attachment 90ef0a7d）
- 范围: 仅 M1 + 其依赖的 shared contracts/config/tests；未进入 M2 七分量、PRE factual replay freeze、
  RMB omega freeze、Exp1-4
- FINAL_TEST_ACCESS_COUNT: 0（未访问 final test，未做 formal 全量实验）

## 0. 结论摘要

| 项 | 状态 |
|---|---|
| M1 principal 语义 | 由 `R_IB -> DELTA_OB -> T_TX` 三头 softmax 分类器迁移为 `T_IB_A00 -> D_OB -> D_TX` 真实估计器 |
| predecessor head | DISCRETE_HAZARD（remaining-time bins + survival tail，PMF 恒归 1） |
| successor heads | HURDLE_QUANTILE（零质量 hurdle + positive conditional quantiles，softplus cumsum 保证单调正） |
| D_TX 形式父节点 | formal D_OB（signed DELTA_OB 永不进入 D_TX 图） |
| D_TO | `D_OB + D_TX` 逐 scenario 派生，无独立 head |
| R_IB | `max(0, T_IB_A00 - t)` 派生，无独立 head |
| history | FULL_ADAPTIVE_CAUSAL_PREFIX，H=32（`m1_fixed_history_window_minutes=30` 迁为 SENSITIVITY_ONLY/HISTORICAL_V1） |
| 最终状态 | PASS_WITH_HORIZON_DECISION_PENDING（唯一 HUMAN_DECISION_REQUIRED: `m1_v2_quantile_levels` 为 DEVELOPMENT_ONLY） |

## 1. 正式科学契约

- primitive chain: `T_IB_A00 -> D_OB -> D_TX`
- 派生量: `R_IB = max(0, T_IB_A00 - t)`、`D_TO = D_OB + D_TX`（逐 scenario）
- 前驱 head: discrete hazard；公开 scenario 可恢复绝对事件时间 `T_IB_A00`
- 后继 head: `P(D=0 | parents, h) + P(D>0 | parents, h) * Q_D(u | D>0, parents, h)`
- Data2 编码器不要求 trajectory；`ceiling_base_m` 进入受支持 weather 特征集
- 警告事件: `P(D_TO > 30)`，只消费 V2 formal scenario（T_IB_A00 / D_OB / D_TX / D_TO）
- config: `m1_state_estimator_v2 = M1_STATE_ESTIMATOR_V2`（FROZEN，ROUND2_TRANCHE2_SPEC provenance）

## 2. 实现落点（未提交）

- `model/M1/semantics.py` — V2 常量与派生 helper（`derived_r_ib_minutes`、`derived_d_to_from_primitives`）
- `model/M1/contracts.py` — `HazardBinContract`、`HurdleQuantileContract`、`M1V2TargetLabel`、`M1V2Scenario`
- `model/M1/loss.py` — `hazard_pmf`、`hazard_interval_nll`、`pinball_loss`、`hurdle_quantile_loss`、
  `monotone_positive_quantiles`、`quantile_value`（含全局分母 batch-split invariant 支持）
- `model/M1/network.py` — `M1V2GRU`（hazard_head / ib_embedding / d_ob 双 head / d_ob_embedding / d_tx 双 head）
- `model/M1/scenarios.py` — `_uniform_v2`、`ancestral_sample_v2`（T_IB_A00 -> D_OB -> D_TX 祖先序、
  typed observed 替换、父节点 ABSTAIN 传播到子 scenario）
- `model/M1/pipeline.py` — V2 `M1Pipeline`（smoke/from_scientific_config/predict_distributions/sample_from_pre/save/load）
- `model/M1/lifecycle.py` — V2 training lifecycle（teacher forcing 依 formal 序；microbatch == fullbatch 梯度）
- `model/M1/warning.py` — V2 `batched_warning_probability` / `warning_probability`
- `model/M1/data.py` — V2 特征组（X=30, M=36, Delta=2, E=30, S=4，合计 102）与无 trajectory 编码器
- `model/M1/target_builder.py` — `build_v2_target_labels`（T_IB_A00 / D_OB / D_TX，stage-gated）
- `model/M1/{cache,coverage,preparation,fast_path,service,summaries,cli,__init__}.py` — V2 消费方
- `configs/scientific/foundation.yaml` — `m1_state_estimator_v2`、`m1_v2_quantile_levels`(DEVELOPMENT_ONLY)、
  `m1_fixed_history_window_minutes` -> SENSITIVITY_ONLY、`m1_stochastic_targets` 增加 LEGACY_V1 role

## 3. 测试执行

- 新增 V2 focused tests: `tests/m1/test_v2_contracts.py`、`tests/m1/test_v2_loss.py`、
  `tests/m1/test_v2_science_closure.py`（observed-IB contraction、signed-DELTA_OB 隔离、网络级零质量/单调、
  无 trajectory 编码、CIG 支持、full-history prefix）
- 迁移 `tests/m1/*` 至 V2：ancestral/batched warning/lifecycle/performance/pipeline/signed-ob/warning 等
- 跨模块更新：`tests/reconciliation/test_m1_joint_identity.py`、`tests/reconciliation/test_fast_path.py`、
  `tests/integration/test_refactor_behavioral_equivalence.py`、`tests/contract/test_configuration_layers.py`、
  `tests/unit/test_m1_coverage_data2.py`、`tests/static/test_pre_ownership_gate_v2.py`
- 全仓结果: **562 passed, 1 skipped**（Tranche 2 前基线 543 passed, 1 skipped）
- `exp/` 未修改；未出现需分类 `EXPECTED_EXPERIMENT_STALE` 的失败

## 4. 修复的沿路缺陷（不要回退）

- `hurdle_quantile_loss` 对 `(B,1)` zero logit 兼容 `(B,)` target
- 非激活行 NaN value 不再污染 pinball 均值
- loss 项按全局 active count 归一（denominator），microbatch 与 fullbatch loss/gradient 严格一致
- `batching_diagnostics` padding 计算恢复为 `max_len * batch_size` 口径
- `quantile_value` 支持 scalar / (B,) / (B,S) uniform
- Data1 父 ABSTAIN 传播：D_OB 不支持时 D_TX 一并 ABSTAIN（不再抛 PARENT_UNSUPPORTED）
- `_sample_from_pmf` 消除非连续 searchsorted warning

## 5. 保留的 human gates

- `HORIZON_SEMANTICS_DECISION_REQUIRED`：不伪造 `tau={0,15,60}`；horizon 语义保持待决策
- `m1_v2_quantile_levels` = DEVELOPMENT_ONLY（manuscript 未冻结正分位数值；`[0.1,0.3,0.5,0.7,0.9]` 仅 scaffold）
- Data2 factual replay availability freeze 未执行（Round-2 独立 gate）
- `FINAL_TEST_ACCESS_COUNT = 0`

## 6. Tranche 2.1 — Scientific Closure（2026-08-19）

规格: `AIR_SLOT_ROUND2_M1_V2_1_SCIENTIFIC_CLOSURE`（attachment fcf473d4）。
Tranche 2 建立了 real estimator（`T_IB_A00 -> D_OB -> D_TX` + 派生 `R_IB`/`D_TO`）；
Tranche 2.1 修复 scientific closure，尤其：

- **positive-tail / CVaR compatibility**：`quantile_value` 不再静默 clamp `u > q_max`；
  typed `upper_tail_policy`（UNRESOLVED 主路径 raise / TEST_ONLY_LINEAR 仅 smoke /
  DECLARED_FROZEN 未注册规则）；CVaR 依赖经 `M1_POSITIVE_TAIL_DECISION_REQUIRED` gate；
  config `m1_v2_positive_tail_policy = HUMAN_DECISION_REQUIRED/UNRESOLVED`。
- **state/static representation**：`M1V2StaticContext` + `StaticContextEncoder` +
  `state_representation = concat(recurrent, static)`；仅 schedule timing SUPPORTED，
  其余 manuscript static 字段 ABSTAIN/FORBIDDEN；fast-fusion 解释保持
  `M1_FAST_FUSION_INTERPRETATION_REQUIRED`。
- **marginal summary semantics**：`conditional_head_summary`（单次 sigmoid，显式
  CONDITIONAL_MIXTURE_NOT_MARGINAL / CONDITIONAL_AT_EXPECTED_D_OB_BIN_NOT_MARGINAL）
  与 `scenario_marginal_summary`（empirical weighted marginal）分离，不再误标。
- **T_IB coordinate separation**：internal `T_IB_REMAINING_HAZARD`（remaining-minutes bins）
  与 public `T_IB_A00`（ISO UTC 绝对时间）分离；label 保留 `t_ib_a00_utc` +
  `decision_time_utc`，R_IB=0 历史事件仍可区分。
- **FAST executable boundary**：`LightGBMDistributionalPredictor` 从 scaffold 变为
  executable ARX-LightGBM（fit/heads/predict_development/sample/state_representation）；
  无 train-frozen artifact 时 principal predict 仍 ABSTAIN（artifact freeze 为 human gate）。

结果: 全仓 **580 passed, 1 skipped**（Tranche 2 基线 562 passed/1 skipped，新增 18 个
`test_v2_1_scientific_closure.py` A–R 测试）；`FINAL_TEST_ACCESS_COUNT = 0`；
`exp/` 未修改；无 commit/push。
最终状态: `PASS_WITH_SCIENTIFIC_DECISIONS_PENDING`（详见
`docs/reconciliation/ROUND2_M1_V2_1_AFTER.md`）。

## 7. Tranche 2.2 — Contract Correction（2026-08-19）

规格: `AIR_SLOT_ROUND2_M1_V2_2_CONTRACT_CORRECTION`（attachment e9181943）。
Tranche 2.2 修正四个 contract 问题，不推翻 Tranche 2/2.1 已建立的核心图（`T_IB_A00 -> D_OB -> D_TX`、
派生 `R_IB`/`D_TO`）与 tail/marginal/T_IB/FAST-executable closure：

- **A. static/reference representation**：撤销 Tranche 2.1 的 fake static duplicate
  （`V2_STATIC_FIELDS` / `static_features_from_sequence` / `StaticContextEncoder` /
  `M1V2StaticContext` / `CONCAT_RECURRENT_STATIC` 移除）；schedule countdown 回归 DYNAMIC
  current-AR 变量；新增 typed `M1StaticReferenceContext`（route/carrier/aircraft/schedule-reference/
  turnaround/taxi，全部 `UPSTREAM_PRE_INTERFACE_REQUIRED`）与
  `M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`；static/reference 只在 PRE 发布后进入 estimator。
- **B. FAST discrete-hazard risk-set**：FAST hazard 每 bin 按 risk set
  `R_k = {n : active AND remaining >= start(B_k)}` 训练（`y_{n,k} = 1[remaining in B_k]`）；
  tail rows 保持 at-risk 并被 survival tail 吸收；退化 risk set 仅 TEST_ONLY constant surrogate
  （principal raise `M1_FAST_HAZARD_RISK_SET_DEGENERATE`）；共享 `loss.hazard_pmf`，与
  STATE_AWARE hazard PMF 语义一致。
- **C. common calibration contract**：`M1CalibrationContract`（predecessor=
  `DISCRETE_HAZARD_EVENT_TIME_NLL`、successor_zero_mass=`HURDLE_ZERO_BINARY_CE_TEMPERATURE`、
  positive_quantile=`QUANTILE_CALIBRATION_NOT_APPLIED`、split=calibration、version
  `M1_CALIBRATION_CONTRACT_V1`、final_test_access_count=0）；hazard 温度改由 event-time NLL 拟合
  （`fit_hazard_temperature`）；hazard logits 使用 multiclass CE 一律 raise
  `M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN`；STATE_AWARE 与 FAST 共享同一 policy。
- **D. fast/current-AR representation**：`r_fast` = 最后一个 causal row 的确定性 V2 特征块；
  STATE_AWARE = `concat(GRU(history), projection(r_fast))`（`FastRepresentationEncoder`，H=32
  `IMPLEMENTATION_CHOICE_NO_SEARCH`）；FAST 直接消费 r_fast；撤销
  `M1_FAST_FUSION_INTERPRETATION_REQUIRED`（最新 manuscript Section 3–4 语义无歧义证据）。
- config: `m1_v2_representation_contract`（FROZEN, `ROUND2_2_MANUSCRIPT_IMPLEMENTATION`,
  `STATIC_REFERENCE_CONTEXT_PENDING_PRE`）、`m1_v2_calibration_contract`（FROZEN,
  `M1_CALIBRATION_CONTRACT_V1`）。
- horizon 文档状态改为 `MANUSCRIPT_REQUIREMENT_CLEAR` / `CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE`
  （不再用 `MANUSCRIPT_AMBIGUOUS` 表述）；代码 gate `HORIZON_SEMANTICS_DECISION_REQUIRED` 保持。

结果: 全仓 **604 passed, 1 skipped**（Tranche 2.1 基线 580 passed/1 skipped；新增 24 个
`tests/m1/test_v2_2_contract_correction.py` A–X 测试；M1 + reconciliation/contract/unit 定向套件
145 passed）；`FINAL_TEST_ACCESS_COUNT = 0`；`exp/` 未修改；无 commit/push。
最终状态: `PASS_WITH_UPSTREAM_PRE_AND_SCIENTIFIC_DECISIONS_PENDING`（详见
`docs/reconciliation/ROUND2_M1_V2_2_AFTER.md`）。

