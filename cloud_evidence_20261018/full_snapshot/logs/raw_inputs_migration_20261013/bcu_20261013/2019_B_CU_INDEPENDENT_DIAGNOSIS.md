# 2019 B CU 独立诊断书（第三轮任务 A）

日期：2026-10-13。方法：不看上一轮结论，独立从代码行级归因（git blame/diff）、全部调用方、
历史产物数值比对与官方接受性合同取证。

## 结论（先行）

2019 Year-local B CU（B 合同，year-replicated 构建器）的失败**不是"2019 特例该删"的问题**，
而是 **3f27f6e9（2026-10-11）在同一提交内写下了两处互相矛盾的约定**：

- 构建器给**所有年份**的行盖共享身份 `data2_2017_2022`（data2/scripts/build_year_references.py:167）；
- 但 `fit_train_references` 对 `year == 2019` 期望 `data2_2019`
  （data2_m2_train_fit.py:674 → turnaround:675-677 / exposure:678-680）。

→ 2019 行(2017_2022) ≠ 期望(2019) → `REFERENCE_DATASET_MISMATCH`（turnaround_data2.py:182）。
该期望对 **legacy 调用方**（`model/M2/cu/registry.py:464-470`，其行由 `iter_train_rows` 默认
盖 `data2_2019`）是**正确的**；只对 year-replicated 构建器（行=2017_2022）错误。
修复方向=**显式区分构造上下文**，不删除 year==2019 判断。

## 逐项核查记录

### 1. build_year_references 的身份与年份参数
- `INSTANCE_ID = "data2_2017_2022"`（:55）；`iter_train_rows(..., dataset_instance_id=INSTANCE_ID)`（:167）；
  `fit_train_references(rows, root, fit_period=f"{year}-H1", year=year)`（:217）；
  输出经 `normalize()`（:73-83）统一重盖 bundle 级身份与 correction-8 字段。
- 行盖参数由 **3f27f6e9** 引入（blame 已证）；此前行为 yield `schedule.dataset_instance_id`（恒为
  data2_2019，因 `canonicalize_ontime_row` 硬编码，normalization_flights.py:53）。

### 2. collect_train_rows / iter_train_rows 行合同
- `collect_train_rows = list(iter_train_rows(...))`；行含 15 键：dataset_instance_id、aircraft_id(_namespace)、
  flight_id、canonical_record_id、origin/destination_airport_id、event_start_time/event_end_time、
  actual_arrival/departure_utc、taxi_out_minutes、carrier_id、month、split。**身份唯一来源=显式参数**
  （默认 `data2_2019`=legacy 兼容，iter_train_rows:88）。

### 3. fit_train_references 四路径
| 参考 | 行来源 | 身份期望 | 2019 实况 |
|---|---|---|---|
| turnaround | rows(构建器盖 2017_2022) | `reference_dataset_id`（:674，2019→data2_2019） | ✗ 冲突→崩溃 |
| downstream_exposure | rows | 同上（:678） | ✗ 同 |
| passenger | `stream_passenger_routes` 自盖（年基表达式, :241） | 年基表达式（:694） | ✓ 两侧同为 data2_2019，自洽 |
| taxi | 2019=读 v5 冻结文件；其余=从 rows 重拟合（:700-714） | — | 停滞于 turnaround，未到 |

### 4. Legacy 2019 与 Year-local 2019 的实际调用关系
- **Legacy**：`model/M2/cu/registry.py`（M2 V4 CU registry 物化）→ `build_data2_m2_train_preparation`
  （行默认 data2_2019）→ `fit_train_references`（无 year 参数→2019 默认）→ 期望 data2_2019 ✓ 自洽；
  该路径在 3f27f6e9 前后均自洽（这也是行 670-673 注释所称"frozen 2019 reference path"）。
- **Year-local**：`data2/scripts/build_year_references.py`（E4/D4 束）→ 唯一会崩的调用方。
- 归因链：c0e3de62（10-03，M5 年参数化）引入 `year` 参数、passenger 年基身份、2019 taxi 分支；
  3f27f6e9（10-11）引入行盖身份 + turnaround/exposure 年条件 + 非 2019 taxi 重拟合。
  3f27f6e9 随后在 M5-b 六年度实验（10-02/03 使用旧行为）之后从未成功跑过 2019。

### 5. 2019 Taxi Reference 来源
- 现役代码 2019 → `artifacts/diagnostics/v5_development_freeze/DATA2_TAXI_REFERENCE_TRAIN_FROZEN_V1.json`。
- 数值比对（本地）：v5 文件 ≡ `PRE_MULTIYEAR_V1/2019` 冻结 taxi（349 cells 全部一致，global=15.0；
  仅 provenance 标签多一个 `BTS_SIGNED_DELAY_SEMANTIC_CORRECTION`、fit_period 标签
  "2019-01..2019-06" vs "2019-H1" 不同）。
- R1/2019 bundle 的 taxi payload `reference_id = sha256:7e304a84…` **与 v5 文件完全相同**
  （若读 PM19 则应为 be1a68b0…）→ 历史 year-local 2019 用的就是 v5 内容。保持该来源=既定先例。
- 附：非 2019 的"重拟合 vs 旧 PM 文件"数值差（以 2018 实测）：数值 0 差异、cells 全同、仅 LGA 一格
  sample_count 不同 → 3f27f6e9 的重拟合是元数据卫生性改动，非估计量变化。

### 6. 2019 参考对象的 provenance / identity / 下游接受性
- bundle 级身份由 `normalize()` 统一为 data2_2017_2022 + experiment_year 2019 + fit 窗口
  2019-01-01..06-30 + YEAR_SPECIFIC_H1_M2_REFERENCES_V1 + JATM_F_CONTINUITY_B_V1。
- 内部 builder 的 dataset_instance_id **只进入 reference_id/artifact_hash 的内容哈希**，不进入任何数值。
- 下游 `load_annual_cu(YEAR_LOCAL/2019, B)` 的硬校验：manifest/scales/六参考哈希重算、**turnaround 数值
  必须等于 `PRE_MULTIYEAR_V1/2019` 冻结 turnaround**（349 cells, global 57.0，已确认存在）、principal
  scales 正支撑；**无任何校验要求内部身份为 data2_2019**。

### 7. R1/2019 参考束（身份/时间范围/用途）
- `PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1/2019`，created 2026-09-30T05:57:45Z，LEGACY_A 时代
  （无 continuity_contract 字段）；bundle 身份（normalize 后）data2_2017_2022；内部行/参考为
  年参数化前的 data2_2019 约定；taxi=v5 内容；fit 窗口 2019-H1。
- 用途：E4/YEARLOCAL 的 R1（revision-1）轨道束，由 LEGACY_A_V1 的 annual_cu 消费。
- **不可与将建的 B/2019 混同**：连续合同不同（LEGACY_A vs B）、内部身份约定与 taxi 元数据不同；
  两者仅共享"年份=2019"这一标签。

### 特别确认：B 合同是否要求按年重新拟合 Taxi？
冻结现状（c0e3de62 注释 + 3f27f6e9 改动 + R1 实践）为：**非 2019 年份=从 H1 Train 行重拟合；
2019=指定使用 v5 冻结件**。该例外有明确注释、历史先例与用户本轮指令背书（"不将 2019 的旧 Taxi
Reference 擅自替换为重新拟合的参考"）。且数值上 v5≡PM19。→ 维持现状，**无需任何科学变更**。

## §一 环境复核中的两个额外发现（已处置/在案）

1. **云端缺失 v5 taxi 冻结文件**（未被 439 清单覆盖，`artifacts/diagnostics/v5_development_freeze`
   被 .gitignore；2019 代码硬依赖）→ 已按输入补齐流程上传并校验：
   `sha256:12ca5e93a6f6f0dcfc0dfe217a14a132fea93811ecef94875a4042025a0d5b34`。属输入完整性，非代码/科学变更。
2. 2019 构建的其他输入已确认在位：PM19 turnaround（annual_cu 数值对照用）、2019 cohort、DB1B、
   H1 T-100（封存后）。

## 修复授权边界自检

- 不改数据筛选、七项 consequence、F_continuity 公式、归一化定义 ✓（只加身份参数路由）
- 不改 2019 taxi 来源 ✓；不触碰 Development/Test ✓；不重算任何已 PASS 参考 ✓
- Legacy 2019（registry.py 调用约定）行为不变 ✓；其他年份不变 ✓
→ 属"Legacy 与 Year-local 路径未正确区分"的限定范围工程修复，可实施。
