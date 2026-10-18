# CALIBRATION_REPORT_V1（R7，2026-10-13）— E1/E2E3 chunk 扩展 + E4 N 扩展

> PILOT/CALIBRATION 性质，非论文结论。仅含执行时间/内存/吞吐/检查点稳定性/失败诊断。授权：`CALIBRATION_EXECUTION_AUTHORIZATION_V1.json`（USER_APPROVED；DEVELOPMENT_ONLY；fta=0；禁 full/禁 Final-Test/零代码变更/不重生已产输入）。全部输出位于 `artifacts/experiment/jatm_s34/calibration_20261013/`。

## 1. 测量结果总表（全部真实运行，year 2019）

| 运行 | 配置 | wall | 峰值 RSS | 结果 | 关键分解 |
|---|---|---|---|---|---|
| E1 c4（R6 基线） | 128, chunk=4 | 38:34 | 3.50 GiB | PASS | 32 块 → 块阶段 35:56 |
| **E1 c64** | 128, chunk=64 | **4:47.75** | 3,725,996 KB (3.55 GiB) | **PASS** | 2 块；chunk 阶段 2:44；bootstrap+汇总 1:19 |
| E2/E3 c4（R6 基线） | 128, chunk=4 | 74:23 | ≥3.92 GiB | PASS | 32+32 块 |
| **E2/E3 c64** | 128, chunk=64 | **6:57**（12:43:57→12:50:54） | ≥2.82 GiB（采样；time_v 被重复启动截断，已披露） | **PASS** | pass1 3:34.7 / pass2 2:31.7 / **bootstrap+E3+序列化 ≤50.1s**；2+2 块 |
| E4 N=128（R6） | n_grid=(128) | 30:19 | 13.55 GiB | 四阶段+设计性硬停止 | headroom 5:58 / fit 76.8s+开销 / ladder 1:37 / eval 21:24 |
| **E4 N=256** | n_grid=(256) | **30:41 累计**（尝试1 7:30 + 续跑 23:10.67） | 5.24 GiB（attempt2） | 四阶段+设计性硬停止（`PILOT_COMPLETE_HARD_STOP`，failed_instances=[]） | headroom 5:55 / fit 82.3s/train / ladder 1:37 / **eval 21:26** |

## 2. chunk 扩展结论（Task B/C 判定）

两点模型（T(c) = n_chunks·F + n_items·I）解出：**每块固定开销 F≈62–67 s；每 item 增量 I≈0（在测量精度内）**。即 c4 的 38:34/74:23 几乎全部由 32（或 64）块 × ~65 s 的**块级固定成本**（authorities/service/bridge 逐块构建）构成。

- **E1 full（chunk=64，默认）**：64 块 → **≈65–70 min/年**（+ bootstrap ~1.3 min）→ **预算 1.0–1.5 h/年**（R6 的 12–19 h 外推作废）。
- **E2/E3 full（chunk=64）**：128 块（两遍） → **≈2.1–2.4 h/年**（+ bootstrap ≤1 min）→ **预算 2.5–3 h/年**（R6 的 25–40 h 外推作废）。
- **bootstrap（replicates=2000）**：E2/E3 c64 末段（bootstrap+E3+序列化）**≤50.1 s**（检查点 mtime 分解）；E1 为 1:19。**bootstrap 不是全量瓶颈**。
- 检查点：E1 c64=2 chunk+checkpoint（哈希 `…` 于 PILOT_RESULTS/本表数据源）；E2/E3 c64 两遍检查点（first 12:47:31 / second 12:50:03 / summary 12:50:53）。

## 3. E4 N 扩展结论（Task D 判定）

- **fit**：N=128→76.8 s（2037 ex.）；N=256→82.3 s（3851 ex.）→ 用时比 1.07×（≈亚线性/近常数）。
- **eval**：N=128→21:24；N=256→21:26 → 比 1.002×：**eval 基本与 N 无关**（评估集 E=4096 固定，N 只改变被评模型的极小前向成本）。
- **headroom/ladder**：5:58→5:55 / 1:37→1:37（ladder 按设计锚定同一 N128 检查点，显然恒定）。
- **判定：N=4096 全网格不按 N 线性增长**；全网格每年预计 = headroom ~6 min + fit×6档（近常数，~10–15 min 合计）+ ladder ~1:37 + eval×6档（~6×21.5 min ≈ 2:09）+ 汇总 ≈ **2.5–3.5 h/年**（保守上界）。

## 4. 失败诊断与事件（全部留档，原始记录未改写）

1. **E4 n256 首次停在 ladder**：`BLOCK_M5B_SENTINEL_CHECKPOINT_MISSING`——ladder 需要 `{root}/2019/N128/M1_N.pt`，其 legacy 回退槽为 `…/sentinel_N128_r1/N128/M1_N.pt`；N=(256) 网格不含 128 锚。处置：将 R6 r2 已训练的 N128 复本（同快照/同协议/同种子）哈希校验后放入代码自带的回退槽（`SENTINEL_PLACEMENT_NOTE.txt`），随后**阶段级 resume 从 ladder 续跑**（headroom/fit 未重跑）。并入链诊断：`calib_chain.sh` 按规则在 FAILED 时停机 → 由人工 resume 完成，链条未重启。
2. **E2/E3 c64 重复启动事件**：本会话误启一条重复实例（12:56:05 起、12:56:40 击杀，35 秒内、未落任何产物；摘要 mtime 12:50:53 早于其启动）。其启动却再次打开并**截断**了有效运行的 `time_v.txt`（同 R6 复现）→ wall 由 meta 时间戳（12:43:57→12:50:54，精确到秒）回证，RSS 由采样器（≥2.82 GiB）回证。**根因=runner 的 time_v 覆盖式写入 + 无单驱动执行的启动前检查**；建议下一轮 runner 改为按尝试序号命名（time_v_attemptN.txt）+ 启动前校验对应 tag 的上一条 status 记录。
3. E4 attempt-1 的 `time_v.txt` 被 attempt-2 启动截断（同类机制）→ wall 用 meta（7:30）、峰值用采样器（≈5.1 GiB）回证。
4. 运行链结构性发现（供 full 计划）：电池 **ladder 依赖 N=128 锚**（或 sentinel 回退）——full 网格（含 128）天然满足；无需任何代码/协议变更。

## 5. 检查点稳定性

三类检查点（E1 chunk 组、E2/E3 两遍、E4 阶段级）在本轮**再次经受真实中断**（E4 停机→resume 从 ladder 续跑成功；未产生重复产物），全部可解析、含恢复身份；已完成的产物哈希在事件前后不变。

## 6. 结论

chunk=64 与 N=256 两项校准完成；R6 的部分外推被实测显著下修（详见 `FINAL_EXECUTION_RESOURCE_PLAN_V2.md`）。未启动 full、未触 Final-Test、无代码/模型变更、无输入产物再生成。云端无残留进程，可安全停机。
