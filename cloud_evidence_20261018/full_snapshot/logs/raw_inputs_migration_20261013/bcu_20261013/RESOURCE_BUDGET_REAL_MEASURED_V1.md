# RESOURCE_BUDGET_REAL_MEASURED_V1（基于 2026-10-13 pilot 实测；Task F）

**用途**：full experiment 调度与预算。**PILOT 数据，非论文结论。** 所有数字来自 R6 三组 pilot 的真实运行（year 2019），配置：E1 node_limit=128/chunk=4、E2/E3 node_limit=128/replicates=2000、E4 N_GRID=(128)，单核单线程纪律。

## 0. 实测锚点（全部真实测量）

| Pilot | wall | 峰值 RSS | 吞吐 | 检查点 |
|---|---|---|---|---|
| E1（128 items → 1781 决策节点） | 38:34（块阶段 35:56） | 3.50 GiB | 53.4 chunks/h；**214 items/h** | 32 chunk + checkpoint（哈希已录） |
| E2/E3（128 items，两遍 pass） | 74:23 | ≥3.92 GiB（time_v 被重复启动截断，已披露并回证） | **103 items/h** | 两遍检查点（哈希已录） |
| E4 单年 pilot（四阶段全通） | 30:19（headroom 5:58 / fit 1:20 / ladder 1:37 / eval 21:24） | **13.55 GiB** | N=128 评估子集 | 阶段级 `E4_YEAR_STATE`（四阶段） |

全量基准：每年度 development items = 4096（六年度一致；2019 的 E1 全量节点规模 ≈58.5k，与 M1 receipt 的 development_node_count 58554 相符）。

## 1. E1 full 预计时间（每年）

- **实测外推（chunk=4 线性）**：4096 / 214 items/h ≈ **19.1 h/年**（±10%）。
- **修正区间**：pilot 的 chunk=4 放大了每块固定开销；全量默认 chunk=64 可摊薄（未实测）→ **乐观下界 ~12 h/年**。
- **结论区间：12–19 h/年**；**下一授权须先测 chunk=64 单点**（node_limit=128 不变）以收窄。

## 2. E2/E3 full 预计时间（每年）

- **实测外推（chunk=4）**：4096 / 103 items/h ≈ **39.7 h/年**（含两遍 pass + bootstrap 2000；bootstrap 未单独计时，为已披露的限制）。
- **修正区间**：同 chunk 摊薄逻辑 → **25–40 h/年**（乐观下界）。
- E2/E3 为最重的 Development 链；建议全量排程前先测 chunk=64 单点。

## 3. E4 单年完整时间

- **Pilot 范围（仅 N=128）实测：30:19/年**（eval 占 70%）。
- **全网格（N=128…4096，fit+eval 六档）无 pilot 基准**；规划锚= M5-b 电池先例 **7–11.7 h/链·年**（同系 `consequence_stability_battery`，但为不同轮次/协议版本，仅作量级——不作为外推依据）。
- **建议**：下一授权加测 N=256 单点以量测 fit/eval 的 N 缩放，再冻结全网格预算。

## 4. 六年度并行预算

- 单任务峰值 RSS 实测：E1 3.50 GiB、E2/E3 3.92 GiB、E4 **13.55 GiB**（全部单进程单核；CPU/磁盘非瓶颈，内存与墙钟是约束）。
- 内存公式（安全线 20 GiB）：`并发 ≤ floor(102.3 GiB / 单任务峰值)` → E4 ≤7；E1/E2E3 ≤25（受 CPU 排程与墙钟目标约束更紧）。
- **六年度串行之和（区间）**：E1 72–114 h；E2/E3 150–240 h；E4（全网格按锚）42–70 h。
- **并行墙钟**：E4 六年度按 4–6 worker ≈ **一次 7–12 h 波次**（若全网格）或 N=128-only 直通 ≈ 一次 ~30 min 波次/年；E1 六年度按 3 并发 ≈ 24–38 h；E2/E3 六年度按 3 并发 ≈ **50–80 h**（重量级，建议先做 chunk 测量再定）。

## 5. 推荐并发数

1. **E4：4–6 个年度 worker**（6 worker 合计 81.3 GiB ≤ 102.3 GiB 预算，余量 >40 GiB；官方 `e4_scheduler` 原生支持、含内存感知）；
2. **E1/E2/E3：每年 1 进程；批内 2–3 并发**，且与 E4 worker 混跑合计满足内存公式（例：4×E4 + 2×E2/E3 = 62.2 GiB ✓）；
3. **总纪律**：重型任务合计 ≤6 并发、系统可用内存 ≥20 GiB、全部单线程（OMP/MKL/OPENBLAS/NUMEXPR=1）、同年份/同输出目录禁止并发、按 `E4_YEAR_STATE`/`E1_CHUNK_CHECKPOINT`/两遍检查点断点续跑；
4. **推荐排程顺序**：E4 六年度（一次六 worker 波次）→ E1 六年度（3 并发×2 波）→（先补 chunk=64 单点测量）→ E2/E3 六年度；
5. 采样器（10 分钟粒度）在长跑期间常开；任何非零退出仅阻塞对应年份与下游依赖。
