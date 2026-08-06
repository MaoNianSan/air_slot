# PRE GitHub Large File Audit（大文件审计）

> 上传审计专用（不上传 GitHub）。生成时间：2026-08-05。

## 结论

`LARGE_FILE_STATUS=PASS` — 无任何 >=10 MiB 的上传候选文件，无 blocker。

## 6.1 已跟踪文件（>=10 MiB）

```
(none)
```

- 已跟踪文件数：253（`git ls-files` 计数；`git ls-files -ci` 无输出说明无已跟踪忽略项）
- 已跟踪总大小：7.39 MB
- 已跟踪最大单文件：2.32 MB（远低于 10 MiB 阈值）

## 6.2 未跟踪且未被忽略的文件（>=10 MiB）

```
(none)
```

未跟踪非忽略文件最大仅约 12.2 KB（`pre/config/schema/legacy_tables.yaml`），
其余候选均为小型源码/测试/配置。

## 分类判定

| 区间 | 判定 | 本项目情况 |
|---|---|---|
| <10 MiB | 通常可接受 | 全部上传候选文件均在此区间 |
| 10–50 MiB | 必须解释必要性 | 无 |
| 50–100 MiB | 默认阻止，除非用户批准 | 无 |
| >=100 MiB | GITHUB_UPLOAD_BLOCKER | 无 |

## 备注

- Core observation / cache / Parquet / 模型二进制均被 `.gitignore` 排除（`*.parquet`、
  `*.joblib`、`/pre/output_core/`、`/pre/cache/`、`/pre/output/`），不在上传候选内，
  因此本项目不需要 Git LFS。
- 本地最大的生成物（staging 578.57 MB、legacy cache 908.50 MB）均位于忽略路径，
  不会进入 Git 索引。
