# ROUND2_TRANCHE3_M1_PRE_BEFORE — 第一轮真实执行路径审计

- 日期: 2026-08-19
- 规格: `AIR_SLOT_ROUND2_TRANCHE3_M1_PRE_INTERFACE_CLOSURE`（attachment 43646333）
- HEAD: `66002114d85e575f5b6a89bac545843949c08e59`
- 性质: 修改前审计记录。分类: ALIGNED / CODE_STALE / UPSTREAM_INTERFACE_STALE /
  SCIENTIFIC_DECISION_REQUIRED / HISTORICAL_ONLY。

## 1. 审计路径

canonical Data2 -> PRE records -> PRE mapper/publication -> PREState -> M1 sequence
-> r_fast -> M1 state representation -> heads -> calibration -> forecast -> ancestral scenario

## 2. 逐项发现

| 路径点 | 分类 | 问题 |
|---|---|---|
| `M1Service.predict_now(mode="state")` | CODE_STALE | 调 `predict_distributions(values, lengths)` 未传 `fast_features`；旧实现可能退化为 `concat(GRU, zero)` |
| `M1Pipeline.predict_distributions` | CODE_STALE | `fast_features=None` 时不自动推导 `r_fast`，生产与 scenario 路径可能消费不同信息状态 |
| `M1Lifecycle.calibrate` | CODE_STALE | 只拟合 hazard 温度；`fit_zero_mass_temperature` 定义但未接线 |
| `M1Pipeline.conditional_head_summary` | CODE_STALE | 若用单一 D_OB temperature 同时缩放 zero 与 quantile logits，违反 zero-mass 只作用 hurdle Bernoulli 的要求 |
| `fit_hazard_temperature` | CODE_STALE | 若对 inactive label=-1 调用 `contract.bin_start(-1)` 会触发 invalid bin access |
| FAST predictor | CODE_STALE | 无 development/calibration interface；D_TX parent 编码误用 D_TX 分钟值而非 formal D_OB parent |
| PRE `realized_operational_event` | UPSTREAM_INTERFACE_STALE | 一律 `posthoc_only / EVALUATION_ONLY`，未区分 "最终 realized outcome" 与 "decision time 已可见" |
| PRE pipeline | UPSTREAM_INTERFACE_STALE | 无 factual replay availability gate；无 static/reference publication |
| `FlightRecord` | UPSTREAM_INTERFACE_STALE | BTS `Reporting_Airline` 未正式保留为 `carrier_id`（只在 flight_id hash 内） |
| M1 static contract | UPSTREAM_INTERFACE_STALE | 六字段全部 `UPSTREAM_PRE_INTERFACE_REQUIRED`；M1 无法消费 PRE 发布内容 |
| `M1Pipeline._information_state` | CODE_STALE | 读取旧字段名 `static_reference_context`（实际应为 `static_reference_publication`） |
| `factual_observed_state` | CODE_STALE | D_TX 事实依赖调用方传 taxi reference，未从 PRE publication 读取同一冻结参考 |
| Data2 factual availability 数值规则 | SCIENTIFIC_DECISION_REQUIRED | 无真实 message-arrival 时间戳；需 human gate（UNRESOLVED 默认） |
| positive tail / quantile grid / horizon / FAST artifact | SCIENTIFIC_DECISION_REQUIRED | 保持 typed gate，本 tranche 不冻结 |
| V1 signed estimator | HISTORICAL_ONLY | `R_IB -> DELTA_OB -> T_TX` 仅 deserialize provenance |

## 3. 结论

所有非 human-decision blocker 均在本 tranche 直接修改（见 AFTER 文档）。
`FINAL_TEST_ACCESS_COUNT = 0` 保持。
