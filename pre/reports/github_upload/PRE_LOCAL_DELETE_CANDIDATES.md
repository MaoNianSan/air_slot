# PRE Local Delete Candidates（本地删除候选清单）

> 上传审计专用（不上传 GitHub）。生成时间：2026-08-05。
> 原则：只列出能明确证明为临时/可再生/不影响恢复的项；**本次不实际删除**。

## 1. 已实际清理的临时项（可再生，已删除）

| 路径 | 大小 | 理由 |
|---|---|---|
| `.pytest_cache/` | ~25 KB | pytest 标准缓存，可再生成 |
| `overall_adv/.pytest_cache/` | ~1.9 KB | 同上 |
| `overall_run/.pytest_cache/` | ~9.8 KB | 同上 |
| `part_adv/.pytest_cache/` | ~1.7 KB | 同上 |
| `pre/.pytest_cache/` | ~3 KB | 同上 |

未发现 `__pycache__/`、`*.pyc`、`*.pyo`、`.mypy_cache/`、`.ruff_cache/`、
`.coverage`、`htmlcov/`、`*.swp`、`*.swo`、`*.tmp`、`*.bak`、Codex scratch 文件。

## 2. 已确认保留（禁止删除）

| 路径 | 说明 |
|---|---|
| `pre/cache/state_extract_core_v1-6840ae55cc35` | **当前 Core cache**（285.18 MB, 120/120 分区, cache key 6840ae55cc35） |
| `pre/cache/state_extract_v2` | **legacy cache**（908.50 MB, 2026-07-27）；Phase 1 等价性 run 仍 CACHE HIT 使用，不可删 |
| `pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b` | **当前 Core staging**（578.57 MB, 29 分区, 10,544,721 行） |
| `pre/output/fast` 及 `pre/output/middle`、`pre/output/phase1_equivalence` | legacy 输出，Phase 1 接受输出与等价性证据 |
| `pre/pre/output/phase1_equivalence` | 嵌套 legacy 输出（见下，列为候选但本次不删） |
| `pre/reports/**` | 全部本地 debug/审计报告 |
| 全部 parquet partition / manifest / registry / schema YAML / column audit / test fixture | 审计与恢复所需 |

## 3. 旧 staging / cache 分析（候选，本次不删除）

### 3.1 概览

| 路径 | 大小 | mtime | 有 manifest? | 与当前兼容性判断 |
|---|---|---|---|---|
| `pre/cache/state_extract_core_v1-6840ae55cc35` | 285.18 MB | 2026-08-04 20:43 | `cache_manifest.json` | **当前**（key=6840ae55cc35） |
| `pre/cache/state_extract_core_v1-d86413cad17a` | 196.59 MB | 2026-08-04 19:54 | `cache_manifest.json` | 旧 key（d86413cad17a），早于当前 6840 约 49 分钟；大小小于当前，疑似未完成/旧 config 产物 |
| `pre/cache/state_extract_v2` | 908.50 MB | 2026-07-27 07:43 | `cache_manifest.json` | legacy cache；**等价性 run 仍 HIT 引用，必须保留** |
| `pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b` | 578.57 MB | 2026-08-04 21:16 | 无 | **当前 Core staging**（观测证据） |
| `pre/output_core/smoke` | 0 B | 2026-08-04 20:24 | 无 | 空目录，无害 |
| `pre/output/phase1_equivalence` | 189.43 MB | 2026-08-04 18:59 | `run_state.json` | legacy 等价性输出（对照证据） |
| `pre/pre/output/phase1_equivalence` | 4.68 MB | 2026-08-04 18:31 | `run_state.json` | 嵌套重复输出，疑似 cwd 误用产物；与 `pre/output/phase1_equivalence` 疑似副本 |

### 3.2 判断结论

- **可删除候选（本次不删）**：
  - `pre/cache/state_extract_core_v1-d86413cad17a` — 与当前 key 不一致、时间更早、体积更小；若后续确认当前 cache
    完整（120/120）且 d864 无独立引用，可视为废弃副本。**删除前需由用户确认**。
  - `pre/pre/output/phase1_equivalence` — 疑似 `pre/output/phase1_equivalence` 的重复副本（嵌套 pre/ 目录异常）；
    已确认被 `pre/.gitignore` 的 `output/` 规则忽略（不会上传）。若确认无任何代码/脚本引用，可删。**删除前需由用户确认**。
- **保留**：`state_extract_v2`（legacy run 依赖）、当前 staging/cache、`pre/output/phase1_equivalence`（等价性证据）。
- `pre/output_core/smoke` 空目录：在受保护目录内，不删，无害。

> 本次全部候选均未实际删除，等待用户确认。
