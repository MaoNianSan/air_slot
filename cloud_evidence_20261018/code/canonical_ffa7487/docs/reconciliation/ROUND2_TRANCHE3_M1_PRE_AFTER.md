# ROUND2_TRANCHE3_M1_PRE_AFTER — 修改与验证记录

- 日期: 2026-08-19
- 规格: `AIR_SLOT_ROUND2_TRANCHE3_M1_PRE_INTERFACE_CLOSURE`（attachment 43646333）
- 性质: 修改后记录；不冻结论文参数，不进入 M2。

## 1. M1 execution closure

- `model/M1/pipeline.py::_information_state`：`fast_features=None` 时自动
  `fast_features_from_sequence(values, lengths)`（生产路径不再退化为 zero block）；
  生产预测与 scenario generation 消费相同 `h + r_fast (+ c_static)`。
- `fit_hazard_temperature`：只把 ACTIVE label 转 bin interval；inactive(-1) 行零影响。
- `M1Lifecycle.calibrate`：接线 `fit_hazard_temperature`（event-time NLL）+ D_OB_ZERO /
  D_TX_ZERO（binary CE）。temperature registry 区分
  `M1_TEMPERATURE_HAZARD / M1_TEMPERATURE_D_OB_ZERO / M1_TEMPERATURE_D_TX_ZERO`。
- `conditional_head_summary` / `ancestral_sample_v2`：zero-mass temperature 只缩放
  hurdle Bernoulli zero logit；quantile values/logits 永不被 zero-mass temperature 缩放。
- FAST：`calibration_policy()` 与 STATE_AWARE 共享 `M1CalibrationContract`；
  `calibrate_development` 拟合 hazard + D_OB_ZERO + D_TX_ZERO（per-estimator 数值可不同，
  科学 procedure 相同）；D_TX parent 现在从 `d_ob_target` 编码（formal D_OB parent）。
- FAST static parity：`fit(..., static_features=...)` 使模型在
  `concat(r_fast, c_static)` 上拟合；缺失 static block 显式报错，不静默补零；
  新增 `predict_from_pre`（与 STATE_AWARE 相同的 PRE 接口）。

## 2. PRE factual-role architecture

- `model/common/enums.py`：`DecisionTimeRole.FACTUAL_REPLAY_EVIDENCE`、
  `AvailabilityBasis.FACTUAL_REPLAY_RULE`。
- `model/PRE/factual/availability.py`：`Data2FactualReplayAvailabilityPolicy`
  （UNRESOLVED / DECLARED_RULE）、`factual_availability_time`、
  `factual_replay_legal`（availability_time <= information_cutoff）。
- `model/PRE/factual/replay.py`：`publish_factual_replay` —— 同一 source record 多角色
  （TRAIN_LABEL / EVAL_OUTCOME / FACTUAL_REPLAY_EVIDENCE），不复制/伪造实际值，
  cutoff 不合法则不发布。
- `model/PRE/pipeline.py`：ProductionPREPublisher 接线 factual replay +
  static/reference publication；`ProductionPRERequest` 增加
  `factual_availability_policy` / `factual_replay_declared_lag_minutes` /
  `taxi_reference` / `turnaround_reference`。
- `model/M1/factual_state.py`：`factual_observed_state(pre_state)` —— observed 只由
  PRE typed factual state 派生，逐项复验 availability <= cutoff；保留绝对 `T_IB_A00`；
  COMPLETED 阶段 D_TX 从 PRE 发布的同一 taxi reference 推导。

## 3. PRE static/reference publication

- `model/PRE/publication/static_reference.py`：六字段 typed publication
  （route/carrier/aircraft/schedule/turnaround/taxi）。RETAINED_IDENTITY 不进 numeric
  block；turnaround/taxi 冻结参考进入 `c_static`。无 schedule / 无冻结 cell 时发布
  ABSTAIN（reason_code），绝不伪造 SUPPORTED-with-None。
- `FlightRecord.carrier_id`（BTS Reporting_Airline）、`schedule_reference` canonical
  含 `carrier_id` / `aircraft_id` / `aircraft_id_namespace`。
- registry：`realized_operational_event` 1.1.0（consumers `[EVALUATION_ONLY, M1]`、
  `factual_replay_support: HUMAN_GATE`）；六新变量为 M1 consumer；manifest 重新生成
  （`sha256:e8315fe8953d35dec58d33a13c9cc2631cb04c80ecbd8417b6e372a1aa1750e0`）。

## 4. M1 final typed wiring

- `model/M1/contracts.py::static_reference_context_from_pre`：从
  `PREState.static_reference_publication` 重建 typed `M1StaticReferenceContext`。
- `pipeline._information_state` / `predict_from_pre` / `sample_from_pre` 全部经此接线；
  只消费 PRE 已发布 + MODEL_FEATURE + 合法 reference/freeze 的字段。
- STATE_AWARE `chi = concat(GRU(history), proj(r_fast), proj(c_static))`；
  FAST `concat(r_fast, c_static)`。

## 5. 验证

- 新增测试: `tests/m1/test_tranche3_execution.py`（12）、
  `tests/pre/test_tranche3_factual_static.py`（18）、
  `tests/integration/test_tranche3_cross_stage_information.py`（7）—— 覆盖规格 §14 全部 35 项。
- `FINAL_TEST_ACCESS_COUNT = 0`；无 full paper run；exp/ 未改。
- 尾部/quantile/horizon/FAST artifact 保持 typed gate。

## 6. 状态

M1 estimator architecture + M1 production execution + PRE->M1 information interface
可暂时冻结结构。下一步才是 M2 seven-component V2（本 tranche 不开始）。
