# PRE GitHub Upload Audit（上传前审计报告）

> 本地审计报告，**不上传 GitHub**。生成时间：2026-08-05。
> 审计基线：`PRE_UPLOAD_BASELINE.txt`（Phase 1）。

## 1. 当前 Git commit

```
HEAD = 7f5f36703fd6d97a050fc3d2a4c1f84681f9bf1f
branch = main
```

## 2. 当前修改文件（M）

```
M .gitignore                     # 追加 PRE V2 本地运行产物忽略分组
M data/README.md                 # 移除本地绝对路径（中性化）
M pre/.gitignore                 # 重写为 output/output_core/cache/reports 分组
M pre/README.md                  # 移除本地绝对路径（中性化）
M pre/main.py                    # Core CLI 命令与 legacy 并存
M pre/src/pipeline.py            # Core 入口导出
M pre/src/pipeline_build.py      # 瘦身 legacy 编排器（27 行）
M pre/src/pipeline_config.py     # legacy/Core schema 拆分加载
M pre/src/pipeline_publish.py    # 发布拆分后的兼容门面
M pre/src/snapshot.py            # snapshot 拆分后的兼容门面
M pre/tests/conftest.py          # Core 测试共享 fixture 路径
```

## 3. 当前新增文件（??，均为源码/测试/配置）

```
pre/config/schema/{column_aliases,column_roles,core_tables,legacy_tables}.yaml  (4)
pre/src/{artifact_registry,bundle_writer,column_audit,column_audit_report,
  column_audit_sources,contract_enrichment,legacy_snapshot_grid,run_metadata,
  snapshot_reference_enrichment,state_feature_resolver,state_quality}.py       (11)
pre/src/core/*.py                                                                (22)
pre/src/stages/*.py                                                              (8)
pre/tests/{core_fixtures,test_chain_ambiguity,test_chain_builder,test_chain_split,
  test_column_registry,test_core_idempotence,test_core_manifest,test_event_availability,
  test_event_contract,test_observation_native_dedup,test_observation_requests,
  test_reference_train_only}.py                                                (12)
```

## 4. 当前删除文件（D）

```
D pre/config/schema.yaml
```

**解释**：被 `pre/config/schema/` 下 4 个拆分文件值等价替代。已程序化验证：
统一 legacy schema 对象与旧 `schema.yaml` **VALUE_EQUAL=True**（键集合与值完全一致；
`_load_schema` 读取 legacy_tables.yaml(tables,consumers) + column_roles.yaml
(m1_required_inputs,evidence_completeness_features) + column_aliases.yaml(aliases)）。
删除不是遗漏。

## 5. .gitignore 修改内容

### 根目录 `.gitignore`（追加，未删除任何既有规则）

```gitignore
# ===== PRE V2 Local Runtime Artifacts =====
/pre/output_core/
/pre/output/
/pre/cache/
/pre/reports/
/PRE_DEBUG_STATUS.md
/PRE_GITHUB_UPLOAD_AUDIT.md
/PRE_GITHUB_UPLOAD_FILELIST.txt
/PRE_GITHUB_UPLOAD_BLOCKERS.txt
.mypy_cache/
.ruff_cache/
.pyright/
```

既有规则保留：`data/raw/`、`*.parquet`、`*.joblib`、`analysis/`、`reports/`、
`.staging/`、`*.tmp`、`*.bak`、`*.backup`、Python/IDE/OS/环境分组。
未增加过宽规则（`*.yaml|*.json|*.csv|*.md|pre/|tests/|config/|src/`）。

### `pre/.gitignore`（重写为）

```gitignore
# Generated legacy PRE output
output/
# Generated PRE Core output and staging
output_core/
# Reusable local caches
cache/
# Local audit/debug reports
reports/
```

未忽略 `src/ tests/ config/ README.md main.py clean.py`。

## 6. 被忽略的 output/cache/staging 路径（验证：check-ignore exit=0）

```
pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b   -> pre/.gitignore output_core/
pre/cache/state_extract_core_v1-6840ae55cc35                   -> pre/.gitignore cache/
pre/reports/local_debug/PRE_LOCAL_RECOVERY_SUMMARY.md          -> pre/.gitignore reports/
pre/output/fast/**                                             -> pre/.gitignore output/
pre/pre/output/** (嵌套 legacy)                                -> pre/.gitignore output/
```

源码/配置确认不被忽略（check-ignore exit=1，无输出）：
`pre/src/core/pipeline.py`、`pre/tests/test_core_manifest.py`、
`pre/config/schema/core_tables.yaml`、`pre/README.md`。→ `GITIGNORE_STATUS=PASS`

## 7. 被取消跟踪但保留本地的文件

```
无（git ls-files -ci --exclude-standard 无输出：没有任何已跟踪文件被 ignore 命中）
```

无需 `git rm --cached`；未对仓库运行无差别 `git rm -r --cached .`。

## 8. dry-run 上传文件列表

见 `PRE_GITHUB_UPLOAD_FILELIST.txt`（70 行：add 69 + remove 1）。
分类：SAFE_SOURCE 46 / SAFE_TEST 13 / SAFE_CONFIG 4 / SAFE_DOCUMENTATION 2 /
EXPECTED_DELETE 1（schema.yaml）；SUSPICIOUS_* 与 UNRESOLVED 均无。
禁止上传模式（data/raw、pre/cache、pre/output、pre/output_core、pre/reports、
*.parquet、*.joblib、*.log、*.tmp、*.bak、*.staging）在 dry-run 中零命中。

## 9. 大文件审计

见 `PRE_GITHUB_LARGE_FILE_AUDIT.md`。`LARGE_FILE_STATUS=PASS`
- 已跟踪 253 文件共 7.39 MB，最大 2.32 MB（<10 MiB）。
- 未跟踪非忽略最大 12.2 KB。
- 无 >=10 MiB 文件；无 blocker；不需要 Git LFS。

## 10. secret 审计

见 `PRE_GITHUB_SECRET_AUDIT.md`。`SECRET_SCAN_STATUS=PASS`
- gitleaks 未安装 → 使用本地正则只读扫描（TOOL_UNAVAILABLE 已记录，未联网安装）。
- 文件名扫描：无命中。
- 内容扫描（私钥/GitHub/AWS/Google/sk-/Bearer/password/api_key/access_token/
  refresh_token/client_secret/数据库连接串/内网 URL/用户名）：无命中。
- 邮箱仅出现在第三方公开许可证 `data/source_docs/opensky/LICENSE.txt`
  （`contact@opensky-network.org`，公开文本，非秘密）。
- remote URL `https://github.com/MaoNianSan/air_slot.git` 无凭据嵌入。

## 11. 本地路径审计

`LOCAL_PATH_STATUS=PASS`
- 发现 2 处并已修复：`data/README.md:5`、`pre/README.md:48` 中的
  `D:\research\air_slot\code\explore` 绝对路径 → 中性描述。
- 复扫 `D:\research\`/`C:\Users\`/`/home/`/`/Users/`：无命中。

## 12. 测试结果

```
python -m pytest pre/tests -q  ->  41 passed in 13.74s
```
`TEST_STATUS=PASS`（>= 已知 41 项要求）。

## 13. compile 结果

```
python -m compileall -q pre/src pre/tests  ->  exit 0
```
`COMPILE_STATUS=PASS`

## 14. diff check 结果

```
git diff --check  ->  exit 0（仅 LF->CRLF 换行提示，无空白错误）
```
`DIFF_CHECK_STATUS=PASS`

## 15. raw data 是否修改

`RAW_DATA_LEAK=NO`；`git diff --name-only -- data/raw` 为空。`data/manifests/` 未修改。

## 16. legacy output 是否保留

`LEGACY_OUTPUT_PRESERVED=YES`：`pre/output/fast`（acceptance run
`pre-fast-20260803T022638Z-64115215`, PASS）、`pre/output/middle`、
`pre/output/phase1_equivalence`、`pre/pre/output/phase1_equivalence` 均保留，
且被 `pre/.gitignore` 忽略不会上传。

## 17. Core staging 是否保留

`CORE_STAGING_PRESERVED=YES`：`pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b`
（578.57 MB，29 分区，10,544,721 行）保留，被忽略不会上传。

## 18. cache 是否保留

`CACHE_PRESERVED=YES`：当前 Core cache `pre/cache/state_extract_core_v1-6840ae55cc35`
（285.18 MB，120/120 分区）与 legacy cache `pre/cache/state_extract_v2`
（908.50 MB，legacy run 仍 HIT 使用）均保留，被忽略不会上传。

## 19. 未解决风险

（均为**开发/科学**风险，**不阻塞上传**；上传层面无未解决项）

1. `RAW_COLUMN_RETENTION`：Core 未保留全部审计 raw 列（state callsign/alert/spi/squawk、
   geoaltitude、lastposupdate、lastcontact、METAR sky/raw-report 等）。
2. `COLUMN_LEVEL_EVIDENCE`：observation evidence 为分区级摘要，非最终列级血缘。
3. `UNVERIFIED_STAGING_RESUME`：staging resume 未验证 config/request/code hash 与 manifest；
   恢复路径改动（九列投影+文件字节哈希）未对完整 staging 验证。
4. `UNSUPPORTED_OPERATIONAL_EVENTS`：无官方 AOBT/AIBT/ATOT/ALDT/SOBT/rotation/cancel/diversion/swap。
5. `column_audit.py` 当前未被任何源码/测试 import（独立 Phase 2 审计工具模块，产出
   `PRE_DATASET_COLUMN_AUDIT.csv`）；属真实源码，保留，建议后续补 import 或测试引用。
6. `snapshot_reference_enrichment.py:232` 有 `except Exception: pass`（受控抑制单行
   enrichment 失败，配合 missing_reason 语义，符合 legacy empty-result 设计）——记录非问题。
7. `pre/README.md` 未描述拆分 schema 布局（可选文档补充；README 历史上未描述过 schema.yaml）。

## 20. 用户手动上传前的命令建议

```powershell
# 1. 复核状态（应只看到上表第 2/3/4 节的源码级变更）
git status --short --untracked-files=all

# 2. 复核 dry-run 清单（不应出现任何 output/cache/staging/reports/parquet）
git add -n .

# 3. 加入暂存区（用户自行决定）
git add .gitignore pre/.gitignore data/README.md pre/README.md pre/main.py `
  pre/src pre/tests pre/config

# 4. 再次复核将要提交的内容
git status
git diff --cached --stat

# 5. 提交与推送（用户自行执行）
# git commit -m "..."
# git push origin main
```

> 提示：`pre/reports/` 与全部本地审计报告均被忽略，不会上传；
> 本次审计报告留在本地即可，无需推送。

---

## 最终状态

```text
GITHUB_UPLOAD_READY=YES
GITIGNORE_STATUS=PASS
GENERATED_ARTIFACT_LEAK=NO
RAW_DATA_LEAK=NO
CACHE_LEAK=NO
STAGING_LEAK=NO
SECRET_SCAN_STATUS=PASS
LARGE_FILE_STATUS=PASS
LOCAL_PATH_STATUS=PASS
DIFF_CHECK_STATUS=PASS
COMPILE_STATUS=PASS
TEST_STATUS=PASS
UNINTENTIONAL_DELETE=NO
KNOWN_BLOCKERS=
```

判定依据（全部满足）：
- output/cache/staging/reports 不在上传候选 ✓
- raw data 不在上传候选 ✓
- 无 secret ✓
- 无大文件 blocker ✓
- 无本地绝对路径泄漏 ✓
- 无无法解释的删除 ✓（唯一删除 schema.yaml 已值等价验证）
- compile 通过 ✓
- 测试通过（41 passed）✓
- `git diff --check` 通过 ✓
- `.gitignore` 未误伤源码/测试/配置 ✓

> 说明：`KNOWN_BLOCKERS` 为空指**上传阻塞**为空；第 19 节列出的开发/科学 blocker
> 不影响上传就绪，但影响后续 PRE 完整重跑。
