# ROUND2_M1_V2_2_BEFORE — M1 Contract Correction 只读审计（Tranche 2.2）

- 日期: 2026-08-19
- REPOSITORY_HEAD: `8404e67dbcacd40bd8aaf7a1ea58a194012c2eb7`（与规格已知 SHA 一致）
- WORKTREE_STATUS: clean（审计全程只读，未改任何代码）
- 规格: `AIR_SLOT_ROUND2_M1_V2_2_CONTRACT_CORRECTION`（attachment e9181943）
- 范围: 仅 4 个 contract-correction 问题（A static/reference contract、B FAST discrete-hazard
  risk set、C common calibration contract、D fast/current-AR representation semantics）；
  不进入 PRE factual replay availability freeze、PRE static/reference publication、M2 七分量、
  RMB omega、Exp1-4、formal paper run
- FINAL_TEST_ACCESS_COUNT: 0

## 审计结论（只回答 4 个问题）

| 问题 | 状态 | 一句话原因 |
|---|---|---|
| STATIC_CONTEXT | CODE_STALE（且真实 static 字段 UPSTREAM_PRE_INTERFACE_REQUIRED） | `schedule.signed_minutes_to_crs_departure` 作为动态倒数同时进入 recurrent sequence 与 static branch（duplicated fusion），不是 manuscript 的 "separately retained static context"；route/carrier/aircraft/schedule-reference/turnaround/taxi 均未被 PRE 发布到 M1 |
| FAST_HAZARD | CODE_STALE | 每个 finite bin 的 binary classifier 在所有 valid rows 上拟合 `y = 1[T in bin k]`，不是 risk-set hazard；退化 bin 静默用零分类器 surrogate |
| CALIBRATION | CODE_STALE | `model/M1/calibration.py::fit_temperature` 是 multiclass cross entropy，不能用于 discrete-hazard logits；无 typed `M1CalibrationContract`；zero-mass 无明确 discipline；quantile calibration 状态未显式声明 |
| FAST_REPRESENTATION | CODE_STALE | `M1_FAST_FUSION_INTERPRETATION_REQUIRED` 无 manuscript 文本证据仍被保留；`r_fast` 未被定义为 deterministic current/AR feature block；STATE_AWARE 未消费 `r_fast` |

## 1. STATIC_CONTEXT = CODE_STALE（+UPSTREAM_PRE_INTERFACE_REQUIRED）

证据：
- `model/M1/data.py`：
  - `V2_STATIC_FIELDS = ("schedule.signed_minutes_to_crs_departure",)`；
  - `_v2_x_names()` 把同一 `schedule.signed_minutes_to_crs_departure` 放进每个 sequence row
    （DYNAMIC countdown，随 decision time 变化）；
  - `static_features_from_sequence()` 再从最后一个 causal row 抽出同一字段作为 "static" 输入
    → **同一个动态变量被 fused 两次**。
- `model/M1/network.py::M1V2GRU`：
  - `static_encoder = StaticContextEncoder(1, hidden)` 对该重复值做第二次线性投影；
  - `state_representation = concat(history, static_encoder(static))`；
  - 文档声称 `CONCAT_RECURRENT_STATIC` 已实现 manuscript static fusion → **假 closure**。
- `model/M1/contracts.py::M1V2StaticContext`：`supported_fields = ("schedule.signed_minutes_to_crs_departure",)`；
  route/aircraft/carrier/turnaround/taxi 全部 `SUPPORT_ABSTAIN`，且没有任何 typed
  reference-context contract（无 support_state / encoded representation / provenance id / freeze id）。
- `model/M1/lifecycle.py`：train / batched_logits 都调用 `static_features_from_sequence(values, lengths)`
  把该重复值传入 forward。
- `model/PRE/*` + `registries/scientific_variables.yaml`：
  - `schedule_reference`：FROZEN，data2 EMPIRICAL_REFERENCE（这是 DYNAMIC countdown 的来源，不是 static identity）；
  - `segment_reference`：DEVELOPMENT_FROZEN、DOMAIN_PROXY、仅 M2/M3 consumer（aircraft type unverified）→
    AVAILABLE_BUT_NOT_PUBLISHED_TO_M1；
  - `airport_reference`：FROZEN static（namespace mapping，无 aircraft/route identity context）；
  - route / carrier / turnaround reference / taxi reference / aircraft identity：
    无 M1 可消费的 canonical registry 条目 → NEEDS_PRE_REFERENCE_BINDING（taxi/turnaround 已有
    PRE reference objects `taxi.py`/`turnaround.py`，但只进入 label/scenario provenance，未发布为
    M1 encoder 输入 → AVAILABLE_BUT_NOT_PUBLISHED_TO_M1）。
- 结论：撤销 schedule countdown 的 static duplicate；STATIC_AWARE principal 回到
  recurrent + current-AR representation；建立 `M1StaticReferenceContext` typed contract +
  `M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`，全部真实 static 字段标
  UPSTREAM_PRE_INTERFACE_REQUIRED（`STATIC_REFERENCE_CONTEXT_PENDING_PRE`）。

## 2. FAST_HAZARD = CODE_STALE

证据（`model/M1/fast_path.py::LightGBMDistributionalPredictor.fit`）：
- 对每个 finite bin k：
  ```
  y = (ib_bin[ib_valid] == bin_index)
  model.fit(features[ib_valid], y)
  ```
  即所有 valid rows 都进入每个 bin 的分类器 → `h_k` 实际是
  `P(T in B_k | valid, x)`，不是正式离散 hazard `P(T in B_k | T >= start(B_k), x)`。
- 退化 bin（y 单类）时静默 `model.fit(features[ib_valid][:4], zeros(4))` —— 既不是 TEST_ONLY
  surrogate 的显式标记，也不改变统计定义，且没有 risk-set 概念。
- 下游 `loss.hazard_pmf` 已实现 `h_k * prod_{j<k}(1-h_j)` + survival tail（正确），但 FAST
  训练 semantics 与其不一致 → 需要 risk-set 训练 + 一致性测试。
- `model/M1/scenarios.py` 采样使用 `hazard_pmf(model.hazard_logits(state), hazard)`，因此
  FAST hazard logits 的语义直接决定 scenario 分布正确性。
- 结论：每 bin 按 risk set `R_k = {n: active AND remaining >= start(B_k)}` 训练；
  tail rows 保持 at-risk 但不产生 finite event；退化 risk set 仅允许 TEST_ONLY
  deterministic/constant surrogate（显式 fixture-only，principal 不静默替换）。

## 3. CALIBRATION = CODE_STALE

证据：
- `model/M1/calibration.py` 只有：
  ```
  fit_temperature(logits, labels, active, steps=50)
      -> F.cross_entropy(logits[active] / temperature, labels[active])
  ```
  这是 **mutually-exclusive class softmax** 校准；hazard logits 的每个分量是 conditional
  hazard，不是 class logit → 直接套用会破坏离散 hazard 语义。
- 无 hazard 专用校准（未通过 `hazard_pmf` / survival likelihood 做 event-time NLL）。
- 无 successor zero-mass calibration discipline（零概率的 temperature/calibration 策略未定义）。
- positive quantiles：无显式状态（manuscript 未冻结方法时应标
  `QUANTILE_CALIBRATION_NOT_APPLIED` + calibration-split coverage diagnostic，而非静默声称已校准）。
- 无 typed `M1CalibrationContract`（predecessor / successor_zero_mass / positive_quantile /
  split / version / final_test_access_count）。
- STATE_AWARE 与 FAST 没有共享 calibration policy 的强制契约。
- 结论：新增 `fit_hazard_temperature`（hazard chain → event-time NLL，calibration split only）；
  旧 `fit_temperature` 对 hazard logits 必须拒绝（`M1_HAZARD_MULTICLASS_CALIBRATION_FORBIDDEN`）；
  建立 `M1CalibrationContract`；zero-mass 有明确 discipline；quantile 状态显式
  `QUANTILE_CALIBRATION_NOT_APPLIED`。

## 4. FAST_REPRESENTATION = CODE_STALE

证据：
- `model/M1/contracts.py` / `network.py` 保留 `M1_FAST_FUSION_INTERPRETATION_REQUIRED`
  （fast-representation A/B 歧义 gate），但最新 manuscript Section 3–4 语义清晰：
  fast path "omits recurrent state and uses current/autoregressive representation directly"，
  state-aware path 同时保留 recurrent state 与 current/AR 信息 → 无文本歧义，gate 应撤销。
- `model/M1/fast_path.py::_arx_features` 把最后 `feature_window` 行（102 维 × window）flatten
  成 FAST "state" —— 是 full sequence 的第二次 flatten，不是 spec 6.3 要求的
  current-node + local-change + short-term AR deterministic block。
- `M1V2GRU.state_representation` 只 concat recurrent + (假) static，没有
  `projection(r_fast)`。
- `M1V2StaticContext.fusion = "CONCAT_RECURRENT_STATIC"` 未包含 fast block。
- 结论：定义 `r_fast = 最后一个 causal row 的 V2 特征组切片`（current X + Delta X + AR +
  masks + evidence/support + stage），deterministic、无需搜索；STATE_AWARE =
  `concat(history_repr, projection(r_fast), projection(static_repr if supported))`；
  FAST 直接消费 `r_fast`（+ static when available）进 LightGBM，不使用 GRU hidden。

## 5. 其他受控状态（本 tranche 不改）

- Tail / T_IB public-internal 分离 / marginal summary / FAST executable scaffold：保持
  Tranche 2.1 正确结果，不重开。
- `M1_POSITIVE_TAIL_DECISION_REQUIRED`、`m1_v2_quantile_levels`(DEVELOPMENT_ONLY) 保持。
- Horizon 文档状态将改为 `MANUSCRIPT_REQUIREMENT_CLEAR` /
  `CODE_LABEL_EXECUTION_CONTRACT_INCOMPLETE`（不再用 `MANUSCRIPT_AMBIGUOUS` 表述）。
- PRE scientific ownership 不修改；只新增 typed M1 input contract + PRE-required field list。
- 无 train-frozen V2 FAST artifact → principal FAST predict 保持 ABSTAIN。
- `FINAL_TEST_ACCESS_COUNT = 0`；`exp/` 不修改；无 commit/push。

## 6. 预期最终状态

`PASS_WITH_UPSTREAM_PRE_AND_SCIENTIFIC_DECISIONS_PENDING`：真实 static/reference 字段
UPSTREAM_PRE_INTERFACE_REQUIRED（下一 tranche PRE 发布），加上保留的 tail / quantile-levels /
horizon / factual-availability / FAST-artifact human gates。
