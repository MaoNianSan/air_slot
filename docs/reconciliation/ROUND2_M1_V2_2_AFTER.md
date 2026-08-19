# ROUND2_M1_V2_2_AFTER — M1 Contract Correction 实现与验证（Tranche 2.2）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `8404e67dbcacd40bd8aaf7a1ea58a194012c2eb7`
- WORKTREE_STATUS: dirty（Tranche 2.2 全部改动未提交；无 commit/push）
- 规格: `AIR_SLOT_ROUND2_M1_V2_2_CONTRACT_CORRECTION`（attachment e9181943）
- 范围: 仅 4 个 contract-correction 问题；未进入 PRE factual replay availability freeze、
  PRE static/reference publication、M2 七分量、RMB omega、Exp1-4、formal paper run
- FINAL_TEST_ACCESS_COUNT: 0

## 0. 结论摘要

| 问题 | BEFORE | AFTER |
|---|---|---|
| A. static/reference representation | CODE_STALE（schedule countdown 双重 fused） | 假 static closure 撤销；`M1StaticReferenceContext` typed contract；全部字段 UPSTREAM_PRE_INTERFACE_REQUIRED |
| B. FAST discrete hazard | CODE_STALE（全行拟合，非 risk set） | 每 bin 按 risk set 训练；tail rows 保持 at-risk；TEST_ONLY surrogate 显式 fixture-only |
| C. calibration contract | CODE_STALE（multiclass CE 用于 hazard） | `M1CalibrationContract` + `fit_hazard_temperature`（event-time NLL）；zero-mass discipline；quantile 状态显式 NOT_APPLIED |
| D. fast/current-AR representation | CODE_STALE（`M1_FAST_FUSION_INTERPRETATION_REQUIRED` 保留；无 r_fast） | `r_fast` deterministic block；STATE_AWARE = concat(GRU, projection(r_fast))；FAST 直接消费 r_fast；fusion gate 撤销 |
| 最终状态 | — | `PASS_WITH_UPSTREAM_PRE_AND_SCIENTIFIC_DECISIONS_PENDING` |

## 1. A. Static/reference representation contract — RESOLVED (UPSTREAM_PRE_PENDING)

- `model/M1/data.py`：删除 `V2_STATIC_FIELDS` / `V2_STATIC_FIELD_INDEX` /
  `static_features_from_sequence`；`schedule.signed_minutes_to_crs_departure` 保持为
  DYNAMIC current-AR 变量（只出现在 recurrent sequence / r_fast 块中，不再重复进 static branch）。
  新增 `fast_features_from_sequence()` = 最后一个 causal row 的完整 V2 特征块（r_fast）。
- `model/M1/contracts.py`：`M1V2StaticContext` 移除，替换为 `M1StaticReferenceContext`
  （route_context / carrier_context / aircraft_identity / schedule_reference_context /
  turnaround_reference / taxi_reference，每项含 support_state + pre_status +
  provenance_reference_id + freeze_id）；全部字段 `UPSTREAM_PRE_INTERFACE_REQUIRED`；
  `M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE` 逐项标注
  AVAILABLE_ALREADY / AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 / NEEDS_PRE_REFERENCE_BINDING /
  UNSUPPORTED（available-but-not-published 绝不误标 UNSUPPORTED）。
- `model/M1/network.py`：`StaticContextEncoder` 移除，替换为 `FastRepresentationEncoder`；
  `M1V2GRU` 删除 static branch，`state_width = 2 * hidden`（history + projection(r_fast)）；
  `state_representation(history, fast_features)`；无 fast 输入时 fast 块显式为零
  （不伪造任何 static/reference context）。
- `model/M1/pipeline.py` / `lifecycle.py` / `scenarios.py`：全部改传 `fast_features`；
  `sample_from_pre` 不再从 schedule 抽 static 值。
- 语义确认：RETAINED_IDENTITY ≠ MODEL_FEATURE；PRE 未发布前任何 static 字段不进入 estimator
  （`STATIC_REFERENCE_CONTEXT_PENDING_PRE`）；M1 不绕过 PRE 读取 raw/BTS/reference 文件。

## 2. B. FAST discrete-hazard risk-set semantics — RESOLVED

- `model/M1/fast_path.py::fit`：对每个 finite bin k：
  - risk set `R_k = {n : active AND remaining >= start(B_k)}`；
  - `y_{n,k} = 1[remaining in B_k]`，只在该 risk set 上拟合 binary classifier；
  - `remaining >= max_finite` 的样本保持 at-risk 于所有 finite risk set，不产生 finite event
    （由 survival tail 吸收）。
- 退化 risk set（单类 / 空）：principal 训练 raise
  `M1_FAST_HAZARD_RISK_SET_DEGENERATE`；仅 synthetic smoke 在
  `allow_test_only_surrogate=True` 时使用 `_ConstantHazardSurrogate`
  （TEST_ONLY 常数 hazard，显式 fixture-only，不改变统计定义）。
- `hazard_risk_set_sizes()` 契约方法可直接验证 risk-set 语义；`hazard_logits` + 共享
  `loss.hazard_pmf`（`h_k * prod_{j<k}(1-h_j)` + tail）保证 FAST 与 STATE_AWARE 的
  hazard PMF 语义一致。
- `FastPathContract.hazard_semantics = "DISCRETE_HAZARD_RISK_SET"`。

## 3. C. Common calibration contract — RESOLVED (POLICY_FROZEN, NO_FITTED_ARTIFACT)

- `model/M1/calibration.py` 重写：
  - `M1CalibrationContract`：predecessor_probability_calibration
    （`DISCRETE_HAZARD_EVENT_TIME_NLL`）、successor_zero_mass_calibration
    （`HURDLE_ZERO_BINARY_CE_TEMPERATURE`）、positive_quantile_calibration
    （`QUANTILE_CALIBRATION_NOT_APPLIED`）、split、version、final_test_access_count。
  - `fit_hazard_temperature(logits, labels, active, contract)`：hazard logits -> temperature ->
    hazard probabilities -> induced event-time PMF/survival tail -> event-time NLL
    （通过 `hazard_interval_nll`）；calibration split only。
  - `reject_multiclass_hazard_calibration()`：对 hazard logits 使用 multiclass softmax CE
    一律 raise `M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN`（旧 `fit_temperature` 移除）。
  - `fit_zero_mass_temperature`（zero-mass binary CE discipline）；
    `quantile_coverage_diagnostic`（calibration-split coverage，仅诊断）。
  - `require_calibration_split` / `require_no_final_test` 强制 split 与 Final-Test 边界。
- `model/M1/lifecycle.py::calibrate` 改用 `fit_hazard_temperature`（hazard 温度由 event-time
  NLL 拟合；D_OB/D_TX 温度保持 1.0；positive quantiles 保持 NOT_APPLIED）。
- STATE_AWARE（`M1Pipeline.calibration_policy()`）与 FAST
  （`FastPathContract.calibration_version`）共享同一 `M1CalibrationContract` policy。

## 4. D. Fast / current-AR representation — RESOLVED

- `r_fast(i,t)` = 最后一个 causal row 的 V2 特征块（current state + weather + decision-node
  schedule countdown + Delta X + AR summaries + masks + evidence/support + stage）——
  deterministic feature block，非 full-sequence 第二次 flatten，非 LightGBM prediction/hidden。
- STATE_AWARE: `state = concat(GRU(full admissible history), projection(r_fast))`
  （`FastRepresentationEncoder` 单线性投影到共享 H=32；`IMPLEMENTATION_CHOICE_NO_SEARCH`）。
- FAST: 直接消费 `r_fast`（identity adapter），无 GRU recurrent hidden。
- `M1_FAST_FUSION_INTERPRETATION_REQUIRED` 撤销（最新 manuscript Section 3–4 语义清晰：
  fast path "omits recurrent state and uses current/autoregressive representation directly"，
  state-aware path 同时保留 recurrent 与 current/AR 信息；无文本歧义证据）。
- `M1StaticReferenceContext.fusion = "CONCAT_RECURRENT_FAST_PLUS_OPTIONAL_STATIC"`。

## 5. Config

- `configs/scientific/foundation.yaml` 新增：
  - `m1_v2_representation_contract`：FROZEN，value `ROUND2_2_MANUSCRIPT_IMPLEMENTATION`，
    implementation_choice `ROUND2_2_DETERMINISTIC_CURRENT_AR_BLOCK_NO_SEARCH`，
    static_context_status `STATIC_REFERENCE_CONTEXT_PENDING_PRE`；
  - `m1_v2_calibration_contract`：FROZEN，value `M1_CALIBRATION_CONTRACT_V1`，
    predecessor/successor/quantile 状态 + split=calibration + final_test_access_count=0。
- 未冻结任何新数据驱动参数；Final Test 未访问。

## 6. 测试执行

- 新增 `tests/m1/test_v2_2_contract_correction.py`（spec 第 10 节 tests A–X）：**24 passed**。
- M1 + reconciliation + contract + unit 定向套件：**145 passed**。
- 全仓: **604 passed, 1 skipped**（Tranche 2.1 基线 580 passed/1 skipped；新增 24 个 A–X 测试）。
- 更新：`tests/m1/test_v2_1_scientific_closure.py`（F/G static 测试改为 r_fast/pending-PRE；
  FAST 测试改用 r_fast 宽度与 risk-set surrogate）、`tests/reconciliation/test_fast_path.py`。
- `exp/` 未修改；无 commit/push；无 EXPECTED_EXPERIMENT_STALE 失败。

## 7. Horizon 文档状态

- `HORIZON_SEMANTICS_DECISION_REQUIRED` 代码 gate 保持；文档表述改为
  `MANUSCRIPT_REQUIREMENT_CLEAR` / `CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE`
  （不再使用 `MANUSCRIPT_AMBIGUOUS`）：manuscript 要求明确（horizon 标签执行契约未完成）。

## 8. PRE INTERFACE（本 tranche 只建契约，不实现 PRE）

- 输出 `M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`：
  - route_context / carrier_context: NEEDS_PRE_REFERENCE_BINDING；
  - aircraft_identity / schedule_reference_context / turnaround_reference /
    taxi_reference: AVAILABLE_BUT_NOT_PUBLISHED_TO_M1。
- 详见 `docs/reconciliation/ROUND2_M1_PRE_INTERFACE_REQUIREMENTS.md`。

## 9. FINAL REPORT

```
AIR_SLOT_ROUND2_M1_V2_2
REPOSITORY_HEAD = 8404e67dbcacd40bd8aaf7a1ea58a194012c2eb7
WORKTREE_STATUS = dirty (Tranche 2.2 edits uncommitted; no commit/push)

STATIC_DUPLICATION_REMOVED = true (schedule countdown stays DYNAMIC current-AR only; V2_STATIC_FIELDS/static_features_from_sequence/StaticContextEncoder removed)
STATIC_REFERENCE_CONTRACT = M1StaticReferenceContext typed (route/carrier/aircraft/schedule-reference/turnaround/taxi; support_state + pre_status + provenance/freeze ids); all UPSTREAM_PRE_INTERFACE_REQUIRED
PRE_STATIC_FIELDS_REQUIRED = M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE (route/carrier NEEDS_PRE_REFERENCE_BINDING; aircraft/schedule/turnaround/taxi AVAILABLE_BUT_NOT_PUBLISHED_TO_M1)

FAST_REPRESENTATION = r_fast deterministic current/AR block (last causal row; no GRU, no LightGBM prediction/hidden)
STATE_AWARE_REPRESENTATION = concat(GRU(history), projection(r_fast)); static fused only after PRE publishes (STATIC_REFERENCE_CONTEXT_PENDING_PRE)
FAST_FUSION_HUMAN_GATE_REMOVED = true (M1_FAST_FUSION_INTERPRETATION_REQUIRED removed; manuscript semantics unambiguous)

FAST_HAZARD_RISK_SET = per-bin risk set R_k = {active AND remaining >= start(B_k)}; tail rows at-risk everywhere, absorbed by survival tail
FAST_HAZARD_STATISTICAL_SEMANTICS = pmf_k = h_k * prod_{j<k}(1-h_j); tail = prod_j(1-h_j); degenerate risk sets only TEST_ONLY constant surrogate (explicit, principal raises)

HAZARD_CALIBRATION = DISCRETE_HAZARD_EVENT_TIME_NLL (fit_hazard_temperature; multiclass CE forbidden: M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN)
HURDLE_ZERO_CALIBRATION = HURDLE_ZERO_BINARY_CE_TEMPERATURE (fit_zero_mass_temperature)
POSITIVE_QUANTILE_CALIBRATION = QUANTILE_CALIBRATION_NOT_APPLIED (+ calibration-split coverage diagnostic)
COMMON_CALIBRATION_CONTRACT = M1CalibrationContract (split=calibration, version M1_CALIBRATION_CONTRACT_V1, final_test_access_count=0; shared by STATE_AWARE and FAST)

TAIL_STATUS = M1_POSITIVE_TAIL_DECISION_REQUIRED (unchanged)
T_IB_STATUS = public T_IB_A00 ISO UTC vs internal T_IB_REMAINING_HAZARD separation preserved (unchanged)
HORIZON_STATUS = HORIZON_SEMANTICS_DECISION_REQUIRED; docs now MANUSCRIPT_REQUIREMENT_CLEAR / CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE

FAST_ARTIFACT_STATUS = no train-frozen V2 FAST artifact; principal FAST predict ABSTAIN (unchanged)
PRE_INTERFACE_STATUS = typed contract only; PRE publication NOT implemented (next tranche)

FOCUSED_TESTS = 24 passed (tests A-X, tests/m1/test_v2_2_contract_correction.py)
M1_TESTS = 145 passed (tests/m1 + reconciliation + configuration_layers + unit m1 coverage)
FULL_REPOSITORY_TESTS = 604 passed, 1 skipped

FINAL_TEST_ACCESS_COUNT = 0
FULL_PAPER_EXPERIMENTS_RUN = false

HUMAN_DECISIONS_REQUIRED = M1_POSITIVE_TAIL_DECISION_REQUIRED; m1_v2_quantile_levels freeze; HORIZON implementation/final manuscript handling; Data2 factual replay availability rule; FAST/train artifact freeze

FINAL_STATUS = PASS_WITH_UPSTREAM_PRE_AND_SCIENTIFIC_DECISIONS_PENDING
```
