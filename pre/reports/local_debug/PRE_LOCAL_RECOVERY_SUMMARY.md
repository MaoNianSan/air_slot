# PRE Local Recovery Summary

> 本地恢复/调试汇总（不上传 GitHub）。生成时间：2026-08-05。
> 数据来源：`pre/reports/PRE_DEBUG_STATUS.md`（2026-08-05 09:55 更新）、
> `PRE_BASELINE_AUDIT.md`、`PRE_REFACTOR_EQUIVALENCE.md`、
> `PRE_CORE_CONTRACT.md`、`PRE_DATASET_COLUMN_AUDIT.csv|.md` 及本次上传审计实测。

| 字段 | 值 |
|---|---|
| **Git commit** | `7f5f36703fd6d97a050fc3d2a4c1f84681f9bf1f`（branch: main, "add detail"） |
| **当前 Phase** | `PHASE_8_DEBUG_AND_VALIDATION_INCOMPLETE`（Core 验证发布未完成） |
| **当前 staging 路径** | `pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b`（仅 observations/，无 manifest/validation/readiness/run_state/run log） |
| **cache 路径** | `pre/cache/state_extract_core_v1-6840ae55cc35`（285.18 MB, mtime 2026-08-04 20:43:59, 含 cache_manifest.json） |
| **cache key** | `6840ae55cc358c3246dc998134fa76bd08e9e7f895c93ca87445176d8e9d5eba`（cache dir 后缀 `6840ae55cc35`） |
| **partition 数** | cache 120/120；staging observations 29 个分区（state=5, flow=5, weather=19） |
| **observation 行数** | 10,544,721（state 10,290,528 + flow 251,396 + weather 2,797）；cache candidate rows 10,290,528，flow source rows 7,087,981 |
| **已通过测试数** | 41 项（`PRE_TEST_STATUS=PASS_41_TESTS`；基线 29 passed，Core 相关新增 12 项） |
| **最近失败位置** | ① `Core 6/7 - Validate and freeze hashes`：`IMPLEMENTATION_VALIDATION_AGGREGATION_ERROR`（bool 被当作 int 计入错误；已修复，回归通过）② `Core 4/7 - Native observation partition resume`：`INEFFICIENT_RESUME_IO_AND_HASHING`（全量读取+字符串哈希过慢；已改为九列投影+文件字节哈希，**未对完整 staging 验证**） |
| **已完成修复** | bool/int 聚合误判（observation validation summary）；resume 读取改九列投影与 Parquet 文件字节哈希（静态/单元覆盖） |
| **未验证修复** | resume 投影验证与文件哈希尚未对完整 staging 集验证；staging 兼容性（config hash/request hash/code hash/cache key/partition manifest）未核验 |
| **已知 blocker** | `RAW_COLUMN_RETENTION`（未保留全部审计 raw 列）；`COLUMN_LEVEL_EVIDENCE`（evidence 为分区级摘要非最终列级血缘）；`UNVERIFIED_STAGING_RESUME`（resume 未验证 config/request/code hash 与 manifest）；`UNSUPPORTED_OPERATIONAL_EVENTS`（无官方 AOBT/AIBT/ATOT/ALDT/SOBT/rotation/cancel/diversion/swap 字段） |
| **下一允许步骤** | `STATIC_RESUME_CONTRACT_AND_SMALL_TEST_FIX`：① 写 observations 前落一个小 staging resume manifest（含 Core schema hash、config/request/interval/code hash、cache key、期望 source/date partition）；② 加双分区合成 resume 测试（投影验证、bool 聚合、文件哈希、拒绝不兼容 staging）；③ 定义并测试 flightlist/state/METAR 最小非丢弃 raw 列存储/注册映射（不改 event/chain 语义）；④ 只跑单元测试与极小合成 smoke，**不重跑 fast**，直到 staging 兼容性被证明 |

## 关键不变项（本次上传审计确认）

- `RAW_DATA_MODIFIED=NO`；`M1_M2_M3_M4_MODIFIED=NO`。
- Legacy `pre/output/fast` 保留且未被覆盖（acceptance run `pre-fast-20260803T022638Z-64115215`, PASS）。
- Core staging 保留（578.57 MB）；Core cache 保留；legacy cache `state_extract_v2` 保留（Phase 1 等价性 run 仍 HIT 使用）。
- Core 合同冻结：`AIR_CHAIN_CORE_V1` / schema `air-chain-core-1.0` / Core schema hash `231a3e34b09ac0e325669de634bca4da85d2a06a9036e2eba056f7eb69d39be6`。
- 事件/链证据（fast）：events 78,506 行（proxy/official 混淆 0，顺序错误 0）；chains 15,866（formal eligible 14,837，ambiguity leakage 0，split leakage 0）。

## 本地调试报告位置（保留）

均已位于 `pre/reports/`（未被忽略的上传范围之外，不上传 GitHub）：

- `PRE_DEBUG_STATUS.md`（最新，2026-08-05 09:55）
- `PRE_BASELINE_AUDIT.md`
- `PRE_REFACTOR_EQUIVALENCE.md`
- `PRE_CORE_CONTRACT.md`
- `PRE_DATASET_COLUMN_AUDIT.csv`（178,288 B）+ `PRE_DATASET_COLUMN_AUDIT.md`
- 本次上传审计：`pre/reports/github_upload/` 下各报告
- 本次恢复汇总：本文件 `pre/reports/local_debug/PRE_LOCAL_RECOVERY_SUMMARY.md`

> 根目录无散落 PRE_* 调试文件，无需移动；各报告用途不同，未合并覆盖。
