# B CU 2017 RETRY1 — 诊断记录（2026-10-13）

## 执行结果
- 命令（官方 `CLOUD_MULTIYEAR_EXECUTION_READINESS.md` §64 指定入口）：
  `python -m data2.scripts.build_year_references --years 2017 --output-root artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1 --continuity-contract JATM_F_CONTINUITY_B_V1`
- 运行记录：`b_cu_2017_retry1.log` / `.pid` / `.exitcode(=1)`（启动 2026-10-13T04:24:24Z，失败约 04:38Z）
- **原阻塞已被输入迁移解除**（逐项验证通过，以下均真实执行成功）：
  1. Y-H1 行流式读取与合法性门（rows=2711361，dropped=1；与首次失败运行逐字一致，确定性）
  2. 非物理轮转排除（2 个航班，2 轮链）
  3. `fit_train_references`（turnaround/exposure/passenger；含此前因 DB1B 缺失而失败的 passenger 参考）✓ 通过
  4. `fit_passenger_consequence_references`（T-100 MONTH<=6 + DB1B Q1+Q2）✓ 通过
  5. `compute_train_scales`（其余 5 个分量）✓ 通过
- **在最后一步 F_continuity（B 合同新增分量）失败**：
  `KeyError: 'scheduled_departure_utc'`，位置
  `model/PRE/reference/data2_m2_train_fit.py:515`（`compute_train_scales_continuity_b`）。

## 根因（代码缺陷，非输入问题）
- `compute_train_scales_continuity_b`（data2_m2_train_fit.py:483）第 515 行读取
  `successor["scheduled_departure_utc"]`（以及同式 `predecessor["actual_arrival_utc"]`）。
- 但该构建路径的唯一行源 `iter_train_rows`（同文件 :84；`collect_train_rows` :130 仅为其
  list 包装）产出的行契约**从不包含任何 `scheduled_*` 键**：
  调度时刻以 `event_start_time`（起飞）/`event_end_time`（到达）承载。
  （`scheduled_departure_utc` 键只存在于另一条流式路径
  `model/PRE/streaming/data2.py:301`，且仅在 `include_warning_fields=True` 时。
  `build_year_references.py` 不经过该路径。）
- 语义等价性证据：`model/PRE/canonical/normalization_flights.py:73/77` 中
  `"scheduled_departure_utc"` 与 `"event_start_time"` 均由同一 `schedule_dep` 赋值；
  `streaming/data2.py:291` 同样 `event_start_time = scheduled_departure`。
  即 `event_start_time` **就是** SOBT（计划离港 UTC）。
- 引入提交：`5f80e20 "Add versioned signed-time continuity contract"`
  （2026-10-13 00:52:53 +0800），是 HEAD `583f2c12` 的祖先——即本次云快照（本地/服务端
  内容一致，仅 CRLF/LF 行尾差异，剥离 CR 后 sha256 同为
  `4ba8b5e15d8ce5a13937d73edb6531deb8bfbf1fce9713494e8c1342418611ca`）必现。
- 从未被执行过的证据：全库（本地+服务端）无任何 `M2_DATA2_TRAIN_SCALES_B_V1` 产物、
  无 `*_B_V1` 参考束目录；B 合同的唯一测试 `tests/m2/test_jatm_continuity_b_v1.py`
  只覆盖 M2 后果服务语义（合成状态），不覆盖本函数与真实行。
- 影响范围：官方入口对所有年份 2017–2022 同样必现（`annual_cu.py` 仅为参考束的消费者，
  不存在绕过该构建器的合法产出路径）。

## 建议修复（未实施，需项目方授权）
- 最小补丁（语义完全不变）：`data2_m2_train_fit.py:515`
  `successor["scheduled_departure_utc"]` → `successor["event_start_time"]`。
- 备选：让 `iter_train_rows` 输出 `scheduled_departure_utc`/`scheduled_arrival_utc`
  键（改动行契约，波及面大，需更广评审）。
- 按项目规则，代码修改须经授权，且修改后需重发云快照（CODE_SNAPSHOT/source 归档哈希变更）。

## 状态保全
- 首次失败日志 `b_cu_2017.{log,pid,exitcode}` 原样保留（未覆盖）。
- 重试失败日志 `b_cu_2017_retry1.*` 保留。
- `M2_REFERENCES` 仍为空目录（失败未产生任何部分产物）。
- 未触碰 439 文件清单（`DATA_TRANSFER_MANIFEST.json` sha256
  `b0735bd93a3a0e75c0e1967c404531f6c842a2abe6134b2d0492228019b9fc82` 与其包内
  CHECKSUMS 一致）、未触碰 Test/Final-Test。
