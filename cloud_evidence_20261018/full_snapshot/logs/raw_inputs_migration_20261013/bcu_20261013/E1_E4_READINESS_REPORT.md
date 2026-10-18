# E1–E4 Readiness Report（第五轮 · 启动前准备；未运行任何 full experiment）

日期：2026-10-13。性质：只读审计 + 计划 + 授权模板。**未启动 E1–E4、未解封 Final-Test、未改任何代码/模型。**

## Task A · 全局状态重建（全部核实）

| year | M1 | Tail | Year-local B CU | D4 Fixed-common | 官方门 |
|---|---|---|---|---|---|
| 2017 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |
| 2018 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |
| 2019 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |
| 2020 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |
| 2021 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |
| 2022 | VALID | VALID | VALID | VALID | INPUTS_VALIDATED |

- 依据文件全部实读并记哈希：`SIX_YEAR_INPUTS_VALIDATED.json`、`M1_2019_2022_TRAINING_SUMMARY.json`（all_pass=true）、`ANNUAL_TAIL_2019_2022_VERIFICATION.json`（all_valid=true，2019–2022 manifest 哈希 a2651c46/25be8b7b/2e7c23ec/db202ac4）、`DEVELOPMENT_SMOKE_VERIFICATION.json`（PASS）、`SIX_YEAR_INPUT_GATE_FINAL.json`。汇总见 `CURRENT_SYSTEM_STATE.json`。
- `final_test_access_count = 0`：六年门逐条、四份 M1 receipt、smoke 输入合同、登记 scope 均为 0。
- 无残留 Air Slot 计算/调度进程（检测器 v1 曾误匹配系统守护进程 networkd-dispatcher，已修正并留档）。
- 代码身份 = `CODE_SNAPSHOT`(583f2c12 / archive 4e8e64b6) + 补丁链 `8cc7a1b7`(d1c72a7) + `1d3ba5d3`(ffa7487)；两个被补丁文件哈希与补丁档案逐字一致；registry 冻结哈希 befc3ae1。

## Task B · E1–E4 Execution Readiness Matrix

**共享输入适配器**：`exp/jatm_s34/annual_bridge.load_annual_bridge` —— cohort（HASH_SELECTED_N4096）+ 年度 M1（两角色）+ **R1 参考束**（`PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1/{year}`，LEGACY_A；这是 Development 实验链的既定输入，B 束供 CU/门使用，两者不混用）+ Annual Tail + configs + Authorities。E1/E2/E3 的年度入口统一由 `annual_development.run_year_bounded` 编排。

| 维度 | E1 | E2 | E3 | E4 |
|---|---|---|---|---|
| 入口 | `e1_information_gain.run_bounded_annual`（legacy: `run`） | `e2_e3_exact.run_bounded_annual`（E2 段：`information_value_main`） | 同模块 E3 段：`comparator_recovery`（`exp/jatm_section5/recovery_value.py:171`） | `e4_run.run`（阶段编排）+ `e4_scheduler`（并行）+ `e4_development.run`（前置检查） |
| 输入依赖 | annual_bridge（cohort/M1/R1/tail）+ Section-5 节点构建器（`_build_nodes`）+ M2 原生分量 P_time/F_propagation + M1 D_TO | 同桥 + `ExactWeightedMarginalDistribution`（HISTORY_MARGINAL_EXACT）+ headroom 汇总 | 同桥 + comparator 模块替换：`ExactWeightedMarginalDistribution` ↔ 旧置换实现（legacy 留于 `HISTORY_MARGINAL_LEGACY`，不覆盖历史输出）+ PROFILES 域强调视图（FLIGHT/PASSENGER/RESOURCE） | 每年链：`consequence_stability_battery`（`--bundle-base` 可配；默认检查 R2，现网 R2 与 B_V1 均具 scales）+ 六年度 PRE 开发输入（manifest/states/cohort_state/split_audit，六年齐） |
| 输出 | `E1_SUMMARY.json`(`JATM_S34_E1_DEVELOPMENT_BOUNDED_V1`) + `E1_SELECTED_ROWS.json` + `E1_CHART_DATA.json` + `chunks/chunk_*.json` + `materialization/` | `E2_E3_SUMMARY.json`(`JATM_S34_E2_E3_EXACT_DEVELOPMENT_BOUNDED_V1`，含 information_value/diagnostics/bootstrap/comparator 行) | `E3_MECHANISM_DIAGNOSTICS.json` + `E3_OBJECTIVE_ROWS.json` + `EXACT_MARGINAL_AUDIT.json` | `YEAR_{y}/E4_YEAR_STATE.json`（阶段进度）+ `{phase}.log`（headroom/fit/ladder/eval）+ 电池年度输出 |
| provenance | `git_head`(需 GIT_DIR 适配) + `input_hashes`（两 checkpoint + R1 manifest）+ 每 chunk 检查点（含 git_head/input_hashes/`fta=0`，resume 时校验） | 双 pass 检查点（canonical/selected 两级，`fta=0`）+ `git_head` + input hashes | 随 E2/E3 摘要记录（`comparator="HISTORY_MARGINAL_EXACT"`、`sealed_executor_called=false`、`scientific_recomputation=true`） | 阶段级 resume（断点续跑）+ 每年独立目录 + FINAL_TEST 路径守卫（输出/bundle 路径含 final_test 即拒绝） |
| bootstrap/resampling | E1 侧 bootstrap 由 bounded 参数控制（smoke 用 5；全量建议 2000，与 E2 一致后再定） | **replicates=2000（调用点显式），seed=20261011** | E3 非重采样实验（模块替换对照） | N_GRID=(128,256,512,1024,2048,4096)，fit/eval 两阶段共用（eval `--reuse-fit-comparison`） |
| Final-Test 依赖 | **无**（仅记录 fta=0；无 Test 路径） | **无**（`sealed_executor_called=false`；fta=0 常量） | **无** | **无**（前置检查 `test_status=BLOCKED_TEST_ACCESS`；run 守卫拒绝 final_test 路径） |

**就绪判定**：输入侧 **READY**（六年 R1/B/D4(R2+B)/M1/Tail/cohort/PRE 开发输入全部在云端齐备且通过官方验收；E4 前置检查可用 `--bundle-root` 指向任一经批准的束根）。**唯一硬前置 = 实验执行授权**（Task D 模板，当前 NOT_APPROVED）。次要工程注意事项：① 云端无 `.git`，凡调用 `git rev-parse` 的入口（E1/E2E3/E4-preflight）须带 `GIT_DIR=/data/airslot/smoke_gitmeta/repo/.git`（HEAD→583f2c12，已验证可行）；② 全量 CPU-hours 未测，见预算计划的先导阶梯。

## Task E · 禁止事项检查（全部确认）

- 未启动 E1–E4 full run（本轮仅只读审计与文档；smoke 为第 4 轮已授权 bounded 运行，非 full）。
- Final-Test 保持封存：六年门/登记/smoke/四 receipt 的 fta 全 0；E4 各入口带路径守卫。
- 未修改任何模型公式/损失；未改 action/consequence 定义（本轮零代码变更；补丁链保持 d1c72a7+ffa7487 不变）。
- 未重训任何 M1（2017/2018 原样；2019–2022 为第 4 轮授权训练产物，本轮未动）。
