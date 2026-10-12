# M5-b Cohort-Size Study — ZCodex Autonomous Execution Plan V3

## 0. Purpose and authority

This is an execution plan for ZCodex. It is not a result report and it is not permission to retrain the scientific models.

This document is an autonomous-runner specification, not a checklist for a human operator. ZCodex must execute the permitted phases itself, reuse completed artifacts, resume from the last successful phase, write machine-readable status files, and stop with a typed status when a required artifact or authorization is absent. It must not wait for a human to choose the next routine step.

The runner must be non-interactive. Do not ask for confirmation during a permitted phase. If a human decision is required, write the decision request to the status and report, terminate the current run cleanly, and return the exact status token defined below.

The runner must be idempotent. Before every command, it must check whether the corresponding output is already complete and hash-compatible. A complete output must be reused. A partial or hash-incompatible output must be quarantined under an `incomplete/` subdirectory and reported; it must not trigger raw-data reprocessing automatically.

The plan separates:

1. the already completed 2017--2022 PRE-state materialization;
2. read-only audit of those existing artifacts;
3. optional PRE-observable diagnostics;
4. a consequence-side pilot that is executable only when ZCodex is launched explicitly with `--mode pilot`; audit mode never enters that battery.

If this plan conflicts with repository authority, stop and follow:

- AGENTS.md;
- REPOSITORY_AUTHORITY.md;
- frozen scientific registries under registries/;
- the current model and experiment contracts.

When a scientific definition is unclear, return HUMAN_DECISION_REQUIRED. Do not guess.

## 1. Canonical paths

Repository:

~~~text
D:\research\air_slot\code\explore
~~~

Existing multi-year PRE materialization:

~~~text
data2/reports/cohort_size_stability/
~~~

Existing run log:

~~~text
data2/logs/m5_phaseD_5years.log
~~~

Scripts:

~~~text
data2/scripts/cohort_size_study.py
data2/scripts/cohort_size_metrics.py
~~~

## 1.1 Autonomous runner contract

The autonomous program must implement the following state machine in this order. The current requested mode is the development-only pilot mode defined in the attached M5-b authority document, so the program must be able to run the consequence-side pilot automatically after the protocol and artifact gates pass.

~~~text
INIT
  -> PREFLIGHT
  -> REUSE_ARTIFACT_AUDIT
  -> PROTOCOL_GATE
  -> DETERMINISM_SENTINEL
  -> M2_REFERENCE_GATE
  -> FIT_SIZE_STABILITY
  -> EVAL_SIZE_STABILITY
  -> PILOT_REPORT
  -> HARD_STOP
~~~

The pilot mode permits M1 training and calibration only for 2019 and 2020, only on the existing hash-ranked Train/Calibration/Development cohorts, and only for the development-window stability battery. It never permits Final-Test access, Section-4 rerun, COMMON_N_STAR freeze, or expansion to 2017/2018/2021/2022 or N=8192.

The program must also support `--mode audit`. Audit mode executes only `PREFLIGHT`, `REUSE_ARTIFACT_AUDIT`, `PRE_METRICS`, and `CONSEQUENCE_INTERFACE_AUDIT`, then stops. Pilot mode is the mode requested for the autonomous consequence-side run.

The runner must create or update the following control files under the existing study root:

~~~text
data2/reports/cohort_size_stability/AUTORUN_STATE.json
data2/reports/cohort_size_stability/AUTORUN_REPORT.md
data2/reports/cohort_size_stability/AUTORUN.log
~~~

`AUTORUN_STATE.json` must contain at least:

~~~text
run_id
started_at
updated_at
repo_root
git_head
git_branch
current_state
completed_states
failed_state
status
input_manifest_hash
outputs_manifest_hash
final_test_access_count
model_retrained
model_recalibrated
consequence_side_executed
next_action
~~~

At startup, read `AUTORUN_STATE.json` if it exists. Resume from the first incomplete state only when all earlier state outputs still pass their recorded hashes. If the state file is missing, initialize a new run. If the state file is malformed or an output hash has changed unexpectedly, write `BLOCKED_AUTORUN_STATE_CORRUPT` and stop without deleting or rewriting scientific artifacts.

Each state must be committed to `AUTORUN_STATE.json` only after its outputs have been flushed and hash-checked. A process interruption must therefore permit safe continuation from the last completed state.

The runner must use exit-status handling rather than textual guesses. A command exit code other than zero, a missing required output, or a failed invariant must produce a typed failure status and stop the dependent states.

### 1.2 Required wrapper functions

The autonomous wrapper must have separate functions (or equivalent isolated units) for:

~~~text
load_or_initialize_state()
acquire_single_run_lock()
collect_repository_provenance()
build_input_manifest_without_test_paths()
audit_pre_materialization()
run_or_reuse_pre_metrics()
audit_consequence_interfaces_without_execution()
freeze_or_verify_protocol()
run_determinism_sentinel()
reuse_or_build_year_references()
run_fit_size_stability()
run_eval_size_stability()
apply_stability_decision_tree()
write_atomic_state_and_report()
release_single_run_lock()
~~~

The lock must be acquired before reading or writing the control files. If another live runner owns the lock, return `BLOCKED_AUTORUN_ALREADY_RUNNING`; do not kill the other process. If a stale lock is detected, preserve it as evidence and return `BLOCKED_AUTORUN_STALE_LOCK` unless the user explicitly authorizes stale-lock recovery.

`build_input_manifest_without_test_paths()` must hash only the existing PRE summaries, ranked cohort records, N-level PRE files, source scripts, configuration, and registries required by the audit. It must reject any path containing `final_test`, `test`, October, November, or December before opening it. This is a path-safety guard, not a substitute for the per-file Final-Test audit.

All control-file writes must be atomic: write a temporary file in the same directory, flush it, replace the target, and then hash the final file. Never truncate an existing state file in place.

## 2. Hard rule: reuse all existing 2017--2022 preprocessing

The 2017--2022 preprocessing and PRE-state materialization already exist and must be reused directly.

The previous collection command is recorded only as provenance for artifacts that are already on disk. It is not an instruction to run it again. In particular, `cohort_size_study.py --collect` performs a lightweight January--September scan to enumerate and hash-rank episodes. That scan has already been completed for the newly materialized years, and the ranked records are now inputs. Repeating the scan would violate the reuse requirement.

Do not:

- redownload raw data;
- rebuild 2017--2022 input files;
- rerun monthly chain enumeration;
- rerun hash-ranked pool collection;
- regenerate HASH_SELECTED_COHORT_RECORDS_N4096.jsonl;
- regenerate existing PRE_DEVELOPMENT_STATES.jsonl;
- rebuild yearly taxi or turnaround references;
- overwrite existing materialization summaries;
- change data preprocessing semantics;
- change the temporal split rule;
- change the fixed hash seed;
- create a second preprocessing pipeline.

Do not invoke `cohort_size_study.py --collect` or the materialization command again merely because a downstream report is absent. First audit the existing JSONL and N-level directories. A missing report is a reporting problem; it is not permission to recreate the source cohort.

If a downstream step cannot run from existing artifacts, return:

~~~text
BLOCKED_MISSING_PRECOMPUTED_ARTIFACT
~~~

Do not solve this status by rerunning preprocessing.

The only allowed new files in this plan are the audit/diagnostic reports and, if absent, the single autonomous orchestration wrapper named in Section 6.0:

~~~text
data2/reports/cohort_size_stability/
~~~

~~~text
data2/scripts/run_m5b_autonomous.py
~~~

The only allowed source modification for pilot mode is the minimal implementation of the currently stubbed EVAL phase in `data2/scripts/consequence_stability_battery.py` (or one directly imported helper module), plus the autonomous wrapper. No model definition, registry, raw-data, preprocessing, manuscript, or JATM Section-5 driver may be modified.

## 3. Forbidden operations

Do not read, materialize, overwrite, or regenerate:

~~~text
October--December 2017--2022 test data
artifacts/experiment/final_test_v2*
formal/FINAL_TEST_COHORT_AUTHORITY_V1.json
frozen registries
~~~

In `--mode audit`, do not execute:

~~~text
M1 retraining
M1 recalibration
Final-Test evaluation
formal paper experiment drivers
git commit
git push
git reset --hard
git clean
git checkout -- file
Remove-Item -Recurse
~~~

In `--mode pilot`, M1 retraining and calibration are permitted only inside the existing `data2/scripts/consequence_stability_battery.py` FIT/SENTINEL path, for years 2019 and 2020, and only after the protocol gate passes. All other prohibitions remain active. The pilot must not call `exp/jatm_section5/run_development.py`, because that is a separate JATM Section-5 orchestration path rather than the M5-b FIT/EVAL battery.

## 4. Scientific layer definitions

### 4.1 PRE-observable layer

This layer uses only existing development PRE-state files. It can report:

- episode count;
- node count;
- states per episode;
- operating-stage composition;
- weather admissibility;
- evidence-ledger admissibility;
- taxi and turnaround support;
- target-support composition;
- descriptive ranking stability based on existing reference quantities;
- episode-level bootstrap precision for PRE-observable quantities.

It cannot establish:

- M1 training stability;
- M1 calibration stability;
- seven-component consequence stability;
- Stage-I shortlist stability;
- Stage-II target stability;
- L_att stability;
- L_rec stability;
- a final cohort-size contract.

### 4.2 Consequence-side layer

This layer would require M1/M2 and downstream decision computation. It would answer whether changing cohort size changes:

- Flight, Passenger, and Resource consequences;
- Stage-I screening;
- Stage-II local-recovery activation;
- effective target selection;
- L_att;
- L_rec.

In `--mode pilot`, this layer is executed only for the 2019 and 2020 development-window pilot after the protocol, PRE-artifact, determinism, and M2-reference gates pass. In `--mode audit`, it remains design-only and is not executed.

### 4.3 Final-Test layer

Final Test is out of scope. Any command or file access involving test, Final Test, or October--December data must stop immediately.

## 5. Existing completed run

The completed command was:

~~~text
python -u data2/scripts/cohort_size_study.py --collect --materialize --years 2017 2018 2020 2021 2022 --n 128 256 512 1024 2048 4096
~~~

The process exited with code 0. It completed collection and materialization for 2017, 2018, 2020, 2021, and 2022. Corresponding 2019 artifacts already existed and must be reused.

Observed pool counts:

| year | train | calibration | development |
|---:|---:|---:|---:|
| 2017 | 2,052,860 | 378,604 | 711,892 |
| 2018 | 2,628,470 | 481,415 | 910,427 |
| 2019 | 2,665,240 | 490,886 | 946,184 |
| 2020 | 1,637,411 | 239,916 | 477,873 |
| 2021 | 1,809,799 | 419,705 | 799,702 |
| 2022 | 2,352,702 | 434,494 | 838,441 |

Observed development-node counts:

| year | N=128 | N=4096 |
|---:|---:|---:|
| 2017 | 1,805 | 56,191 |
| 2018 | 1,725 | 58,083 |
| 2019 | 1,885 | 58,681 |
| 2020 | 2,370 | 65,967 |
| 2021 | 2,062 | 63,884 |
| 2022 | 1,993 | 65,877 |

These facts describe PRE-state materialization only. They do not identify a consequence-side N-star.

## 6. Phase 0 — read-only preflight

### 6.0 Runner behavior

The runner must execute Phase 0 automatically from the canonical repository root. The operator should only need to launch the runner once; no manual command copying is required after launch.

The runner may be implemented as a new orchestration script, but it must not modify the scientific model implementations. A suitable location is:

~~~text
data2/scripts/run_m5b_autonomous.py
~~~

If that wrapper already exists, reuse it. If it does not exist, ZCodex may create only this orchestration wrapper and the control/report files listed in Section 1.1. It must not create a replacement cohort, M1, M2, or decision implementation.

The wrapper must invoke commands in subprocesses with captured stdout, stderr, return code, start time, end time, and command hash. In `--mode audit`, the minimum permitted command sequence is:

~~~powershell
python data2/scripts/cohort_size_metrics.py --years 2017 2018 2019 2020 2021 2022
~~~

In `--mode pilot`, the wrapper must execute the following sequence automatically, caching each completed phase and resuming after interruption:

~~~powershell
python data2/scripts/consequence_stability_battery.py --phase sentinel --years 2019
python data2/scripts/build_year_references.py --years 2019 2020
python data2/scripts/consequence_stability_battery.py --phase fit --years 2019 2020 --n 128 256 512 1024 2048 4096
python data2/scripts/consequence_stability_battery.py --phase eval --years 2019 2020 --n 128 256 512 1024 2048 4096
~~~

The checked-out battery currently exposes `sentinel`, `fit`, and `eval` phases, but its `eval` phase is not yet implemented and currently raises `NotImplementedError`. Therefore the autonomous wrapper must first perform a code/interface gate. It may implement the missing evaluation and bootstrap layer in the existing battery file, preserving the frozen protocol and existing FIT outputs, but it must not proceed to pilot metrics while `eval` remains a stub. A stub must produce `BLOCKED_CONSEQUENCE_INTERFACE`, not a false-success report.

The wrapper must verify the actual command-line parser before launching. If a listed flag such as `--n` is unsupported by the checked-out script, update the script interface in a reviewable, contract-preserving change or pass the values through the wrapper's Python API. It must never silently drop the requested N grid, bootstrap seed, or year scope.

The wrapper must not invoke:

~~~powershell
python data2/scripts/cohort_size_study.py --collect ...
python data2/scripts/cohort_size_study.py --materialize ...
python exp/jatm_section5/run_development.py
~~~

The first two commands would recreate already available preprocessing/materialization. The third command is a different JATM Section-5 orchestration path and is outside this M5-b pilot contract. The wrapper must record those commands as `NOT_EXECUTED_BY_CONTRACT`, not silently skip them.

If `cohort_size_metrics.py` has already produced reports whose input hashes match the current materialization audit, reuse them and mark `PRE_METRICS` as `REUSED`. Do not rerun only to refresh timestamps.

At the end of each state, append one JSON line to `AUTORUN.log` with fields `state`, `event`, `status`, `command`, `return_code`, `output_paths`, `input_hashes`, and `timestamp`.

Run from the repository root:

~~~powershell
git status --short
git branch --show-current
git rev-parse HEAD
Get-Content -Raw AGENTS.md
Get-Content -Raw REPOSITORY_AUTHORITY.md
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'cohort_size|M5|PRE_MULTIYEAR' } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine,CreationDate
~~~

Confirm:

1. the root is the canonical repository;
2. no Final-Test process is running;
3. no frozen artifact is being written;
4. current branch and HEAD are recorded;
5. pre-existing dirty files are listed and left untouched;
6. existing 2017--2022 materialization directories are present.

If any item fails, write no scientific output and return:

~~~text
BLOCKED_PRECHECK
~~~

## 7. Phase 1 — audit existing materialization

For each year Y in 2017, 2018, 2019, 2020, 2021, 2022, inspect:

~~~text
data2/reports/cohort_size_stability/Y/HASH_RANKED_POOL_SUMMARY.json
data2/reports/cohort_size_stability/Y/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl
data2/reports/cohort_size_stability/Y/N128/
data2/reports/cohort_size_stability/Y/N256/
data2/reports/cohort_size_stability/Y/N512/
data2/reports/cohort_size_stability/Y/N1024/
data2/reports/cohort_size_stability/Y/N2048/
data2/reports/cohort_size_stability/Y/N4096/
~~~

Do not regenerate these files.

For every year and every N, check:

1. MATERIALIZE_SUMMARY.json exists;
2. materialized_episodes equals N;
3. development_nodes equals prestates;
4. episode IDs are unique;
5. the N episode set is nested within the 2N episode set;
6. stored rank order agrees with the fixed seed contract;
7. train size equals N;
8. calibration size equals N/2;
9. development size equals N;
10. `weather_audit.final_test_access_count` equals 0 (the field is nested in the current MATERIALIZE_SUMMARY schema; do not assume a top-level field);
11. the source summary and the materialized summary agree on year and N;
12. all years use the same seed contract;
13. no output is missing.

Write only:

~~~text
data2/reports/cohort_size_stability/PRE_STATE_MATERIALIZATION_AUDIT_V2.json
data2/reports/cohort_size_stability/PRE_STATE_MATERIALIZATION_AUDIT_V2.md
~~~

The audit must contain repository HEAD, branch, source-script hashes, log hash, per-year pool counts, per-year and per-N counts, nested-cohort checks, Final-Test access checks, missing-file checks, and overall status.

Allowed statuses:

~~~text
PASS_PRE_STATE_AUDIT
FAIL_PRE_STATE_AUDIT
BLOCKED_MISSING_PRECOMPUTED_ARTIFACT
BLOCKED_PRECHECK
~~~

Do not create a scientific N-star field in this audit.

## 8. Phase 2 — optional PRE-observable diagnostics

Run this phase only after Phase 1 passes.

First read:

~~~text
data2/scripts/cohort_size_metrics.py
~~~

Confirm that its contract says PRE-observable layer only, no M1/M2 consequence side, and development window only.

Then the allowed command is:

~~~powershell
python data2/scripts/cohort_size_metrics.py --years 2017 2018 2019 2020 2021 2022
~~~

This command is diagnostic-only. It is not the M5-b consequence battery.

The generated reports may describe structural convergence, stage-share changes, admissibility changes, reference support, target support, descriptive ranking changes, and bootstrap precision.

They may not establish M1 stability, consequence stability, screening stability, local-recovery stability, or N-star.

Every interpretation report must contain:

~~~text
analysis_layer = PRE_OBSERVABLE_ONLY
decision_authority = NONE
consequence_side_executed = false
final_test_access_count = 0
N_star_status = NOT_IDENTIFIED
~~~

If COHORT_SIZE_FREEZE_RECOMMENDATION.json is generated, describe it as a PRE-observable lower-bound diagnostic only. Do not freeze it as a scientific cohort-size decision.

If a denominator is insufficient, use:

~~~text
NOT_IDENTIFIABLE_AT_THIS_N
~~~

Do not replace missing, unsupported, or non-identifiable values with zero.

## 9. Phase 3 — consequence-side interface audit only

In `--mode audit`, this is an interface audit only. In `--mode pilot`, the same audit is a gate: the existing M5-b battery must be executable for the authorized 2019/2020 development-only scope before FIT/EVAL is started.

Read only:

~~~text
model/M1/
model/M2/
model/M3/
exp/jatm_section4/
exp/jatm_section5/
formal/v2_phase7/
artifacts/paper_results_v2_final_test_rmb/
~~~

Record the exact existing entry points for M1 training, M1 calibration, yearly M2 reference loading, canonical Stage-I screening, canonical Stage-II exact enumeration, development-only evaluation, manifest generation, and provenance/hash recording.

Do not run Final-Test, Section-4, or JATM Section-5 entry points. In pilot mode, run only the existing M5-b battery entry points explicitly listed in Section 6.0, after the interface gate passes.

Create a planning table with:

| object | exact interface | input artifact | Final-Test access | frozen-artifact write | status |
|---|---|---|---|---|---|
| M1 train | path or MISSING | train cohort | yes/no | yes/no | NOT_AUTHORIZED |
| M1 calibration | path or MISSING | calibration cohort | yes/no | yes/no | NOT_AUTHORIZED |
| M2 reference | path or MISSING | yearly H1 bundle | yes/no | yes/no | NOT_AUTHORIZED |
| Stage I | path or MISSING | development states | yes/no | yes/no | NOT_AUTHORIZED |
| Stage II | path or MISSING | development states | yes/no | yes/no | NOT_AUTHORIZED |

If an interface is missing, return:

~~~text
BLOCKED_CONSEQUENCE_INTERFACE
~~~

Do not write a replacement scientific implementation.

### 9.1 Existing Section-5 development path

The repository already contains a development-only consequence-side driver:

~~~text
exp/jatm_section5/run_development.py
~~~

It is the existing integration point for JATM Section-5 development outputs and writes only to:

~~~text
artifacts/experiment/jatm_section5/development/
~~~

If a later human authorization opens the consequence-side battery, reuse this driver rather than creating a parallel M5-b implementation. Its guards are part of the execution contract:

1. `run_section4=True` is forbidden; Section 4 must be reused.
2. The output root must remain the development namespace above.
3. Section-4 reuse must pass `H_CAPACITY_SELECTION.json` and `H_CAPACITY_MODEL_PERFORMANCE.csv` under:

~~~text
artifacts/diagnostics/jatm_section4/h_capacity/
~~~

4. The reused Section-4 selection must have status `COMPLETE`, history-capacity grid `[8, 16, 32]`, and `final_test_access_count = 0`.
5. The driver loads the existing `H16_CHECKPOINT` and `CURRENT_CHECKPOINT`; it is not a license to retrain or recalibrate M1.
6. The resulting manifest must retain `final_test_access_count = 0`, `M1_DEFINITION_CHANGED = NO`, and `M2_DEFINITION_CHANGED = NO`.
7. The current driver declares `scientific_patch = STAGE_MATCHED_PRE_TURN_SCREENING` and `SCIENTIFIC_ORCHESTRATION_CHANGED = YES`. Treat this as a scientific orchestration change that requires a separate human decision and manuscript alignment; do not describe it as a neutral rerun.

Under the current plan this driver is audit-only. Do not call `run_development()` and do not infer consequence-side completion from the presence of the driver. If any guard or required artifact is missing, return `BLOCKED_CONSEQUENCE_INTERFACE` rather than repairing the driver or rerunning Section 4.

## 10. Phase 4 — future consequence-side design

This section is a design contract only. It must not be executed under the current plan.

The existing `cohort_size_metrics.py` output cannot substitute for this phase. Its `stable_N_y` is explicitly a PRE-observable lower bound based on headline-share convergence, and its `N_star_max` is emitted with status `AWAITING_HUMAN_CONFIRMATION`. The thresholds in that script are diagnostic parameters whose confirmation is still pending; they are not a frozen scientific cohort-size rule. Do not rename either field into a final N-star or cite it as decision stability.

### 10.1 Pilot execution contract from the frozen M5-b protocol

Pilot mode must follow the existing `CONSEQUENCE_STABILITY_PROTOCOL_V1.json` exactly. Before any consequence metric is computed, load the protocol and verify its hash. Do not recreate the protocol from prose and do not edit its bands, seed, N grid, or fallback ladder after outcomes are available.

The automatic pilot sequence is:

1. **Determinism sentinel.** Run only 2019 at N=128 and N=4096, with two identical repetitions per setting. Compare training-example, normalization, calibration, checkpoint, and development-output digests. If the sentinel fails or its nondeterminism floor is of the same order as a frozen equivalence band, return `BLOCK_M5B_NONDETERMINISM` and stop.
2. **Year-specific M2 references.** Reuse the existing Y-H1 taxi and turnaround references. Build or reuse the 2019 and 2020 M2 reference bundles with `data2/scripts/build_year_references.py`; the bundle must fit once per year and be shared by every N. Never overwrite the frozen taxi/turnaround reference files. Record bundle hashes and the exact H1/Q1-Q2/June filters.
3. **FIT_SIZE_STABILITY.** For 2019 and 2020, train and calibrate M1 for N in 128, 256, 512, 1024, 2048, and 4096 using the fixed hash-ranked prefixes already written by the completed PRE run. The code may materialize the selected Train/Calibration records in memory for M1 input construction, but it must not re-enumerate raw months, rerun hash collection, or rewrite the existing PRE JSONL. Evaluate every M1_N on the same top-4096 development cases. Use episode-level paired bootstrap with B=2000 and seed 20260906.
4. **EVAL_SIZE_STABILITY.** Fix M1_4096 and the year-specific M2 bundle. Evaluate nested development prefixes at the same N grid. Use nested-cohort bootstrap; each replicate must preserve the prefix relationship between D_N and D_4096. Plain independent or ordinary paired bootstrap over different cohort sizes is invalid.
5. **Decision.** Treat N=4096 as the reference only. It cannot certify itself. A candidate N is stable only when every binding metric's 95% confidence interval for the difference from N=4096 lies inside the frozen equivalence band and all identifiability gates pass. If 2048 versus 4096 fails any binding metric, return `N_GRID_UPPER_BOUND_REACHED`; do not choose 4096 automatically and do not expand to 8192.

The current `consequence_stability_battery.py` already contains the sentinel and FIT training path, but its EVAL phase raises `NotImplementedError`. ZCodex must implement the missing EVAL metric layer in that existing file (or a directly imported module) before launching the pilot. The implementation must preserve the existing protocol and reuse `evaluate_dev_cases`; it must not report FIT completion as overall stability completion.

The pilot must emit, per year and per N, at least:

~~~text
training cohort hash
calibration cohort hash
development cohort hash
M1 checkpoint hash
M2 bundle hash
development node count
seven consequence-component summaries
Kendall tau-b
Ranking@k
top-k overlap
large-decile displacement
activation rate
missed activation rate
false activation rate
L_att
L_rec
bootstrap confidence interval
identifiability status
equivalence status
~~~

The battery must preserve `NOT_IDENTIFIABLE_AT_THIS_N` for insufficient denominators. It must not replace an unidentifiable rate with zero or count it as an equivalence pass.

### 10.2 Required EVAL implementation behavior

The missing EVAL implementation must be deterministic and must not call raw-data enumeration. For each year:

1. Load the already hash-ranked development records from `HASH_SELECTED_COHORT_RECORDS_N4096.jsonl`.
2. Define D_N as the first N ranked development episodes and verify D_N is a prefix of D_4096.
3. Load the cached M1_4096 checkpoint and the fixed year-specific M2 bundle.
4. Evaluate each D_N using the same consequence mapping, common-support rule, scenario count, action grid, tie-breaking, and policy parameters as the protocol.
5. Aggregate node-level outputs to episode-level decision metrics before bootstrap resampling. Never treat rolling nodes as independent episodes.
6. For each bootstrap replicate, draw episode IDs once and evaluate the paired metrics on D_N intersecting the draw and D_4096 intersecting the same draw. Record the difference and its 2.5th/97.5th percentiles.
7. Write per-N rows only after all denominators, support counts, and hashes are recorded.

The EVAL implementation must fail closed if the fixed checkpoint, M2 bundle, protocol hash, or development cohort hash does not match the manifest. It must not silently load the nearest available checkpoint or substitute a PRE-only ranking metric for a consequence metric.

For candidate N:

~~~text
TRAIN = N
CALIBRATION = N/2
DEVELOPMENT = N
FINAL_TEST = forbidden
~~~

Candidate grid:

~~~text
128, 256, 512, 1024, 2048, 4096
~~~

The same nested hash contract must be used:

~~~text
SHA256("M5-COHORT-SEED-20260928" || episode_id)
~~~

Hold fixed year, M2 reference bundle, development decision cases, scenario count, consequence components, CU normalization, action grid, tie-breaking, common-support rule, policy parameters, and bootstrap contract.

Potential decision metrics are:

- Stage-I shortlist membership, top-K overlap, retained consequence value, L_att, and active-boundary displacement;
- Stage-II activation, zero-target decisions, exact agreement, missed activation, false activation, over-recovery, under-recovery, L_rec, and V;
- Delay versus Consequence, Current versus History, Point versus Marginal, Marginal versus Joint, and Point versus Joint contrasts.

Use episode-level paired bootstrap for matched cases. Use nested-cohort bootstrap for nested cohorts and preserve D_N subset D_4096 within each replicate.

The largest N cannot certify itself. If N=2048 versus N=4096 fails a binding metric, return:

~~~text
N_GRID_UPPER_BOUND_REACHED
~~~

Do not automatically select 4096 and do not automatically expand to 8192.

## 11. Phase 5 — determinism sentinel

In `--mode pilot`, this phase runs automatically before FIT_SIZE_STABILITY. In `--mode audit`, it is recorded as `NOT_EXECUTED_BY_CONTRACT`.

Compare two repetitions for 2019 N=128 and 2019 N=4096. Compare training episode hash, normalization hash, calibration payload hash, checkpoint hash, development scores, and development decision metrics.

If repeated runs differ materially, return:

~~~text
BLOCK_M5B_NONDETERMINISM
~~~

Stop before the full battery. Do not silently fix nondeterminism by changing seeds.

## 12. Provenance contract

Every new audit or diagnostic report must include:

~~~text
git_head
git_branch
source_script_paths
source_script_hashes
config_hash
registry_hash
dataset_instance_id
experiment_year
fit_start
fit_end
protocol_id
protocol_hash
seed_contract
final_test_access_count
model_retrained
model_recalibrated
final_test_materialized
analysis_layer
status
~~~

For the current PRE-state scope:

~~~text
model_retrained = false
model_recalibrated = false
final_test_materialized = false
final_test_access_count = 0
analysis_layer = PRE_OBSERVABLE_ONLY
~~~

When auditing an existing yearly reference bundle loaded by the cohort scripts, record that the bundle was reused and metadata-bound for the requested year. Do not describe this load as a new fit. Retain the reference-file hash and the binding fields (`dataset_instance_id`, `experiment_year`, fit dates, and contract identifier) so that reuse is distinguishable from retraining.

Use the repository canonical text hashing utilities where applicable:

~~~text
validation/v2_phase6/common.py
validation/v2_phase6_r2/common.py
~~~

Do not normalize line endings merely to make hashes match.

## 13. Manuscript-use rules

If only PRE-state diagnostics exist, they may support an Appendix subsection titled:

~~~latex
\subsection{Cross-Year PRE-State Materialization Diagnostics}
~~~

The text must say that these are state-construction, support, and cohort-structure diagnostics. They must not be presented as evidence that decision losses or information value are stable.

If a consequence-side battery is later completed, only then consider:

~~~latex
\subsection{Cross-Year Robustness of Decision-Support Comparisons}
~~~

Possible tables include year by N decision metrics, nested-cohort comparisons, support rates, PRE/TURN composition, activation, missed activation, L_att, L_rec, equivalence bands, and non-identifiable statuses.

Do not call this universal generalization. Call it cross-year validation within the replicated design.

## 14. Completion criteria

### 14.1 Audit mode

Audit mode is complete only when:

1. existing preprocessing and materialization are reused without regeneration;
2. all six years and all six N values are audited;
3. nested containment is checked;
4. Final-Test access is verified as zero;
5. PRE diagnostics, if run, are marked PRE_OBSERVABLE_ONLY;
6. no M1 retraining or recalibration occurs;
7. no Final-Test artifact changes;
8. no new N-star is frozen;
9. completed facts and pending consequence-side design are separated;
10. the report includes hashes, HEAD, commands, outputs, and statuses.

Expected current-scope status:

~~~text
PRE_STATE_MATERIALIZATION_COMPLETE_CONSEQUENCE_SIDE_PENDING
~~~

The presence of `exp/jatm_section5/run_development.py`, frozen M1 checkpoints, or Section-4 diagnostics does not change this status. They establish that an integration path exists; they do not show that the consequence-side battery has been run for the six cohort sizes.

If an audit fails:

~~~text
FAIL_PRE_STATE_AUDIT
~~~

### 14.2 Pilot mode

Pilot mode is complete only when:

1. the 2019/2020 protocol hash is recorded before metrics;
2. the 2019 N=128/N=4096 determinism sentinel passes;
3. the 2019 and 2020 M2 bundle hashes are fixed and shared across all N;
4. FIT_SIZE_STABILITY completes for every requested year and N, or returns a typed failure;
5. EVAL_SIZE_STABILITY is implemented and completes with nested-cohort bootstrap, or returns `BLOCKED_CONSEQUENCE_INTERFACE`;
6. every metric has an equivalence or `NOT_IDENTIFIABLE_AT_THIS_N` status;
7. no Final-Test path is read or materialized;
8. no COMMON_N_STAR is frozen;
9. the runner stops after the pilot report and records the next human decision.

Expected successful pilot status:

~~~text
M5B_PILOT_COMPLETE_HARD_STOP
~~~

## 15. Final instruction to ZCodex

### 15.1 Autonomous decision tree

Implement the following exact branching logic. Select the branch from the explicit `--mode` argument; never infer pilot mode from the presence of files.

~~~text
IF repository root is not the canonical root:
    status = BLOCKED_PRECHECK; stop
IF a Final-Test process or forbidden writer is active:
    status = BLOCKED_PRECHECK; stop
IF any required 2017--2022 PRE artifact is missing:
    status = BLOCKED_MISSING_PRECOMPUTED_ARTIFACT; stop
IF any existing materialization invariant fails:
    status = FAIL_PRE_STATE_AUDIT; stop
IF mode == audit:
    IF PRE metrics are absent or their input hash is stale:
        run only cohort_size_metrics.py; if it fails, status = FAIL_PRE_METRICS; stop
    inspect consequence-side interfaces without executing them
    status = PRE_STATE_MATERIALIZATION_COMPLETE_CONSEQUENCE_SIDE_PENDING; stop
IF mode == pilot:
    verify protocol hash and pilot years == {2019, 2020}; otherwise BLOCKED_PROTOCOL_SCOPE
    verify M5-b eval phase is implemented; if stub, BLOCKED_CONSEQUENCE_INTERFACE
    run 2019 N=128/4096 determinism sentinel; if it fails, BLOCK_M5B_NONDETERMINISM
    reuse/build 2019/2020 year-specific M2 bundles; if a bundle is missing or mutable, BLOCKED_M2_REFERENCE
    run FIT_SIZE_STABILITY; if it fails, FAIL_FIT_SIZE_STABILITY
    run EVAL_SIZE_STABILITY with nested bootstrap; if it fails, FAIL_EVAL_SIZE_STABILITY
    apply the frozen equivalence and identifiability rules
    if 2048 vs 4096 fails any binding metric, status = N_GRID_UPPER_BOUND_REACHED
    otherwise status = M5B_PILOT_COMPLETE_HARD_STOP
~~~

The runner must return a nonzero process exit code for statuses beginning with `BLOCKED_`, `FAIL_`, or `N_GRID_`. It may return zero for `PRE_STATE_MATERIALIZATION_COMPLETE_CONSEQUENCE_SIDE_PENDING` because the authorized autonomous scope completed successfully while the unauthorized scientific phase remains pending.

The runner must never convert a missing artifact, unsupported denominator, failed interface, or unexecuted consequence-side phase into a numeric zero. Preserve the typed status in both JSON and Markdown reports.

The final report must contain a `COMMANDS_EXECUTED` table and a `COMMANDS_NOT_EXECUTED_BY_CONTRACT` table. In audit mode, the second table must list collection, materialization, M1 training, M1 calibration, Section-4 rerun, M5-b FIT/EVAL, Section-5 consequence-side run, and Final-Test evaluation. In pilot mode, it must list collection, materialization, Section-4 rerun, Section-5 consequence-side run, and Final-Test evaluation as not executed, while listing the authorized M5-b sentinel/FIT/EVAL commands in the executed table.

Do not optimize for a positive result.

Do not turn missing consequence-side computation into zero.

Do not turn a PRE-observable lower bound into a scientific N-star.

Do not rerun existing preprocessing because a downstream file is missing.

In audit mode, do not retrain or recalibrate. In pilot mode, retrain and recalibrate only the authorized 2019/2020 development-only M1_N settings through the existing M5-b battery, and record every checkpoint and calibration hash.

Do not read Final Test.

When the authorized scope is complete, stop and return:

1. exact commands run;
2. exact files read and written;
3. repository HEAD and hashes;
4. per-year and per-N counts;
5. nested-cohort audit;
6. Final-Test access audit;
7. explicit non-executed items;
8. status from the decision tree;
9. the smallest next action requiring human authorization.
