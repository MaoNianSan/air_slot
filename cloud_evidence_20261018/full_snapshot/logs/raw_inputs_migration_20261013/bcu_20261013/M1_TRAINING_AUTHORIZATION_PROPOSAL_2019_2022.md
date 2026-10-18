# M1 Training Authorization Proposal 2019–2022（第三轮任务 E · 提案，非授权）

**当前状态：NOT_APPROVED。本提案不构成授权；不得据此启动训练。**
授权须由用户在独立受控记录上以 `status=USER_APPROVED` + `years=[...]` 明确批准
（`cloud_train_models.validate_authorization` 会拒绝其他任何状态）。

## 1. 拟训练范围

| 项 | 值 |
|---|---|
| 年份 | 2019、2020、2021、2022（2017/2018 已有模型，不得重训） |
| N | 4096（不扩大；train=4096 集、calibration=2048 集，与 2017/2018 完全一致） |
| 角色 | `M1_HISTORY_PRIMARY`（FULL_ADAPTIVE_CAUSAL_PREFIX）、`M1_CURRENT_COMPARATOR`（NO_HISTORY_CURRENT_OBSERVATION） |
| 训练分区 | Train=月份 1–6；Calibration=月份 7；Development 不参与拟合（`development_used_for_fit=false`） |
| Final-Test | `final_test_access_count=0`；不读取任何 Test/Final-Test 分区 |
| 模型结构/参数来源 | 与 2017/2018 同一代码路径与科学配置层（`configs/`，`annual_models.build_annual_models`）；不改结构、不改损失、不改样本 |
| 输入 | `data2/reports/cohort_size_stability/{year}/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl`（每年 12,288 行 = 4096×3 分区；已核验在云端存在且 counts/dedup/窗口通过 `check_year`） |
| 现存前置 | PRE 参考束（LEGACY + B 双轨）已全部就位；M1 训练本身不读取 v5 冻结区（已核对 `annual_models`/`annual_development` 无 v5 依赖）；registry 冻结字节修复后 `registry_hash=befc3ae1…` 与历史一致 |

## 2. 输出对象与校验链

每年产出（隔离目录，拒绝覆盖）：
`artifacts/models/m1/YEAR_{year}/`：`M1_HISTORY_PRIMARY.pt` + `_MANIFEST.json`、
`M1_CURRENT_COMPARATOR.pt` + `_MANIFEST.json`、`ANNUAL_M1_TRAINING_RECEIPT.json`。

执行命令（**仅授权后**）：
`python -m exp.jatm_s34.cloud_train_models --year <Y> --approval <approved record>`

校验链（缺一不可）：
1. `validate_authorization`（schema/status/n/roles/months/fta=0）；
2. 训练后 `model_bindings(year)`：schema `JATM_ANNUAL_M1_RUNTIME_V1`、epoch 计数、
   history 模式、checkpoint sha256 == manifest、`final_test_access_count=0`、
   `m5b_n128_pilot_reused is False`；
3. `check_year(year, require_tail=False, B)` 变为 `INPUTS_VALIDATED`；
4. 每年 Tail（决策已覆盖 2019–2022）随后补算，补完后 `check_year` 全字段通过。

## 3. 算力预算与执行协议（measure-first）

- 真实基准仅有两类：B CU（单核 99%、峰值 13.3–23.4 GiB、11.6–19.3 min）与
  tail_2018（2.7 GiB、37.7 min）。**M1 训练无实测**，不得假设其与 B CU 同型。
- 首年（2019）单任务先跑，记录 wall、峰值 RSS、CPU、I/O；据此选择后续并发：
  - 方案 A：逐年串行（最稳）；
  - 方案 B：2 年并发；
  - 方案 C：4 年并发（仅在单任务峰值 RSS ≤ ~12 GiB 且磁盘 I/O 有余量时）。
- 任何方案保持 ≥20 GiB 内存余量、单任务=1 逻辑核不超订（OMP/MKL/OPENBLAS/NUMEXPR=1，
  或按实测决定 torch 线程数）；不同年份使用独立输出目录，禁止同年并发写。
- 串行估算（仅作排程上限，不作承诺）：若单年 ≤20 min，则 4 年串行 ≤~80 min；
  并发 2 约减半。

## 4. 可审计性

- 本提案文件、批准记录（若批准）及其 sha256 必须同时归档于
  `/data/airslot/logs/raw_inputs_migration_20261013/` 与本地镜像；
- 授权草稿：`M1_TRAINING_AUTHORIZATION_DRAFT_2019_2022.json`（当前 `NOT_APPROVED`）。
  批准流程 = 复制该草稿 → 仅改 `status/years` → 计算 sha256 → 在受控位置归档；
- 用户对云算力的一般性许可**不构成**年度训练授权。

## 5. 风险与边界

- 不重训 2017/2018；不改 N/结构/损失；不动 Test；不因训练失败放宽任何合同；
- 若 `model_bindings` 或 `check_year` 任一环节失败 → 停止该年，保留日志与 receipt，
  不生成"补写"模型；
- 若训练需要任何超出上述范围的代码/配置变更 → 停止并提科学决策请求。
