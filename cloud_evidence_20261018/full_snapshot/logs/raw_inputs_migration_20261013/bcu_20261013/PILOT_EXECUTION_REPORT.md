# PILOT EXECUTION REPORT（R6，2026-10-13）— 仅链路验证/资源测量/调度确定

> **PILOT 声明**：本报告及全部 pilot 输出**不得用于论文实验结论**；不包含任何科学结果表。仅含：执行时间、内存、吞吐、检查点稳定性、失败诊断。E1–E4 全量实验与 Final-Test 均未启动（`final_test_access_count=0`，双证于输入合同与 EVAL 决策）。

## 1. 授权与范围（Task A）

`EXPERIMENT_EXECUTION_AUTHORIZATION_PILOT_V1.json`（sha256 `a427b36f…`），范围逐字对齐任务书：experiment_ids=[E1_PILOT,E2_PILOT,E3_PILOT,E4_PILOT]、years=[2019]、DEVELOPMENT_ONLY、Final-Test 禁止、代码零变更（快照 583f2c12 + 补丁链 d1c72a7/ffa7487）、全部输出带 provenance。双侧归档。

## 2. 资源采样（Task B）

`resource_sampler_v2.sh` 10 分钟粒度（loadavg/memory/disk/进程树 RSS），采样于 `resource_pilot.log`；pilot 期间系统可用内存始终 ≥115 GiB，磁盘 25%，CPU 余量充足（单核任务）。

## 3. 链路验证结果（Tasks C/D/E）

| Pilot | 配置 | 结果 | wall | 峰值 RSS | 检查点 |
|---|---|---|---|---|---|
| E1 | node_limit=128, chunk=4 | **PASS**（DEVELOPMENT_COMPLETE） | 38:34 | 3.50 GiB | 32 chunk + CHUNK_CHECKPOINT（`810face3…`），resume 守卫=git_head+input_hashes |
| E2/E3 | node_limit=128, replicates=2000, seed=20261011 | **PASS** | 74:23 | ≥3.92 GiB | 两遍检查点（`8ca8f7cb…`/`5414d424…`）；230 条 exact-marginal 审计全部 included（0 abstain）；E3 四 profile × 136 行；bootstrap 2000 产 8 行 CI（值不报告） |
| E4 | year 2019, N_GRID=(128), R1 束根 | **四阶段全通**；终态=设计性 `PILOT_COMPLETE_HARD_STOP`（failed_instances=[]） | 30:19（headroom 5:58 / fit 1:20 / ladder 1:37 / eval 21:24） | 13.55 GiB | 阶段级 `E4_YEAR_STATE`（四阶段完成）+ 电池输出（headroom/ladder/N128 检查点/EVAL_METRICS） |

吞吐：E1 214 items/h（53.4 chunks/h）；E2/E3 103 items/h；E4 N=128 子集 30:19/年。

## 4. 检查点稳定性

- 三类检查点全部 JSON 可解析、含恢复所需身份（E1：git_head+input_hashes 守卫；E2/E3：两遍 chunk 计数 32+32；E4：阶段级 resume）。
- 重复启动事件未触碰已完成产物：E2_E3_SUMMARY.json 哈希 `809ab8a8…` 在 11:46 完成后保持不变（mtime/哈希复核）。
- 无同年份同目录并发写；所有写发生在各自独立输出目录。

## 5. 失败诊断（3 项，全部有据可查）

1. **E4 尝试#1（11:52:38Z，3 秒失败）**：`PROTOCOL_V1_MISSING` —— 电池协议锚 `CONSEQUENCE_STABILITY_PROTOCOL_V1.json` 云端缺失。修复：从本地权威副本恢复（11:54:13Z，sha256 `cd5dc970…` 与本地逐字节一致）；r2 于 11:54:22Z 正常起跑并四阶段全通。已归档诊断。
2. **E2/E3 重复启动事件**（11:51/12:06/12:16Z 三条短命 START）：采样器证明有效窗口内仅 pid 166388 在跑；重复实例均未持久化、未写产物即终止。唯一记录级后果：有效运行的 `/usr/bin/time` 报告被截断 → 其 wall/峰值由采样器+日志时间戳回证（`tasks/pilot_e2e3/RECORD_ANOMALY_NOTE.txt` v2 完整披露）。
3. **E4 驱动的判成条件**：pilot 硬停止（`M5B_PILOT_COMPLETE_HARD_STOP`）被 e4_run 按设计映射为 `ENGINEERING_INCOMPLETE + completion_class=PILOT_COMPLETE_HARD_STOP`，驱动脚本按"==DEVELOPMENT_COMPLETE"判成 → rc=1。**非链路失败**；已在 `PILOT_RESULTS.json` 与任务目录加注，运行器原始记录不改写。

## 6. 结论与下一步

- 三条 Development 链（E1、E2/E3、E4 四阶段）在云端**端到端验证通过**，检查点/恢复/审计机制均工作。
- 预算更新见 `RESOURCE_BUDGET_REAL_MEASURED_V1.md` / `UPDATED_RESOURCE_BUDGET.md`（E1 12–19 h/年；E2/E3 25–40 h/年；E4 全网格锚 7–11.7 h/年；六年度并行推荐 4–6 worker）。
- **全量 E1–E4 未启动，等待下一次授权**；建议下一授权包含 chunk=64 与 N=256 两个单点测量以收窄外推。
- 云端无残留进程，可安全停机。
