# CLOUD_COMPUTE_RESOURCE_REPORT（第四轮，2026-10-13）

平台：腾讯云 SA9.8XLARGE128（32 vCPU / 123.3 GiB / 数据盘 295 GiB）。
轮次窗口（UTC）：M1 训练 07:53–08:14；Tail 队列 08:06–08:53；六年度验收 08:53–08:54；Development smoke 08:56–09:04。总活跃约 71 分钟（远低于 4 小时上限，任务全部完成后即停止）。

## 逐任务实测

| 任务 | 并发情形 | wall | 峰值 RSS | CPU | 备注 |
|---|---|---|---|---|---|
| M1 2019 训练（双角色，正式） | 单任务（基线测量） | 6:28 | 7.51 GB | 99% 单核 | receipt `f5731410…` |
| M1 2020 / 2021 / 2022 | **3 路并发** | 5:40 / 6:07 / 6:53 | 7.85 / 7.85 / 8.11 GB | 各 99% 单核 | dispatcher 自动调度，全 PASS |
| Tail 2019 / 2020 / 2021 / 2022 | **4 路并发**（看守器自动流水线） | 37:45 / 29:08 / 32:23 / 35:19 | 各 ≈2.2 GB | 各 ~100% 单核 | 每年 M1 PASS 后自动触发 |
| Development smoke 2019（bounded） | 单任务 | 7:31 | 3.9 GB | 99% 单核 | node_limit=8 / chunk=4 / bootstrap=5 |

并发期间：loadavg 峰值 ≈4.0（32 核，>85% 余量）；系统可用内存最低 ≈115 GB（4×2.2 GB Tail + 3×7.9 GB M1 峰值远未逼近 20 GiB 安全线）；数据盘 69/295 GB（25%），I/O 全程非瓶颈。线程纪律：所有任务 `OMP/MKL/OPENBLAS/NUMEXPR=1`，单任务一逻辑核，无过度订阅。

**并发收益**：4 年 M1 若串行 ≈25 分钟，实际 3 路并发墙钟 ≈7.4 分钟（≈3.4×）；4 条 Tail 串行之和 ≈134 分钟，并发墙钟 ≈38 分钟（≈3.5×），且与 M1 训练交叠执行。

## 失败与恢复

- smoke 第 1 次尝试 08:54 失败：Entry `e1_information_gain.py:433` 硬调用 `git rev-parse HEAD`，云端 worktree（tar 部署）无 `.git` → CalledProcessError 128。处置：以**真实 git** 建立仅含 `HEAD→583f2c12…`（取自 CODE_SNAPSHOT.json 的快照真实提交号）的元数据仓库，经 `GIT_DIR` 环境变量提供修订标识（worktree 零改动、无代码修改）；第 2 次尝试 08:55:58 起跑并通过。两次尝试均留档于 `dev_smoke_2019` 任务日志。
- 其余任务零失败；唯一记录保留：m1_2019 的启动授权记录为转写件 `add7004cf…`（与规范件 `826ad275…` 固定字段逐字一致；按"不得重复正式训练"未重跑；receipt 绑定 `add7004cf…`，等价性记录于 `M1_2019_2022_TRAINING_SUMMARY.json`）。

## 停机判断

**全部已授权任务完成；云端无残留计算/调度/采样进程 → 可安全停机（关停实例仅停止计费，所有产物与记录均已持久化于磁盘并双侧归档）。** 恢复要点：任何后续轮次直接读取 `/data/airslot/logs/raw_inputs_migration_20261013/` 下的记录与 `SIX_YEAR_INPUTS_VALIDATED.json`，即可无缝续接（调度器/运行器脚本原样可复用；GIT_DIR 适配器位于 `/data/airslot/smoke_gitmeta/`，供任何仍硬依赖 git 溯源的官方入口使用）。
