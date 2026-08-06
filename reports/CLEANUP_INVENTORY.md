# Cleanup Inventory

Inventory date: 2026-08-02
Status: INVENTORY — awaiting human confirmation before any deletion

This inventory classifies every candidate for cleanup before any destructive
step. Nothing in this file has been deleted.

## Classification policy

| 类型 | 处理 | 内容 |
|------|------|------|
| 正式代码 | 保留 | `pre/src`, `overall_run/src`, `overall_adv/src`, `part_adv/src`, 顶层共享模块 |
| 正式config | 保留 | 所有 `*/config/*.yaml` |
| tests | 保留 | 所有 `*/tests`, 顶层 `tests/` |
| docs | 保留 | `docs/`, `README.md`, `CLOUD_RUNBOOK.md` |
| reports 最终版 | 保留 | `reports/` 下的最终审计报告 |
| prototype | 归档 | `analysis/`、`output/` 下的 prototype 产物 |
| debug 脚本 | 删除 | 无独立 debug 脚本；debug 运行日志见下 |
| 临时输出 | 删除 | dev run 输出、zip、临时 staging |
| 中断 run | 删除 | 未发布的 staging / 中断 run 残留 |
| 旧 registry | 归档 | dev run 归档目录 |

## A. 保护清单（绝不删除）

| 路径 | 理由 |
|------|------|
| `data/` | 只读正式数据 |
| `pre/cache/` | clean 合约明确保留 |
| `pre/output/fast/` | 正式 fast baseline（2026-08-01 发布） |
| `overall_run/output/fast/` | 正式 fast baseline |
| `overall_adv/output/fast/` | 正式 fast baseline |
| `part_adv/output/fast/` | 正式 fast baseline |
| `pre/output/middle/` 等 4 模块 `middle/` | 正式 72-day profile 输出 |
| 全部 `src/`、`config/`、`tests/`、`docs/`、`reports/` 最终版 | 正式代码/文档 |
| 顶层 `action_contract.py` `clean_common.py` `downstream_common.py` `ranking_contract.py` `run_profiles.py` `strict_config.py` | 现行被 import 的共享模块 |

## B. 待确认删除（用户明确授权）

### B1. 开发运行输出 `fast_three_change_dev`（明确不是 PASS）

| 路径 | 内容 | 大小 |
|------|------|------|
| `pre/output/fast_three_change_dev/` | `.staging` 未发布 run（run-951807a9…） | 4.9 MB |
| `overall_run/output/fast_three_change_dev/` | 空目录 | 0 |
| `overall_adv/output/fast_three_change_dev/` | 空目录 | 0 |
| `part_adv/output/fast_three_change_dev/` | 空目录 | 0 |

dry-run 已验证 clean 可精确命中且只清该目录（见 CLEANUP_FINAL_STATUS.md）。

### B2. 开发运行归档（同一非 PASS dev 输出的备份）

| 路径 | 大小 |
|------|------|
| `pre/output/fast_three_change_dev_archive_misresolved_20260802/` | 188.2 MB |
| `overall_run/output/fast_three_change_dev_archive_20260802_154126/` | 12.7 MB |
| `overall_adv/output/fast_three_change_dev_archive_20260802_154317/` | 3.1 MB |
| `part_adv/output/fast_three_change_dev_archive_20260802_154351/` | 54.2 MB |

处置建议：**归档**到 `analysis/archive/`（按"旧 registry → 归档"原则），或删除。待确认。

### B3. 临时 zip

| 路径 | 大小 |
|------|------|
| `part_adv/part_adv output.zip` | 115.1 MB |

处置建议：**删除**（文件名含空格、明显临时打包、内容与 dev 输出重复）。待确认。

## C. 待确认处理（审计/调试产物）

### C1. 代码审计运行输出 `fast_code_audit_n1`

| 路径 | 大小 |
|------|------|
| `overall_run/output/fast_code_audit_n1/` | ~5 MB |
| `overall_adv/output/fast_code_audit_n1/` | ~4 MB |
| `part_adv/output/fast_code_audit_n1/` | ~56 MB |

内容为 code audit N1 的 M1–M4 完整运行产物（含 `m4_ranking_k1/k2/k3/k5`）。
处置建议：非正式输出，**归档或删除**。待确认。

### C2. 顶层 `output/` 分析/prototype 输出

| 路径 | 大小 | 性质 |
|------|------|------|
| `output/chain_feasibility/` | 3,814.6 MB | prototype chain-feasibility parquet |
| `output/p1_event_reconstruction/` | 28.8 MB | P1 prototype 输出 |
| `output/r1_baseline_repair/` | 0 | 空 |
| `output/r1_runtime_logs/` | 0 | 空 |

处置建议：按"prototype → 归档"移入 `analysis/archive/`，或删除。待确认。

### C3. debug 运行日志

| 路径 | 大小 |
|------|------|
| `reports/runtime_logs/`（n1/n14/pre_dev 运行日志） | < 0.1 MB |

处置建议：debug 日志，**删除**。待确认。

### C4. `analysis/` 目录

| 路径 | 大小 | 性质 |
|------|------|------|
| `analysis/chain_feasibility/` | 0.1 MB | prototype 代码 |
| `analysis/formal72_source_coverage/` | 0.3 MB | 分析代码 |
| `analysis/p1_event_reconstruction/` | 0.1 MB | P1 分析 |
| `analysis/r0_baseline_audit/` | 0 | 空 |
| `analysis/r1_baseline_repair/` | 0.1 MB | 分析代码 |

处置建议：体积很小且被 reports 引用，保留原位；如需严格化可统一移入
`analysis/archive/`。待确认。

## D. 明确删除范围汇总（待确认后执行）

```
pre/output/fast_three_change_dev/            (4.9 MB)
overall_run/output/fast_three_change_dev/    (0)
overall_adv/output/fast_three_change_dev/    (0)
part_adv/output/fast_three_change_dev/       (0)
part_adv/part_adv output.zip                 (115.1 MB)
reports/runtime_logs/                        (<0.1 MB)
```

候选归档（待确认）：
```
pre/output/fast_three_change_dev_archive_misresolved_20260802/   (188.2 MB)
overall_run/output/fast_three_change_dev_archive_20260802_154126/ (12.7 MB)
overall_adv/output/fast_three_change_dev_archive_20260802_154317/ (3.1 MB)
part_adv/output/fast_three_change_dev_archive_20260802_154351/   (54.2 MB)
overall_run/output/fast_code_audit_n1/       (~5 MB)
overall_adv/output/fast_code_audit_n1/       (~4 MB)
part_adv/output/fast_code_audit_n1/          (~56 MB)
output/chain_feasibility/                    (3,814.6 MB)
output/p1_event_reconstruction/              (28.8 MB)
output/r1_baseline_repair/                   (0)
output/r1_runtime_logs/                      (0)
```

## E. 保护范围复核

- `config` 不进入任何删除范围：YES
- `src` 不进入任何删除范围：YES
- `tests` 不进入任何删除范围：YES
- `docs` / `reports` 最终版不进入任何删除范围：YES
- 正式 fast baseline 4 模块均受保护：YES
- 正式 middle 输出 4 模块均受保护：YES
- `data/` 与 `pre/cache/` 受 clean 合约保护：YES

## F. 执行顺序

1. 人工确认 B/C 分类与处置方式 —— 已确认（2026-08-02）
2. `clean --output-id fast_three_change_dev --dry-run` —— 已完成（见 B1）
3. 正式 clean（仅 fast_three_change_dev）—— 已完成，4 模块 CLEAN_PASS
4. 手工删除已确认的临时产物 —— 已完成（全部 13 项，共约 4.29 GB）
5. 生成 `reports/CLEANUP_FINAL_STATUS.md` —— 已完成
6. 更新 `README.md`（Step 1）—— 已完成

## G. 执行结果

EXECUTION_STATUS=COMPLETE

- B1 dev 输出：已 clean（4 模块）
- B2 dev 归档（4 目录）：已删除
- B3 临时 zip：已删除
- C1 code_audit_n1（3 模块）：已删除
- C2 顶层 output prototype（含 3.8 GB chain_feasibility）：已删除
- C3 debug 运行日志：已删除
- C4 analysis/ 保留原位（体积小且被 reports 引用）
- 保护清单 A 全部完好（正式 fast/middle/cache/data/config/src/tests/docs）

详细证据见 `reports/CLEANUP_FINAL_STATUS.md`。
