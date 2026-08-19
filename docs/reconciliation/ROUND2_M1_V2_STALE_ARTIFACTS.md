# ROUND2_M1_V2_STALE_ARTIFACTS — M1 V1 历史工件与状态清单

- 日期: 2026-08-19
- 目的: 区分 V2 principal 语义与 V1/HISTORICAL_ONLY 工件，防止旧输出被当作当前科学证据
- 原则: 不删除冻结工件；V1 工件与语义只保留 provenance/历史测试角色，不重新作为 principal 运行

## 1. V1 工件（HISTORICAL_ONLY）

| 工件 | 路径 / 位置 | 状态 | 说明 |
|---|---|---|---|
| M1 signed warning model | `artifacts/diagnostics/v5_development_freeze/M1_SIGNED_WARNING_MODEL_V1.pt` | HISTORICAL_ONLY | V1 冻结 warning artifact；只读保留，`M1Pipeline.load` 仍可反序列化用于 provenance，`sample_from_pre` 拒绝 V1 模型 |
| V1 warning manifest | `artifacts/diagnostics/v5_development_freeze/M1_SIGNED_WARNING_MODEL_V1_MANIFEST.json` | HISTORICAL_ONLY | 同源 manifest |
| V1 signed H/W 证据 | `artifacts/diagnostics/v5_development_freeze/m1_signed_hstar_evidence.json`、`m1_signed_wstar_evidence.json` | HISTORICAL_ONLY | V1 选择证据；V2 不沿用其 principal 结论 |
| V1 scenario artifacts | `tests/m1/test_exp234_scenario_artifact.py`、`tests/m1/test_wstar_development.py` | HISTORICAL_ONLY | 冻结 artifact 校验测试，保持通过 |
| V1 `AlignedScenario` 派生量 | `tests/m1/test_signed_ob_contract.py::test_legacy_*`、`tests/reconciliation/test_m1_joint_identity.py` LEGACY 断言 | LEGACY_V1 | signed DELTA_OB -> R_OB/D_TO 重建仅作历史契约 |

## 2. V1 语义代码（保留为 LEGACY_V1，不再 principal）

| 模块 | 保留内容 | 角色 |
|---|---|---|
| `model/M1/contracts.py` | `TargetBinContract`、`AlignedScenario`、`STOCHASTIC_TARGETS` | LEGACY_V1 / HISTORICAL 消费方 |
| `model/M1/semantics.py` | `derived_d_ob_minutes`、`derived_d_tx_minutes`、`derived_d_to_minutes`、`total_takeoff_delay_minutes` | LEGACY_V1 派生 helper |
| `model/M1/network.py` | `OrderedEventGRU` | LEGACY_V1 反序列化 |
| `model/M1/scenarios.py` | `_uniform`、`aligned_sample`、`ancestral_sample`、`_required_observations` | LEGACY_V1 sampler |
| `model/M1/target_builder.py` | `build_target_labels`、`build_data2_target_labels` | LEGACY_V1 标签构造 |
| `model/M1/data.py` | `MOTION_FIELDS`、`FEATURE_NAMES`（103 维） | LEGACY_V1 特征组 |
| `model/M1/pipeline.py` | `V1_TO_V2_SUPPORT` 映射；`load` 的 V1 分支 | provenance/迁移桥 |

## 3. Config 旧条目

| 参数 | 状态 | 迁移说明 |
|---|---|---|
| `m1_stochastic_targets=[R_IB, DELTA_OB, T_TX]` | FROZEN，role=LEGACY_V1 | 保留 provenance；不可再描述为 principal V2 目标 |
| `m1_fixed_history_window_minutes=30` | SENSITIVITY_ONLY | V1 sensitivity artifact；V2 principal history 为 FULL_ADAPTIVE_CAUSAL_PREFIX |
| `m1_delta_ob_min_finite_minutes=-180` | FROZEN（V1 signed support） | V2 不再有 signed support；D_OB 非负，support 上限复用 `m1_delta_ob_max_finite_minutes=180` |
| `m1_warning_model_artifact` | FROZEN（V1 路径） | V1 warning artifact；V2 warning 只消费 formal V2 scenario |

## 4. 禁止事项（V2 之后）

- 不把 V1 `AlignedScenario` 的 signed D_TO 重建当作 V2 警告/评估证据
- 不把 `m1_stochastic_targets` 或 30 分钟固定窗口描述为 principal
- 不重新运行 Exp1 以"复现"V1 warning（warning 仅消费 V2 formal scenario）
- 不静默虚构 crew/gate/slot/standby 等未实现输入（SUPPORT_ABSTAIN 记录）
- 不伪造 `tau={0,15,60}` 维度（`HORIZON_SEMANTICS_DECISION_REQUIRED` 保持）
