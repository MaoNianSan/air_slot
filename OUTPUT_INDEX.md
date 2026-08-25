# Output index

Generated files are intentionally separated from source code. The three roots
have different meanings:

| Root | Use | Start here |
| --- | --- | --- |
| `outputs/` | Runtime, bounded smoke, fixture, and reserved publication outputs | `outputs/runtime/`, `outputs/real_smoke/`, `outputs/formal/` |
| `artifacts/` | Versioned diagnostics, experiment artifacts, caches, and archived artifacts | `artifacts/diagnostics/`, `artifacts/experiments/`, `artifacts/experiment/` |
| `reports/` | Human-readable audit and validation reports | `reports/REGRESSION_TEST_REPORT.md`, `reports/REFACTOR_REPORT.md`, and the topic subdirectories |

## Where to find the current local results

- Foundation/runtime validation: `outputs/runtime/foundation_validation/validation_result.json`
- M2 smoke context and consequences: `outputs/runtime/m2_smoke/`
- Data2 M1 fast runs: `outputs/runtime/data2_m1_fast_2019_full_year_wx_v2_rl5/`
- Bounded Data2 smoke: `outputs/real_smoke/data2_m1_bounded_smoke_v2/` and `outputs/real_smoke/data2_m1_m4_bounded_chain/`
- Formal fixture output: `outputs/formal/foundation_fixture/foundation-data1/`
- Development and diagnostic manifests: `artifacts/diagnostics/**/**/*MANIFEST*.json` and the adjacent result JSON
- Archived temporary Exp2 package: `artifacts/_archive/2026-08-25/exp2_development_temp/`
- Draft result map: [`DRAFT_RESULTS_INDEX.md`](DRAFT_RESULTS_INDEX.md)
- Human-readable summaries: `reports/`

## Interpretation rules

1. A filename or directory name is not a scientific promotion decision.
   Read the adjacent manifest/status JSON and current registry before using an
   artifact as evidence.
2. `outputs/paper_candidate/`, `outputs/manuscript_values/`, and
   `outputs/evaluation/` are reserved locations; their README files describe
   whether they are populated.
3. `artifacts/_archive/` contains superseded or duplicate artifacts and is not
   the first place to search for current results.
4. `outputs/` and `reports/` are locally generated and ignored by Git. Their
   absence from `git status` is expected; this index is the tracked entry point.

## Snapshot from 2026-08-25

- `outputs/`: 7 top-level groups, 56 files including nested files.
- `artifacts/`: 6 top-level groups, more than 9,000 files; diagnostics are the
  largest group and contain many historical/versioned runs.
- `reports/`: 11 topic groups plus 4 root reports.

Use the paths above instead of searching the whole repository. New runners
should place runtime results under `outputs/` and formal/diagnostic lineage
artifacts under `artifacts/`, with a manifest in the same directory.
