# ROUND2_M1_PRE_INTERFACE_REQUIREMENTS — M1 static/reference fields required from PRE

- 日期: 2026-08-19
- 规格: `AIR_SLOT_ROUND2_M1_V2_2_CONTRACT_CORRECTION`（attachment e9181943，第 7 节）
- 性质: typed M1 input contract + PRE-required field list。本 tranche 只建立接口契约，
  不实现 PRE publication，不修改 PRE scientific ownership。

## 1. 契约对象

`model/M1/contracts.py::M1StaticReferenceContext` 与
`M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`。

每项字段结构：
- `support_state`：M1 侧支持状态（当前全部 `UPSTREAM_PRE_INTERFACE_REQUIRED`）；
- `pre_status`：PRE 发布状态分类；
- `provenance_reference_id` / `freeze_id`：PRE 发布后填充。

## 2. 字段清单与 PRE 状态

| 字段 | pre_status | 依据 |
|---|---|---|
| `route_context` | NEEDS_PRE_REFERENCE_BINDING | 无稳定 Data2 canonical registry 条目；需 PRE 绑定 route/segment 参考对象 |
| `carrier_context` | NEEDS_PRE_REFERENCE_BINDING | 同上 |
| `aircraft_identity` | AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 | `segment_reference`（DEVELOPMENT_FROZEN，DOMAIN_PROXY，aircraft type unverified）已存在但仅 M2/M3 consumer |
| `schedule_reference_context` | AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 | `schedule_reference` 已 FROZEN（data2 EMPIRICAL_REFERENCE）；但 M1 只消费其 DYNAMIC countdown，schedule identity/reference context 未作为 typed static 发布 |
| `turnaround_reference` | AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 | PRE `reference/turnaround.py` 参考对象已存在；只进入 label/scenario provenance，未发布为 M1 encoder 输入 |
| `taxi_reference` | AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 | PRE `reference/taxi.py` 参考对象已存在；只进入 label/scenario provenance，未发布为 M1 encoder 输入 |

注意：AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 绝不误记为 UNSUPPORTED。
`UNSUPPORTED` 仅用于 PRE 确认无 canonical 路径的字段（当前无）。

## 3. 下一 tranche（PRE FACTUAL + STATIC/REFERENCE PUBLICATION）必须发布

1. decision-time factual replay（Data2 factual availability rule）；
2. route / carrier / aircraft retained identity/context；
3. schedule reference context；
4. turnaround reference publication；
5. taxi reference publication。

## 4. M1 侧接线前置条件

- PRE 发布后：每项字段通过 typed reference object 进入 M1
  （`M1StaticReferenceContext` 对应项的 `support_state -> SUPPORTED`、
  `provenance_reference_id` / `freeze_id` 填充），然后 M1 才允许设计 deterministic encoding
  contract 并将其作为 MODEL_FEATURE 参与
  `state = concat(GRU(history), projection(r_fast), projection(static_repr if supported))`。
- M1 不得绕过 PRE 直接读取 BTS/raw/reference 文件。
- RETAINED_IDENTITY（episode identity / provenance / lineage / routing lookup）不需要
  numeric embedding；只有 PRE 发布后的 MODEL_FEATURE 才进入 estimator。
