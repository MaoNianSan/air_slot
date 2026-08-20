# ROUND2_PRE_FACTUAL_REPLAY_CONTRACT

- 日期: 2026-08-20
- 规格: `AIR_SLOT_ROUND2_TRANCHE3_M1_PRE_FULL_CLOSURE` 第 4 节

## 1. 核心原则

"这是最终 realized outcome" 与 "它在当前 decision time 是否已经可见" 必须分开。
同一 `OperationalEventRecord` 可具有多个角色：

- A. `TRAIN_LABEL`（label construction；posthoc，无 inference role）
- B. `EVAL_OUTCOME`（evaluation；posthoc，无 inference role）
- C. `FACTUAL_REPLAY_EVIDENCE`（可进入 subsequent rolling state，
  仅当 `availability_time <= information_cutoff`）

未来 outcome 即使数据库里已存在，也必须被 cutoff filter 挡住。

## 2. Availability policy

Data2 archive 没有真实 airline-system message-arrival 时间戳；绝不自行宣称
event time 就是真实 production availability time。

`Data2FactualReplayAvailabilityPolicy`:
- `UNRESOLVED`：不启用 formal factual replay（当前 scientific config
  `data2_factual_replay_availability = UNRESOLVED` / `HUMAN_DECISION_REQUIRED`）；
  训练 label / evaluation outcome 继续正常存在。
- `DECLARED_RULE`：`availability_time = event_time + declared_lag`，
  必须显式声明规则；`availability_time <= information_cutoff` 才 legal。
  负 lag 被拒绝。

兼容输入 `DECLARED_RETROSPECTIVE_RULE` 保留为同义的明确回放规则。合法性边界
独立验证 `event_time <= cutoff` 与 `availability_time <= cutoff`，因此畸形的早到
availability timestamp 也不能使未来事件进入推断。

## 3. 状态收缩

PRE/M1 接口支持 upstream event 成为 legal fact 后收缩 unresolved stochastic state:

| stage | 固定 |
|---|---|
| PRE_IB | 无（全随机） |
| POST_IB_PRE_OB | T_IB_A00 |
| POST_OB_PRE_TO | T_IB_A00 + D_OB |
| COMPLETED | T_IB_A00 + D_OB + D_TX |

`observed` 只能由 `factual_observed_state(pre_state)` 产生（PRE typed factual state
派生）；`M1Service.generate_scenarios` 拒绝与该状态不一致的 caller 输入，M1 边界
复验 availability provenance。
public `T_IB_A00` 保留真实绝对 UTC event timestamp（R_IB=0 不丢弃 identity）。

## 4. No-leakage 测试点

A. outcome 在 archive 存在但 availability_time > cutoff => 不能进入 inference
B. 同 outcome 在 availability cutoff 之后 => 可进入 FACTUAL_REPLAY_EVIDENCE
C. label/evaluation role 不隐含 inference availability
D. 未来 WheelsOff/WheelsOn 在 availability 前不能泄漏
E. weather 仍遵守 event time + 5 min / max age 60 min
F. schedule reference 仍是 decision-visible reference

## 5. 接线文件

- `model/PRE/factual/availability.py`
- `model/PRE/factual/replay.py`
- `model/PRE/pipeline.py::ProductionPREPublisher.publish`
- `model/M1/factual_state.py`
- 测试: `tests/pre/test_tranche3_factual_static.py`、`tests/integration/test_tranche3_cross_stage_information.py`
