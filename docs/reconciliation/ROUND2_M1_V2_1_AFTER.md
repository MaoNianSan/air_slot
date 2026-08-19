# ROUND2_M1_V2_1_AFTER — M1 Scientific Closure 实现与验证（Tranche 2.1）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `d506d60ce7b76ca31f080b5106a6845a552c4f6a`
- WORKTREE_STATUS: dirty（Tranche 2.1 全部改动未提交；无 commit/push）
- 规格: `AIR_SLOT_ROUND2_M1_V2_1_SCIENTIFIC_CLOSURE`（attachment fcf473d4，849 行）
- 范围: 仅 M1 V2.1 scientific closure 的 5 个 closure 问题；未进入 PRE factual availability freeze、
  M2 七分量、RMB omega、Exp1-4、formal paper run
- FINAL_TEST_ACCESS_COUNT: 0（未访问 final test，未做 formal 全量实验）

## 0. 结论摘要

| 项 | BEFORE | AFTER |
|---|---|---|
| A. positive-tail / CVaR | CODE_STALE（静默 clamp 到 Q(q_max)） | typed `upper_tail_policy`；principal UNRESOLVED raise；CVaR gate `M1_POSITIVE_TAIL_DECISION_REQUIRED` |
| B. static/recurrent representation | MANUSCRIPT_IMPLEMENTATION_GAP（无 static encoder/fusion） | `M1V2StaticContext` + `StaticContextEncoder` + fused `state_representation`；fast fusion 保持 human gate |
| C. marginal summary | CODE_STALE（double sigmoid；条件分位数均值误标 marginal） | `conditional_head_summary` 与 `scenario_marginal_summary` 显式分离；单次 logit→prob |
| D. T_IB coordinate | CODE_STALE（同名字段两种语义） | internal `T_IB_REMAINING_HAZARD` 与 public `T_IB_A00`(ISO UTC) 分离；past event identity 保留 |
| E. FAST V2 | MANUSCRIPT_IMPLEMENTATION_GAP（纯 scaffold） | executable ARX-LightGBM（fit/heads/predict_development/sample/state_representation）；无 frozen artifact 时 principal 仍 ABSTAIN |
| 最终状态 | — | `PASS_WITH_SCIENTIFIC_DECISIONS_PENDING` |

## 1. A. Hurdle-quantile upper-tail / CVaR compatibility — RESOLVED (DECISION_PENDING)

实现：
- `model/M1/loss.py::quantile_value` 不再 clamp `u > q_max`：
  - `upper_tail_policy="UNRESOLVED"`（principal 默认）→ raise `M1_QUANTILE_UPPER_TAIL_UNRESOLVED`；
  - `TEST_ONLY_LINEAR`（仅 smoke fixture）→ 以 `Q(q_max)` 为锚的末段斜率线性外推；
  - `DECLARED_FROZEN` → raise `M1_QUANTILE_UPPER_TAIL_RULE_NOT_IMPLEMENTED`（接受
    `upper_tail_policy_reference`，供未来 frozen-rule registry 使用）；
  - 未知 policy → `M1_QUANTILE_UPPER_TAIL_POLICY_UNKNOWN`。
- `model/M1/contracts.py::HurdleQuantileContract` 增加 typed `upper_tail_policy` + `q_max` property；
  `cvar_support_status()` / `require_cvar_support()` 在 UNRESOLVED 时返回/抛出
  `M1_POSITIVE_TAIL_DECISION_REQUIRED`。
- `configs/scientific/foundation.yaml` 增加 `m1_v2_positive_tail_policy`：
  `HUMAN_DECISION_REQUIRED` / `UNRESOLVED` / gate `M1_POSITIVE_TAIL_DECISION_REQUIRED`；
  `from_scientific_config` 禁止 TEST_ONLY 规则。
- `model/M1/pipeline.py::smoke()` 使用 `TEST_ONLY_LINEAR`（明确 fixture-only）。

验证：
- `test_a_quantile_value_above_q_max_raises_in_principal_path`：`u == q_max` 返回声明分位数值，
  `u > q_max`（scalar / (1,) / (1,S)）一律 raise；TEST_ONLY 外推严格高于 `Q(q_max)`。
- `test_b_unresolved_upper_tail_gates_cvar_use`：`alpha >= q_max` 时 CVaR 依赖被 gate；
  显式规则打开 gate。

## 2. B. Static + recurrent representation — RESOLVED (FAST_FUSION DECISION_PENDING)

实现：
- `model/M1/contracts.py::M1V2StaticContext`：
  - SUPPORTED: `schedule.signed_minutes_to_crs_departure`（唯一 Data2/PRE 有 canonical encoder 路径的字段）；
  - ABSTAIN: `route` / `aircraft_identity` / `carrier` / `turnaround_reference` / `taxi_reference`；
  - FORBIDDEN: `live_aircraft_availability` / `gate` / `crew` / `slot` / `standby_aircraft`。
  - `fusion = CONCAT_RECURRENT_STATIC`，`implementation_choice = ROUND2_1_SINGLE_LINEAR_PROJECTION_HIDDEN32_NO_SEARCH`。
- `model/M1/network.py::StaticContextEncoder`：单线性投影到共享 hidden 维度（冻结 `m1_hidden_size=32`）；
  `M1V2GRU.state_representation(history, static_features)` 输出
  `state = concat(recurrent_repr, static_repr)`，`state_width = 2 * hidden_size`；
  无 static 输入时 static 块为显式零表示（SUPPORT_ABSTAIN，不伪造上下文）。
- 所有 common heads（hazard / d_ob / d_tx）改消费 fused state。
- `model/M1/data.py::V2_STATIC_FIELDS` / `static_features_from_sequence()`；
  `lifecycle.py`/`pipeline.py`/`fast_path.py` 传递 static features；save/load 持久化 `static_input_size`。
- manuscript "fast representation" 歧义（A. STATE_AWARE 内部共享 fast-path feature；B. FAST 与
  STATE_AWARE 独立 alternatives）保持 human gate `M1_FAST_FUSION_INTERPRETATION_REQUIRED`。

验证：
- `test_f_supported_static_context_reaches_common_heads`：不同 static 值 → 不同 fused state →
  不同 hazard/D_OB 输出；recurrent 块与输入 history 一致；static 块非零。
- `test_g_unsupported_static_context_remains_abstain`：不支持字段不进 encoder。

## 3. C. Marginal distribution summary correctness — RESOLVED

实现：
- `model/M1/pipeline.py::conditional_head_summary()`：
  - D_OB zero probability = `sum_b pmf_b * sigmoid(zero_logit_b)`（**单次** logit→prob，无二次 sigmoid）；
  - positive quantiles 显式标注 `CONDITIONAL_MIXTURE_NOT_MARGINAL`；
  - D_TX 显式标注 `CONDITIONAL_AT_EXPECTED_D_OB_BIN_NOT_MARGINAL`，不再冒充 marginal。
- `model/M1/summaries.py::scenario_marginal_summary()`：基于 aligned V2 scenarios 的
  **empirical weighted** 边际分布（weighted empirical quantile、加权零频率、加权均值），
  作为 principal marginal API；混合 abstention 不静默丢弃。
- `warning_probability` 继续只从 V2 scenarios 计算。

验证：
- `test_c_zero_probability_transformed_exactly_once`：发射值 == 手工单次 sigmoid 加权和，
  且 != 二次 sigmoid。
- `test_d_scenario_marginal_summary_matches_empirical_weighted_scenarios`：weighted median /
  weighted mean 与手算一致；D_TX 零概率 = 加权零频率。
- `test_e_conditional_quantile_mixture_not_mislabeled_marginal`：mixture median（31.0）与
  scenario-derived marginal median（≈23.1）分离，marginal 摘要与 mixture 不同。

## 4. D. T_IB public vs internal semantics — RESOLVED

实现：
- internal hazard coordinate: `M1_V2_HAZARD_COORDINATE_TARGET = "T_IB_REMAINING_HAZARD"`；
  `model/M1/semantics.py` 增加 `remaining_hazard_coordinate_minutes()` /
  `t_ib_a00_from_remaining_minutes()` 双向转换契约。
- `HazardBinContract.target_name` literal 仅接受 `"T_IB_REMAINING_HAZARD"`（默认值同步）；
  `V2_TARGETS` / 网络 forward key / hazard 温度 key / lifecycle / target_builder / warning
  全部使用 internal 名。
- public primitive `T_IB_A00` 保持 ISO UTC 绝对时间；scenario 采样在公开层恢复绝对时间，
  内部层用 remaining-time 坐标。
- `M1V2TargetLabel` 增加 `t_ib_a00_utc` / `decision_time_utc` 字段 + hazard-coordinate 一致性校验；
  R_IB=0（已到达）的历史事件仍保留真实 absolute event time，不同历史事件时间可区分。

验证：
- `test_h_public_t_ib_a00_and_internal_hazard_coordinate_roundtrip` / `test_i_...` /
  `test_j_...`：公开/internal 双向 roundtrip、label 一致性、past event identity 保留。

## 5. E. FAST V2 boundary — RESOLVED (ARTIFACT DECISION_PENDING)

实现（`model/M1/fast_path.py` 重写为 executable ARX-LightGBM）：
- `LightGBMDistributionalPredictor.fit()`：可训练 hazard classifier、D_OB/D_TX zero classifiers、
  positive quantile regressors（ARX-LightGBM 形式）。
- `hazard_logits(state)` / `d_ob_heads(state, ib_bin)` / `d_tx_heads(state, ib_bin, d_ob_bin)` /
  `state_representation()`：与 STATE_AWARE 相同调用形状。
- `predict_development()` / `sample()`：输出与 STATE_AWARE 共享的 scenario/development schema。
- principal `predict_distributions()` 在无 train-frozen artifact 时仍 ABSTAIN
  （`M1_FAST_PATH_ABSTAIN_NO_FITTED_MODELS` / `M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED`）——
  正式 fit / freeze / artifact 注册未执行。

验证：
- `test_m_fast_executable_fit_and_predict_development` / `test_n_...` / `test_o_...` /
  `test_p_...`：synthetic fit 后 heads/sample 可执行、scenario seed key 与 STATE_AWARE 一致、
  principal ABSTAIN 边界成立。
- `tests/reconciliation/test_fast_path.py`（重写）：FAST 与 STATE_AWARE 共享 scenario schema 与
  seed-key 集合；service callback 契约通过。

## 6. 测试执行

- 新增 `tests/m1/test_v2_1_scientific_closure.py`（spec 第 11 节 tests A–R）：**18 passed**。
- M1 + reconciliation/contract/unit 定向套件（`tests/m1`、`tests/reconciliation/test_fast_path.py`、
  `tests/contract/test_configuration_layers.py`、`tests/unit/test_m1_coverage_data2.py`）：**101 passed**。
- 全仓: **580 passed, 1 skipped**（Tranche 2 基线 562 passed/1 skipped；新增 18 个 A–R 测试）。
- 修复的测试问题（测试侧）：`test_v2_contracts.py::_hazard` 使用 internal target 名；
  `test_v2_science_closure.py` / `test_fast_path.py` 改用 `state_representation` 后的 fused state 或
  history 参数；`cache.py::TARGET_NAMES` 迁至 internal hazard 名（schema 版本 V1→V2）。
- `exp/` 未修改；无 commit/push。

## 7. HUMAN_DECISIONS_REQUIRED（PASS_WITH_SCIENTIFIC_DECISIONS_PENDING）

1. `M1_POSITIVE_TAIL_DECISION_REQUIRED`：positive quantile levels、q_max、upper-tail
   表示/外推规则、calibration/freeze procedure（`m1_v2_positive_tail_policy=UNRESOLVED`，
   config `HUMAN_DECISION_REQUIRED`）。
2. `M1_FAST_FUSION_INTERPRETATION_REQUIRED`：manuscript fast-representation 歧义（共享 fast-path
   feature 与独立 alternative）未裁决。
3. FAST artifact freeze：无 train-frozen artifact 注册前，FAST principal predict 保持 ABSTAIN。
4. `HORIZON_SEMANTICS_DECISION_REQUIRED`（未变）：不伪造 `tau={0,15,60}`；`tau_avail` 保持 unresolved。
5. `m1_v2_quantile_levels`（未变）：DEVELOPMENT_ONLY / NOT_FROZEN。
6. Data2 factual replay availability freeze（未变）：独立 Round-2 gate。

## 8. FINAL REPORT

```
AIR_SLOT_ROUND2_M1_V2_1
REPOSITORY_HEAD = d506d60ce7b76ca31f080b5106a6845a552c4f6a
WORKTREE_STATUS = dirty (Tranche 2.1 edits uncommitted; no commit/push)

CORE_V2_GRAPH = T_IB_A00 -> D_OB -> D_TX; D_TO = D_OB + D_TX derived per scenario; R_IB = max(0, T_IB_A00 - t) derived
TAIL_CONTRACT_STATUS = typed upper_tail_policy; principal UNRESOLVED raises M1_QUANTILE_UPPER_TAIL_UNRESOLVED (no silent clamp)
CVAR_TAIL_SAFETY = cvar_support_status/require_cvar_support gated by M1_POSITIVE_TAIL_DECISION_REQUIRED
QUANTILE_LEVEL_STATUS = [0.1,0.3,0.5,0.7,0.9] DEVELOPMENT_ONLY / NOT_FROZEN (unchanged)

STATIC_CONTEXT_SUPPORT = schedule.signed_minutes_to_crs_departure only; route/aircraft/carrier/turnaround/taxi ABSTAIN; gate/crew/slot/standby/live FORBIDDEN
STATIC_CONTEXT_FUSION = CONCAT_RECURRENT_STATIC (single linear projection, hidden=32, no search); zero static block when ABSTAIN
FAST_FUSION_INTERPRETATION = M1_FAST_FUSION_INTERPRETATION_REQUIRED (human decision pending)

ZERO_PROBABILITY_FIX = single sigmoid transformation (no double sigmoid)
MARGINAL_SUMMARY_METHOD = conditional_head_summary (CONDITIONAL_MIXTURE_NOT_MARGINAL) vs scenario_marginal_summary (empirical weighted marginal); no mislabeling

PUBLIC_T_IB_SEMANTICS = T_IB_A00 is ISO UTC absolute event time
INTERNAL_HAZARD_COORDINATE = T_IB_REMAINING_HAZARD remaining-minutes bins; bidirectional conversion contract
PAST_EVENT_IDENTITY_PRESERVED = labels carry t_ib_a00_utc + decision_time_utc; R_IB=0 events remain distinguishable

FAST_V2_EXECUTABLE = executable ARX-LightGBM (fit, hazard_logits, d_ob_heads, d_tx_heads, predict_development, sample, state_representation)
FAST_V2_ARTIFACT_STATUS = no train-frozen artifact; principal FAST predict ABSTAIN (M1_FAST_V2_FITTED_ARTIFACT_NOT_REGISTERED)

HORIZON_STATUS = HORIZON_SEMANTICS_DECISION_REQUIRED (no fake tau={0,15,60}; tau_avail unresolved)
FACTUAL_AVAILABILITY_STATUS = Data2 factual replay availability freeze not executed (separate Round-2 gate)

FOCUSED_TESTS = 18 passed (tests A-R, tests/m1/test_v2_1_scientific_closure.py)
M1_TESTS = 101 passed (tests/m1 + reconciliation fast_path + configuration_layers + unit m1 coverage)
FULL_REPOSITORY_TESTS = 580 passed, 1 skipped

FINAL_TEST_ACCESS_COUNT = 0
FULL_PAPER_EXPERIMENTS_RUN = false

HUMAN_DECISIONS_REQUIRED = M1_POSITIVE_TAIL_DECISION_REQUIRED; M1_FAST_FUSION_INTERPRETATION_REQUIRED; FAST artifact freeze; HORIZON_SEMANTICS_DECISION_REQUIRED; m1_v2_quantile_levels freeze; Data2 factual replay availability freeze

FINAL_STATUS = PASS_WITH_SCIENTIFIC_DECISIONS_PENDING
```
