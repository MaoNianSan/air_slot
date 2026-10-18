# ROUND2_PRE_STATIC_REFERENCE_PUBLICATION

- 日期: 2026-08-20
- 规格: `AIR_SLOT_ROUND2_TRANCHE3_M1_PRE_FULL_CLOSURE` 第 5-8 节

## 1. 六字段

| 字段 | source/canonical | publication_status | model_feature_status |
|---|---|---|---|
| route_context | schedule origin/destination | MODEL_FEATURE_PENDING | MODEL_FEATURE_PENDING |
| carrier_context | FlightRecord.carrier_id（BTS Reporting_Airline） | MODEL_FEATURE_PENDING | MODEL_FEATURE_PENDING |
| aircraft_identity | Tail_Number registration | RETAINED_IDENTITY | RETAINED_IDENTITY |
| schedule_reference | CRS 时间 + semantics | RETAINED_IDENTITY | RETAINED_IDENTITY |
| turnaround_reference | 冻结参考（train-frozen） | MODEL_FEATURE（有 cell） | MODEL_FEATURE |
| taxi_reference | 冻结参考（train-frozen） | MODEL_FEATURE（有 cell） | MODEL_FEATURE |

- RETAINED_IDENTITY ≠ 必须 numeric embedding；本 tranche 只发布 identity/context。
- 禁止把 raw Tail Number 直接作为 ordinal float。
- decision-time countdown 属于 r_fast dynamic 字段；不重复进 static branch。
- 无 schedule（如 data1）或无可冻结 cell 时发布 ABSTAIN（reason_code），不伪造值。

## 2. 冻结参考

turnaround/taxi 只允许 train-frozen reference artifact。发布内容：
value / unit / reference_id / freeze_id / fallback_level / support_state / provenance。
禁止从 development/test 重新拟合。

M1 label construction 与 M1 static/reference input 必须引用同一 frozen reference
identity（lineage equality test: `test_25_taxi_label_input_freeze_lineage_identical`）。

## 3. M1 typed wiring

PRE 不 import M1；`PREState.static_reference_publication` 是 plain per-field dict
（publication_status / model_feature_status / provenance_reference_id / freeze_id）。
M1 通过 `static_reference_context_from_pre` 重建 typed `M1StaticReferenceContext`。
每个字段自含 value / unit / support_state / provenance / reference_id / freeze_id /
fallback_level；M1 只消费 PRE 已发布 + MODEL_FEATURE + 合法 reference/freeze
provenance 的字段。

- STATE_AWARE: `chi = concat(GRU(history), projection(r_fast), projection(c_static))`
- FAST: `concat(r_fast, c_static)`（ARX-LightGBM 在含 static block 的矩阵上拟合）
- 无新架构搜索：H=32，`IMPLEMENTATION_CHOICE_NO_SEARCH`。

## 4. 文件

- `model/PRE/publication/static_reference.py`
- `model/PRE/mapping.py`（schedule canonical 含 carrier/aircraft id）
- `model/PRE/canonical/normalization_flights.py`（FlightRecord.carrier_id）
- `model/M1/contracts.py::static_reference_context_from_pre`
- `model/M1/data.py::static_reference_features_from_pre`
- `registries/scientific_variables.yaml`（六新变量，consumers=[M1]）

连接机场规则：turnaround lookup 使用 successor origin（亦即 predecessor
destination）；taxi lookup 使用 successor origin。二者均复用 PRE 已发布的冻结
lineage，scenario provenance 不要求调用方再次注入 reference object。
