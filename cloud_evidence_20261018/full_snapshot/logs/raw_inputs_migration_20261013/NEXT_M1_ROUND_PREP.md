# NEXT M1 ROUND — Authorization Precheck & Compute Plan (2026-10-13)

Static precheck + planning only. **No status was changed to USER_APPROVED; no
training was started.**

## Status matrix (server worktree `/data/airslot/worktree`)

| year | cohort N4096 file | PRE legacy refs | M1 models + manifest | Annual tail | B CU bundle (this round) |
|------|------------------|-----------------|----------------------|-------------|--------------------------|
| 2017 | present (12288 lines) | present | present (built 2026-10-11) | present | building (run2) |
| 2018 | present | present | present | **supplemental build this round** | queued |
| 2019 | present | present | **MISSING → BLOCKED_M1_MISSING** | blocked on M1 | queued |
| 2020 | present | present | **MISSING** | blocked on M1 | queued |
| 2021 | present | present | **MISSING** | blocked on M1 | queued |
| 2022 | present | present | **MISSING** | blocked on M1 | queued |

Reference facts from the 2017/2018 M1 manifests: n=4096 train episodes,
2048 calibration episodes, ~56-58k development nodes, ~57-58k train examples,
tiny checkpoints (~40-50 KB), HISTORY_PRIMARY = FULL_ADAPTIVE_CAUSAL_PREFIX,
CURRENT_COMPARATOR = NO_HISTORY_CURRENT_OBSERVATION, final_test_access_count=0.

## Exact prerequisites and commands (do NOT run until authorized)

1. Authorization record: copy
   `deploy/jatm_cloud/scientific_decisions/M1_TRAINING_AUTHORIZATION_TEMPLATE.json`
   (or the prepared draft `M1_TRAINING_AUTHORIZATION_DRAFT_2019_2022.json`) and
   set `status: USER_APPROVED` + `years` **only after explicit user approval**
   (`cloud_train_models.validate_authorization` refuses anything else).
2. Per-year training (isolated output dir; refuses overwrite if YEAR dir
   non-empty; validates checkpoints via `model_bindings` and writes
   `ANNUAL_M1_TRAINING_RECEIPT.json`):
   `python -m exp.jatm_s34.cloud_train_models --year <Y> --approval <approved record>`
3. Gate observation (read-only) with `require_tail=False`:
   `python -c "from exp.jatm_s34.cloud_inputs import check_year; import json; print(json.dumps(check_year(<Y>, require_tail=False, continuity_contract='JATM_F_CONTINUITY_B_V1'), indent=2, default=str))"`
4. After this round, every year has both CU tracks (YEAR_LOCAL + D4 FIXED_COMMON),
   so the only remaining `check_year` blockers for 2019-2022 will be the M1
   models; tails are then unblocked (decision already USER_APPROVED for
   2017-2022). E1-E4 execution and Final-Test remain NOT authorized.

## Compute plan and recommended parallel configuration

- Measure first: run 2019 alone; record wall time, peak RSS, CPU. Models are
  small (57k train examples, ~50 KB checkpoints) and the pipeline is
  single-process CPU-bound — expected minutes, not hours, but treat as unknown
  until measured.
- Concurrency: after the first measurement, run 2020-2022 with **2-4 parallel
  single-year jobs** if peak RSS per job stays well under ~12 GiB and disk I/O
  is trivial (training writes are MBs). Keep ≥20 GiB RAM free at all times.
- Every job: own output dir `artifacts/models/m1/YEAR_<Y>/`, own log/pid/exit
  records, `OMP_NUM_THREADS=MKL_NUM_THREADS=OPENBLAS_NUM_THREADS=NUMEXPR_NUM_THREADS=1`
  to avoid oversubscription.
- Validation: after each year, `model_bindings` must pass (schema, n=4096,
  episode counts, history modes, hash match, final_test_access_count=0).
- Tails: run after M1 per year (same decision record; tail build is
  resumable via `train_chunks` cache + `PROGRESS.json`).
