# FULL_EXECUTION_SUMMARY（Air Slot Full Experiment Phase 1 · 2026-10-14）

> 仅报告实验执行结果（耗时/资源/完成矩阵/诊断/产物位置）。**不含论文结果表**；后续科学分析须另行授权。Final-Test 全程封存（各产物 `final_test_access_count=0`）。

## 1. 总体时间线

| 里程碑 | UTC | 北京 | 墙钟 |
|---|---|---|---|
| 链条启动（预检通过后） | 10-13 13:40:50Z | 10-13 21:40 | — |
| **Stage 1 · E4 Full**（六年度 × 6 worker）完成 | 10-13 18:27:54Z | 10-14 02:27 | **4h47m04s** |
| **Stage 2 · E2/E3 Full**（六年度 × 3 并发）完成 | 10-14 01:47:58Z | 09:47 | **7h20m04s** |
| **Stage 3 · E1 Full**（六年度 × 3 并发）完成 | 10-14 09:31:02Z | 17:31 | **7h43m04s** |
| **全链完成（`full_chain_done`）** | 10-14 09:31:02Z | 17:31 | **19h50m12s** |

## 2. 六年度完成矩阵（18/18 PASS，官方校验 `all_pass=true`）

| year | E1 | E2/E3 | E4 | E1 wall / peak | E2E3 wall / peak | E4 wall / peak |
|---|---|---|---|---|---|---|
| 2017 | PASS | PASS | PASS | 3:23:04 / 3.64 GiB | 3:19:27 / 9.89 GiB | 4:06:47 / 10.52 GiB |
| 2018 | PASS | PASS | PASS | 3:59:11 / 3.70 GiB | 3:33:36 / 7.40 GiB | 4:18:18 / 13.34 GiB |
| 2019 | PASS | PASS | PASS | 3:55:14 / 3.65 GiB | 3:41:12 / 9.68 GiB | 3:55:36 / 13.54 GiB |
| 2020 | PASS | PASS | PASS | 3:24:57 / 3.56 GiB | 2:55:00 / 6.44 GiB | 4:23:36 / 8.59 GiB |
| 2021 | PASS | PASS | PASS | 3:46:20 / 3.61 GiB | 3:14:42 / 7.35 GiB | 4:36:02 / 9.51 GiB |
| 2022 | PASS | PASS | PASS | 3:41:11 / 3.69 GiB | 3:37:43 / 10.45 GiB | 4:46:05 / 12.10 GiB |

（峰值 RSS 取 `/usr/bin/time -v`；E4 含全网格 N=128…4096、四阶段与全部比较批）

## 3. 资源消耗

- **机时**：Σ 任务墙钟 = **65.9 机时**（E4 23.3 + E2/E3 20.4 + E1 22.2）；链条墙钟 19.8h。
- 系统内存：采样器 144 次（10 分钟粒度）记录，**峰值已用 36.6 GiB / 最低可用 85.6 GiB**（20 GiB 安全线从未接近）；磁盘 75/295 GiB（27%）；loadavg 峰值 6.08/32 核。
- 全程单线程纪律（OMP/MKL/OPENBLAS/NUMEXPR=1）；同年份/同输出目录零并发。

## 4. 执行保真度（对照冻结基线）

- **E4 协议哈希六年度全部一致**（`sha256:18db92f0…`），终态全部 `DEVELOPMENT_COMPLETE`、决策全部 `N_GRID_UPPER_BOUND_REACHED`、`full_default_grid_observed=true`。
- **`failed_instances` 与 `data2/reports/paper_formal/{year}/EVAL_SUMMARY.json`（M5-b 冻结基线）逐年集合差为空**：2017/18/19/22=11、2021=12、2020=20（与基线逐年逐条一致，双向差集 ∅）。
- E2/E3、E1：各年 `DEVELOPMENT_COMPLETE`；两遍/chunk 检查点齐备（64/64 chunks、2+2 passes）。

## 5. 失败诊断

- **任务级失败：0**（18/18 exit 0；零重启；零重复实例——单驱动纪律全程保持）。
- **两个未建模成本（流程性发现，供资源计划修正）**：① E4 全网格的"比较批"（FIT 5 档 + EVAL 嵌套 5 档 ≈ 20–24 min/档）未含在 R7 校准 → Stage 1 超规划 ~60%；② E1 全量 bootstrap 阶段 ≈ 2h/年（三并发下）未含在校准 → Stage 3 超规划。资源计划应据实上修（E4 ≈4–4.8h/年、E2/E3 ≈2.9–3.7h/年、E1 ≈3.4–4h/年）。
- 无异常数据结构错误；无 provenance/哈希不一致。

## 6. 结果文件位置（云端；本地镜像同步）

- E4：`artifacts/experiment/jatm_s34/full_20261013/e4/{year}/`（`E4_YEAR_STATE`、`EVAL_SUMMARY`、`EVAL_METRICS_{year}_N*.json`、`FIT_METRICS_*`、`LADDER_PROBE`、`{year}/N*/M1_N.pt`、`E4_DEVELOPMENT_MANIFEST.json`）
- E2/E3：`.../full_20261013/e2e3/{year}/`（`E2_E3_SUMMARY.json`、两遍检查点、E3 产物、`EXACT_MARGINAL_AUDIT.json`）
- E1：`.../full_20261013/e1/{year}/`（`E1_SUMMARY.json`、`E1_CHUNK_CHECKPOINT.json`、`chunks/chunk_*.json`、`materialization/`）
- 校验与记录：`logs/raw_inputs_migration_20261013/bcu_20261013/FULL_EXECUTION_VALIDATION_REPORT.json`（含逐年哈希清单）、任务记录 `tasks/{e1,e2e3,e4}_full_{year}/`、链条日志 `full_chain.log`、采样日志 `resource_pilot.log`、授权 `FULL_EXPERIMENT_EXECUTION_AUTHORIZATION_USER_APPROVED_V1.json`。

## 7. 状态与边界

- 全部三阶段 + 校验完成；云端无残留进程，**可安全停机**。
- **未生成论文表、未做科学解释**；分析轮（含与 paper_formal 基线的科学比对）须下一次授权。Final-Test 未访问（`final_test_access_count=0` 全链保持）。
