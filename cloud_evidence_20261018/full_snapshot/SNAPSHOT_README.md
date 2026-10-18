# Air Slot Full Execution Snapshot — 20261014

- 归档完成时间：2026-10-14（北京时间）
- 来源：腾讯云服务器 `ubuntu@134.175.205.112`（广州）
- 内容：**Full Experiment Execution Phase 1（R8）** 全部执行产物 + 云端八轮（R1–R8）日志记录 + 代码/输入/环境绑定 + 缺口区补齐
- 边界：**未生成论文表、未做科学分析**；Final-Test 全程封存（所有产物 `final_test_access_count=0`）

---

## 1. 目录布局

```
airslot_full_execution_snapshot_20261014/
├── artifacts/
│   ├── experiment/jatm_s34/
│   │   ├── full_20261013/            # ★ R8 全量实验产物（E1/E2E3/E4 × 六年度，10536 文件）
│   │   │   ├── FULL_20261013_MANIFEST.sha256   # 服务端逐文件 SHA-256 清单
│   │   │   ├── e1/{2017..2022}/       # E1：chunks（64/年）、materialization、E1_SUMMARY 等
│   │   │   ├── e2e3/{2017..2022}/     # E2/E3：两遍检查点、E3 诊断、EXACT_MARGINAL_AUDIT 等
│   │   │   └── e4/{2017..2022}/       # E4：全网格 N=128..4096、FIT/EVAL 指标、梯级探针、检查点
│   │   ├── pilot_20261013/           # R6 Pilot（386 文件）+ PILOT_20261013_MANIFEST.sha256
│   │   ├── calibration_20261013/     # R7 校准（265 文件）+ CALIBRATION_20261013_MANIFEST.sha256
│   │   ├── development_smoke_20261013_2019/   # R5 Development smoke（云端生成）
│   │   └── p1_semantic_inheritance_20261012/  # 语义继承审计包（云端生成）
│   ├── models/
│   │   ├── m1/YEAR_2017/             # 完整：模型 + tail MANIFEST/PROGRESS/32 chunks（chunks 为本地补件）
│   │   ├── m1/YEAR_2018/             # 模型 + tail（MANIFEST/PROGRESS/32 chunks，云端）
│   │   ├── m1/YEAR_2019..2022/       # 云端 R4 训练：模型 + ANNUAL_M1_TRAINING_RECEIPT + tail（各 39 文件）
│   │   ├── m1/{M1_FROZEN_H8,M1_FROZEN_H16,M1_H16_*,M1_V2_PHASE5_*}/  # 遗留冻结件（云端 LF 版本）
│   │   └── pre/
│   │       ├── PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1/   # ★ 冻结实验实际使用的 CU 适配器（六年度，1.1G）
│   │       └── PRE_MULTIYEAR_V1_D4_2017H1_B_V1/      # FIXED_COMMON 适配器（180M）
│   ├── diagnostics/  paper_results_v2_final_test/  paper_results_v2_final_test_rmb/  calibration/
│   │                                 # 遗留件中与本地字节不同的 104 文件的云端版本（语义等价，见 §2.3）
├── logs/
│   ├── raw_inputs_migration_20261013/     # 云端日志与记录（550 文件）+ RAW_..._MANIFEST.sha256
│   │   └── bcu_20261013/          # R4–R8 任务记录/驱动脚本/授权文件/FULL_EXECUTION_* 报告/
│   │                              #   full_chain.log、resource_pilot.log、tasks/、concurrency/
│   └── b_cu_2017*.log|pid|exitcode、run_b_cu_2017.sh、GAPZONE_*.sha256   # 云端 /data/airslot/logs 根散件
├── code/
│   ├── airslot_code_history_20261014.bundle     # git 完整历史 bundle（718,915,018 B，HEAD=ffa7487）
│   └── smoke_gitmeta/             # GIT_DIR 适配器（HEAD→583f2c12）
├── cloud_upload_package_20261013_v3/    # 上传包记录（含 source/airslot_source_583f2c1.tar.gz 95.8M，
│                                        #   sha256=4e8e64b6… 与 CODE_SNAPSHOT.source_archive_sha256 一致）
├── incoming/                       # 云端落地记录（CLOUD_STAGE_VERIFICATION.json、v3_filelist.txt）
├── metadata/
│   ├── CODE_SNAPSHOT.json         # 代码快照身份（583f2c12…）+ 源归档哈希
│   ├── ENVIRONMENT_LOCK.txt       # 云端 Python 依赖锁定（46 包，python 3.12 venv）
│   ├── CONSEQUENCE_STABILITY_PROTOCOL_V1.json / V2.json   # 冻结协议
│   └── patches/                   # 20261013 两个补丁 + 补丁记录（见 §3）
├── _tars/                         # 七个传输归档（gzip -t 全部通过，可独立复验）
│   ├── full_20261013.tar.gz / pilot_20261013.tar.gz / calibration_20261013.tar.gz / raw_inputs_migration_20261013.tar.gz
│   ├── gap_closure_worktree.tar.gz / gap_closure_root.tar.gz / pre_b_v1_20261013.tar.gz
├── _gapcheck/                     # 缺口区比对证据（云端/本地双侧清单、路径列表、抽样文件）
├── VERIFY_FULL_SHA256_20261014.log   # 10536 行逐文件校验日志（全部 OK）
├── SNAPSHOT_MANIFEST.sha256       # 快照顶层全量清单（除自身）
└── SNAPSHOT_README.md             # 本文件
```

## 2. 校验结论（2026-10-14，全部通过）

### 2.1 主归档与执行记录

| 检查项 | 结果 |
|---|---|
| 主归档 `sha256sum -c FULL_20261013_MANIFEST.sha256` | **ok=10536 / bad=0**（100%） |
| `pilot_20261013` / `calibration_20261013` / `raw_inputs_migration_20261013` 清单校验 | ok=386 / 265 / 550，bad=0 |
| 七个 tar.gz `gzip -t` | 全部 OK |
| 服务器↔本地文件数逐树一致 | 10537 / 387 / 266 / 551（各含清单自身） |
| `FULL_20261013_MANIFEST.sha256` 自身哈希 | `f564e16e…616f44`，服务器/本地一致 |
| 关键报告哈希（服务器=本地，逐字节） | VALIDATION_REPORT `21b3d2f4…`；PRECHECK `e11f5c02…`；SUMMARY.md `4ffb017f…`；full_chain.log `f5ee5ab9…` |
| 驱动脚本哈希（8 件，服务器=本地） | full_chain.sh `f33a6516…`、pilot_runner.sh `638f881c…`、full_e1/e2e3/e4.py、gen_full_reports.py `0d159bc7…`、resource_pilot.log `711cfad1…`、授权文件 `470b5d37…` |
| `git bundle verify` | is okay；complete history；HEAD=`ffa74876…` |

### 2.2 功能与科学保真复核（本地独立复核）

| 检查项 | 结果 |
|---|---|
| 18/18 实验终态 | E1/E2E3/E4 六年度全部 `DEVELOPMENT_COMPLETE` |
| E4 协议哈希六年度一致 | `sha256:18db92f0b3e82b52…`（×6） |
| E4 决策六年度一致 | 全部 `N_GRID_UPPER_BOUND_REACHED`（2048≠4096，N*=网格上界） |
| E4 `failed_instances` vs 冻结基线 `data2/reports/paper_formal/{year}/EVAL_SUMMARY.json` | 双向集合差为空：2017/18/19/22=11、2021=12、2020=20（ALL_MATCH） |

### 2.3 缺口区补齐校验（今日新增，全部通过）

| 检查项 | 结果 |
|---|---|
| 云端独有 + 字节变体文件（294 件：YEAR_2018 tail、YEAR_2019–2022、遗留件变体） | 294/294 哈希与云端清单一致 |
| root 包（散件日志、incoming、smoke_gitmeta、upload 包、dev_smoke、p1_semantic 共 86 件） | 86/86 一致 |
| PRE B_V1 适配器 `sha256sum -c PRE_B_V1_MANIFEST.sha256` | 56/56 OK |
| T-100 审计原件（`D:/research/air_slot/raw_audit/t100`，六年度 annual） | 6/6 云地逐字节一致（本地已有，无需下载） |
| 上传源码包 `airslot_source_583f2c1.tar.gz` | `sha256:4e8e64b6…` = CODE_SNAPSHOT.source_archive_sha256 ✓ |
| YEAR_2017 模型 5 件（含 tail MANIFEST） | 与云端逐字节一致（chunks/PROGRESS 33 件为本地补件） |

**遗留件字节差异说明（重要）**：遗留目录（diagnostics / paper_results / 部分 m1 冻结件）中 104 个文件云端与本地字节不同，经抽样与分类确认**全部为行尾差异（云端 LF vs 本地 CRLF），去掉 `\r` 后内容逐字节一致，语义零差异**（与早前 registry CRLF 事件同源：上传/落地过程做了行尾归一化）。本快照对这些文件保存的是**云端 LF 版本**。

## 3. 代码绑定

- **代码快照**：`583f2c12d54297ce6522285b44ff8bf008587308`（`metadata/CODE_SNAPSHOT.json`；源归档 `sha256:4e8e64b6…`，字节已随 upload 包留档）
- **云端部署代码 = 快照 + 2026-10-13 两个已授权补丁**：
  1. `patches/20261013_b_continuity_row_contract_fix.patch` — `F_continuity` 字段访问修复（本地提交 `d1c72a7`，补丁版本 `8cc7a1b7`）→ `model/PRE/reference/data2_m2_train_fit.py` `sha256:28e8067c…`
  2. `patches/20261013_bcu2019_context_fix.patch` — 2019 construction-context 身份修复（本地提交 `ffa7487`，补丁版本 `1d3ba5d3`）→ 同上 + `data2/scripts/build_year_references.py` `sha256:20f4bc90…`
  - 记录：`metadata/patches/PATCH_RECORD_20261013.json`、`PATCH_RECORD_2_20261013.json`
- **本地 git 历史**：bundle HEAD = `ffa74876bf3c4dfa7031da06e59bf91a0f2899ef`（完整历史）
- 环境锁定：`metadata/ENVIRONMENT_LOCK.txt`（torch 2.11.0+cpu 等 46 包）

## 4. 恢复 / 复验方法

```bash
# 复验主归档（在快照根目录）
cd artifacts/experiment/jatm_s34/full_20261013
sha256sum -c FULL_20261013_MANIFEST.sha256        # 期望 10536/10536 OK

# 从 tar 重新解压（如需；_tars 内另有 gap_closure_* 与 pre_b_v1_*）
tar -xzf _tars/full_20261013.tar.gz -C artifacts/experiment/jatm_s34/

# PRE B_V1 复验
cd artifacts/models/pre && sha256sum -c ../../_gapcheck/PRE_B_V1_MANIFEST.sha256   # 56/56 OK

# 快照顶层全量校验（除清单自身）
cd <snapshot-root> && sha256sum -c SNAPSHOT_MANIFEST.sha256

# 代码历史恢复
git clone code/airslot_code_history_20261014.bundle airslot_code && cd airslot_code
git log --oneline -5                               # 顶端应为 ffa7487

# 未入快照但已有本地权威副本（无需云端）：data2/raw 原始数据 34G、input staging、
# raw_audit/t100 审计原件、M5-b 早期产物（本地 D:/research/air_slot 与 code/explore）
```

## 5. 执行事实摘要（摘自 `FULL_EXECUTION_SUMMARY.md`）

- 链条：2026-10-13 13:40:50Z 启动 → 2026-10-14 09:31:02Z 完成，墙钟 **19h50m12s**，机时 **65.9**（E4 23.3 + E2/E3 20.4 + E1 22.2）
- 结果：**18/18 PASS**（官方校验 `all_pass=true`）；零失败、零重启、零重复实例
- 资源：峰值已用 36.6 GiB / 最低可用 85.6 GiB（20 GiB 安全线未接近）；磁盘 75/295 GiB；loadavg 峰值 6.08/32 核
- 两个未建模成本（流程发现）：E4 比较批 ≈20–24 min/档；E1 全量 bootstrap ≈2h/年

## 6. 边界与后续

- 本快照仅为**执行结果与记录的封存**；论文表/科学解释须下一次明确授权。
- Final-Test 全程未访问：全链 `final_test_access_count=0`（见 VALIDATION_REPORT 与各产物）。
- 云端服务器在全部校验通过后关机（本次归档当时点）；关机前复核：无残留实验进程、无 tmux 会话、load≈0。
