# Q4 run-scope audit (2026-10-15)

## Question

Did the October–December (Q4/Test) cohort run in the six-year S34 execution, perhaps only under E4?

## Finding

No six-year S34 E1–E4 Q4 evaluation is present in the saved execution. E4 ran its full six-year N-grid on the Development cohort (August–September), not the Q4/Test cohort. E1–E3 are also explicitly Development-only. This conclusion is based on the executed code path and saved run receipts, not just section names or the fact that the temporal-split description mentions Test.

## Code evidence

- `data2/scripts/consequence_stability_battery.py` declares `HARD SCOPE: development window only (Y-08-01..09-30); zero Oct-Dec reads` (lines 9–16).
- Its `load_hash_cohort` materializes only `train`, `calibration`, and `development` keys (lines 110–122); `eval_phase` selects `selected_by_year[year]["development"]` (lines 654–675).
- E4's wrapper invokes only `headroom`, `fit`, `ladder`, and `eval` phases of that battery (`exp/jatm_s34/e4_run.py`, lines 20–49 and 75–105). Its `year_local_rule` labels Oct–Dec as Test; it does not invoke that split.
- S34 E1–E3 use `shared_science.execution_identity`, which hashes only `load_hash_cohort(year)["development"]` and records `split="development"` (`exp/jatm_s34/shared_science.py`, lines 47–87). The full E1–E3 run receipts record zero Final-Test access.

## Saved execution evidence

- `logs/raw_inputs_migration_20261013/bcu_20261013/FULL_EXECUTION_PRECHECK.json`: `all_valid=true`; all six annual input gates, BCU/D4 references, M1 models, and tails are `VALID`; `final_test_access_count=0`.
- `logs/raw_inputs_migration_20261013/bcu_20261013/FULL_EXECUTION_VALIDATION_REPORT.json`: full chain `all_pass=true`; E1, E2/E3, and E4 annual tasks completed; chain `final_test_access_count=0`.
- `artifacts/experiment/jatm_s34/full_20261013/e4/{year}/E4_DEVELOPMENT_MANIFEST.json`: all six years `DEVELOPMENT_COMPLETE`, each with `test_access_count=0` and the Development Aug–Sep / Test Oct–Dec rule.
- Across the 36 E4 N-by-year pass manifests (six years × six N values), all 36 are `PASS`, each has 4,096 evaluation cases, and each has `final_test_access_count=0`.

## Hash / protocol discrepancy

- The official run identity is the 583f2c12 code snapshot plus patch chain `8cc7a1b7` and `1d3ba5d3`, effective commit `ffa74876`. The patches change the year-reference construction context / B-continuity reference builder and tests; `git diff 583f2c12..ffa74876` has no changes to E1, E2/E3, E4, cohort loading, or Test partition logic.
- The official precheck passed; therefore a hash mismatch did not prevent the saved full S34 run from executing.
- An earlier E4 **pilot** did fail because `CONSEQUENCE_STABILITY_PROTOCOL_V1.json` was absent (`PILOT_RESULTS.json`: `PROTOCOL_V1_MISSING`). The authoritative V1 protocol was restored and hash-matched before the subsequent run. This was a pilot protocol-anchor issue; it did not turn the full run into Q4 evaluation.
- The local pre-read hash-audit attempts in this folder are not official execution evidence: one was called with the B continuity contract against R1-only local bindings; the other additionally lacked the fixed-common D4 bundle in this isolated root. Their missing-path errors do not establish a prior execution hash failure. Bind the exact cloud B/D4 assets and patched code before any new Q4 read.

## Historical exception

The separately recorded earlier 2019 Q4 experiment remains prior exposure. It is not the six-year S34 E1–E4 extension; keep 2019 labeled as an exposed-window replication if the extension proceeds.

## Access status for the proposed extension

The 18 Q4 raw CSV files have only been inventoried by path and filesystem metadata. Their contents have not been read. The new extension access counter remains zero, and no Q4 outcome computation has started.
