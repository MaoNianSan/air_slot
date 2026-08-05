# PRE Core V2 GitHub sync readiness

Date: 2026-08-05

```text
GITHUB_SYNC_READY=YES
CORE_SOURCE_INCLUDED=YES
CORE_TESTS_INCLUDED=YES
CORE_CONFIG_INCLUDED=YES
PUBLISHED_REPORTS_INCLUDED=YES
BENCHMARK_TOOL_INCLUDED=YES
OUTPUT_EXCLUDED=YES
CACHE_EXCLUDED=YES
STAGING_EXCLUDED=YES
RAW_DATA_EXCLUDED=YES
PARQUET_EXCLUDED=YES
LOCAL_PATH_SCAN=PASS
SECRET_SCAN=PASS
DIFF_CHECK=PASS
COMPILE_STATUS=PASS
TEST_STATUS=PASS_74_TESTS
UNRESOLVED_UPLOAD_RISKS=NONE
```

## Verification record

- Branch: `main`
- HEAD and `origin/main` before upload: `f09e939c0b4831a2fdbe1a262e542ba709355bb5`
- `python pre/tools/pre_core_v2_membership_benchmark.py --help`: PASS
- `python -m compileall -q pre/src pre/tests pre/tools`: PASS
- `python -m pytest -q pre/tests`: 74 passed in 12.38 seconds
- `git diff --check`: PASS
- Upload candidates outside the explicit allowlist: 0
- Upload candidates at or above 1 MB: 0
- Parquet upload candidates: 0
- Runtime artifact upload candidates: 0
- Local absolute-path scan hits: 0
- Secret-pattern scan hits: 0
- `git add -n .`: PASS; dry-run only

The published directory contains small implementation and pre-run validation
evidence only. It does not contain a formal `AIR_CHAIN_CORE_V2` Fast bundle.
No Fast run, real `git add`, commit, branch creation, or push was performed.
