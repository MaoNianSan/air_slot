# RESOURCE_BUDGET_PLAN（E1–E4 正式实验；第五轮制定）

平台：腾讯云 SA9.8XLARGE128（32 vCPU / 123.3 GiB / 数据盘 295 GiB，现用 25%）。
所有估计以第 4 轮真实实测为锚，**全量实验 CPU-hours 明确未知**（官方文档亦如此要求：不得用 smoke 或 M5-b 直接外推）——因此计划采用"先导阶梯测量 → 冻结预算"的两段式。

## 1. 实测锚点（第 4 轮，非模拟）

| 任务 | 并发 | wall | 峰值 RSS | IO/W 少量 |
|---|---|---|---|---|
| M1 年训练（双角色） | 3 路 | 5:40–6:53 | 7.5–8.1 GB | 读 ~0.1 GB |
| Annual Tail | 4 路 | 29–38 min | ≈2.2 GB | 轻 |
| bounded Development smoke（E1 8 节点 + E2E3 8 节点） | 1 路 | 7:31 | 3.9 GB | 轻 |

旁证（非外推依据）：M5-b 电池六年实验单链墙钟 7–11.7 h（同系 consequence_stability_battery，但协议/网格版本不同，仅作量级参考）。

## 2. 并发策略

- **E4**：使用官方 `e4_scheduler`（内建内存感知并行、独立 worker 目录）。建议先 2 年并发实测 → 按测得单 worker 峰值 RSS（预计 8–16 GB/worker，含 torch 单线程）扩展至 **4–6 并发**；同时运行 worker 的合计内存满足 `ΣRSS ≤ 103 GiB`（即 123.3 − 20 GiB 安全线）。
- **E1/E2/E3**：单进程逐年前进（`run_bounded_annual`）；若测得 RSS ≤ 12 GB，可 2–3 年并发（与 E4 worker 共享预算公式）。
- **线程纪律**：所有任务 `OMP/MKL/OPENBLAS/NUMEXPR=1`（与 M1/Tail 同规）；禁止多任务同时放大 BLAS 线程。
- **混跑规则**：E4 与 E1/E2/E3 可交错，但任一时刻合计内存余量 ≥20 GiB；磁盘写入均为 MB–低 GB 级（日志/JSON/检查点），无 IO 风险。
- 复用既有调度设施：`bcu_dispatcher`/`m1_dispatcher` 的队列+并发文件模式 + 看守器（M1→Tail 曾零人工衔接 6 小时窗口）。

## 3. wall time 预算（两段式）

**第一段（授权后先导，必做）**：
1. E1 pilot：`node_limit = 128`（chunk=4），记录 wall/RSS/每节点速率；
2. E1 pilot：`node_limit = 512`（chunk=64），得速率曲线（验证线性度）；
3. E2E3 pilot：同档位两节点数；
4. E4 单年 pilot：`e4_run` 对 2019 跑 `n_grid=(128,)` 的最小子集（headroom→fit→ladder→eval 全阶段路由走通），记录每阶段 wall。
用 1–4 的实测推出全量预算（E1/E2/E3 全量节点数即 development 分区节点总数，可从年度 bridge 实测得出；E4 全量 = 六年 × 四阶段 × N_GRID 六档）。

**第二段（冻结预算）**：以 pilot 外推值 + 20% 余量写入正式授权记录；E4 整轮建议预留 **跨昼夜窗口**（参考量级：每年链 6–12 h，六年串行 1.5–3 天；并发 4–6 年可压至 ~0.5–1 天——**以 pilot 为准**）。

## 4. 内存预算上限

- 全局安全线：**可用内存 ≥ 20 GiB**（与第 4 轮同规）。
- 单任务上限（应用层设定）：E1/E2/E3 ≤ 16 GB、E4 worker ≤ 16 GB、Tail 2.2 GB、M1 8.1 GB（历史峰值 + 20% 余量）。
- 并发上限公式：`concurrency = floor((123.3 − 20 − 1) / 单任务峰值)`；按 16 GB 计 = 6。

## 5. checkpoint / log / provenance 保存策略

- **检查点**：E1 用 `chunks/chunk_*.json` + `E1_CHUNK_CHECKPOINT.json`（断点含 git_head/input_hashes 校验，跨代码变动自动拒绝 resume）；E2E3 双 pass 检查点；E4 用 `E4_YEAR_STATE.json` 阶段级 resume（headroom/fit/ladder/eval）。全部支持中断续跑，**禁止盲目重启**。
- **日志**：每任务独立 tag 目录（`logs/.../tasks/<tag>/`：log、pid、exitcode、meta、time_v、input/output sha256）；E4 另存 `YEAR_{y}/{phase}.log`。
- **provenance**：入口级 `git_head`（云端经 `GIT_DIR=/data/airslot/smoke_gitmeta/repo/.git` 声明真实快照 583f2c12；补丁链单独记录）+ 逐年 input hashes + `fta=0` 断言；所有运行产物的关键 JSON 双侧（云端+本地）归档并记 sha256。
- **资源采样**：任务期间重启 `resource_sampler.sh`（10 分钟粒度，loadavg/free/df/进程 RSS 汇总）。

## 6. 停机/暂停策略

- 批次完成或到达授权时限 → 停止派发新任务；运行中任务依赖其原生检查点安全落盘（E1 chunk / E2E3 pass / E4 phase）。
- 任何非零退出 → 记录完整原因，仅阻塞该年与下游依赖，其他独立年份继续（与第 4 轮规则一致）。
