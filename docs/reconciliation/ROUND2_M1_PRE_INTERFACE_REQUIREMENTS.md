# ROUND2_M1_PRE_INTERFACE_REQUIREMENTS — M1 static/reference fields required from PRE

- 日期: 2026-08-19
- 规格: `AIR_SLOT_ROUND2_M1_V2_2_CONTRACT_CORRECTION`（attachment e9181943，第 7 节）
- 性质: typed M1 input contract + PRE-required field list。本 tranche 只建立接口契约，
  不实现 PRE publication，不修改 PRE scientific ownership。

## 1. 契约对象

`model/M1/contracts.py::M1StaticReferenceContext` 与
`M1_STATIC_REFERENCE_FIELDS_REQUIRED_FROM_PRE`。

每项字段结构：
- `value` / `unit` / `support_state`；
- `pre_status` / `publication_status` / `model_feature_status`；
- `provenance` / `reference_id` / `provenance_reference_id` / `freeze_id` /
  `fallback_level`。

## 2. 字段清单与 PRE 状态（Tranche 3 已发布）

| 字段 | publication_status | model_feature_status | provenance |
|---|---|---|---|
| `route_context` | PUBLISHED / MODEL_FEATURE_PENDING | MODEL_FEATURE_PENDING | schedule_reference |
| `carrier_context` | PUBLISHED / MODEL_FEATURE_PENDING | MODEL_FEATURE_PENDING | schedule_reference (FlightRecord.carrier_id) |
| `aircraft_identity` | PUBLISHED / RETAINED_IDENTITY | RETAINED_IDENTITY | schedule_reference (REGISTRATION) |
| `schedule_reference` | PUBLISHED / RETAINED_IDENTITY | RETAINED_IDENTITY | schedule_reference |
| `turnaround_reference` | PUBLISHED / MODEL_FEATURE | MODEL_FEATURE | 冻结参考 reference_id + freeze_id |
| `taxi_reference` | PUBLISHED / MODEL_FEATURE | MODEL_FEATURE | 冻结参考 reference_id + freeze_id |

注意：AVAILABLE_BUT_NOT_PUBLISHED_TO_M1 已被 Tranche 3 PRE publication 取代；
无 schedule / 无冻结 cell 时 PRE 发布 ABSTAIN（reason_code），绝不伪造值。
`UNSUPPORTED` 仅用于 PRE 确认无 canonical 路径的字段（当前无）。

## 3. Tranche 3 已发布（2026-08-19）

1. decision-time factual replay（`Data2FactualReplayAvailabilityPolicy`，UNRESOLVED 默认）；
2. route / carrier / aircraft retained identity/context；
3. schedule reference context；
4. turnaround reference publication；
5. taxi reference publication。

详见 `ROUND2_PRE_FACTUAL_REPLAY_CONTRACT.md` 与 `ROUND2_PRE_STATIC_REFERENCE_PUBLICATION.md`。

## 4. M1 侧接线（Tranche 3 已完成）

- `PREState.static_reference_publication`（plain dict，PRE 不 import M1）->
  `static_reference_context_from_pre` 重建 typed `M1StaticReferenceContext`
  （`support_state -> SUPPORTED`、`provenance_reference_id` / `freeze_id` 填充）。
- 只有 PRE 发布 + MODEL_FEATURE + 合法 reference/freeze provenance 的字段进入
  `c_static`；STATE_AWARE `chi = concat(GRU(history), projection(r_fast), projection(c_static))`，
  FAST `concat(r_fast, c_static)`。
- M1 不得绕过 PRE 直接读取 BTS/raw/reference 文件。
- RETAINED_IDENTITY（episode identity / provenance / lineage / routing lookup）不进入
  numeric embedding；无 ordinal encoding 被发明（MODEL_FEATURE_PENDING 保持 typed）。
