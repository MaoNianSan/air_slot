# Cloud multi-year execution readiness

**Status date:** 2026-10-13 (Asia/Hong_Kong)  
**Branch:** `v2/paper-primary`  
**P0 scientific baseline:** `e278ac55871dd3208bbd9a55e24b0d7a94314c96`  
**Implementation commit:** `18110df735fd9785492114e3850f14c6d7046212`  
**Scientific contracts:** `JATM_F_CONTINUITY_B_V1`; `JATM_STAGE2_SIGNED_T_IB_V1`  
**Final-Test access count:** `0`

## Readiness gates

| Gate | Status | Evidence and boundary |
|---|---|---|
| Source package upload | **BUILT / CHECKSUM-VERIFIED** | A source-only archive and checksum manifest exist. The archive contains code and deployment files, not the 14.73 GiB annual input closure. It may be uploaded independently of missing scientific inputs. |
| `CLOUD_DEPLOYMENT_READY` | **NOT YET VALIDATED** | Linux dependency installation, source snapshot startup, file transfer, filesystem permissions, systemd/container behavior and target runtime remain untested. This status does not prevent uploading the already checked source package. |
| `ANNUAL_INPUT_PREPARATION_READY` | **PARTIAL** | Parameterized builders exist for B references and tails; a new explicit-approval M1 training entry is available. Inputs have not been built for all years, B outputs are absent, and no combined cloud preparation run has been exercised. See the annual matrix and commands below. |
| `SIX_YEAR_DEVELOPMENT_READY` | **BLOCKED** | Required B CU bundles are missing for all years; 2018 tail is missing; 2019–2022 annual M1 checkpoints/manifests and tails are missing. The six-year gate currently fails closed. |
| Formal Development / Test | **NOT STARTED / PROHIBITED** | No full-year execution, cloud connection, upload or Test/Final-Test read occurred in this task. |

The 93 MB-class source archive means only `CLOUD_UPLOAD_PACKAGE_BUILT`; it is not evidence for `CLOUD_MULTIYEAR_EXECUTION_READY`.

## 1. Six-year scientific run target and entry path

Each year 2017–2022 is a separate Train / Calibration / Development unit. Each uses that year’s legal PRE inputs, N=4096 annual M1 models, annual Train tail, B-version consequence references and Year-local CU. The 2017-H1 `FIXED_COMMON` CU is an auxiliary track with its own identity. E1/E2/E3 are evaluated per year from shared PRE/M1/M2 outputs. E4 runs only after six validated annual full-Development records exist.

```text
cloud_schedule (one config lists all six years; no LLM)
  -> one cloud_worker per admitted year, each with its own output root/log
     -> cloud_inputs.check_year (fail closed; no M1 training)
     -> shared_run
        -> shared_science (PRE/M1/M2 shared annual cache)
        -> E1 Year-local + E1 Fixed Common + E2/E3
     -> content-validated annual result
  -> e4_shared_aggregate (only after all six year records pass)
  -> WAITING_HUMAN_CONFIRMATION
```

Year selection already uses the parameterized `--years` / `run.yml` mechanism. `cloud_schedule` accepts one to three workers, enforces the CPU thread budget and admits a worker only if available memory covers its configured per-worker reserve plus the host reserve. `run.yml` conservatively defaults to one worker; a two-year run can be selected without source edits, but should only be enabled after a measured two-worker benchmark. At 32 vCPU and the current 8-thread/worker budget, two workers fit the CPU budget. The current 24 GiB per-worker and 12 GiB host-reserve figures are admission estimates, not hard memory limits or measured peaks.

The scheduler keeps separate year directories, logs, attempt status and failure records. A failed year does not overwrite a sibling year; transient I/O failures get the configured bounded retry, while scientific/input failures remain visible and the queue can continue. E4 is not called unless the requested set is exactly 2017–2022 and each worker has a zero exit, `FULL_DEVELOPMENT` scope, the expected year, and a valid computed manifest; E4 independently validates annual result files. The terminal status is `WAITING_HUMAN_CONFIRMATION`, never Test access.

Per-year CPU time, wall time, peak RSS and peak private memory are now sampled and recorded. On Linux, private memory uses USS. Sampling occurs on the scheduler polling interval, so peak values are sampled maxima rather than kernel-level exact peaks. GPU execution is not ready for full runs: CUDA is restricted to explicit episode-limited pilots until numeric equivalence is accepted. CPU is the production candidate.

## 2. Annual input preparation: current local evidence

The local disk check and transfer allowlist were inspected separately. Existing legacy A references are not substituted for the approved B contract.

| Year | Train / Calibration / Development cohort and base PRE references | N=4096 M1 history + current models | Train tail | B Year-local CU/reference bundle | B 2017-H1 Fixed Common bundle | Required preparation |
|---:|---|---|---|---|---|---|
| 2017 | Present in local closure | Both checkpoints and manifests present | Present; hash-bound to 2017 H1 Train | Missing | Missing | Build B Year-local and B Fixed Common references; retain M1 and tail |
| 2018 | Present in local closure | Both checkpoints and manifests present | Missing | Missing | Shared 2017 B bundle missing | Build B Year-local; build 2018 tail; no M1 training |
| 2019 | Present in transfer closure | No annual checkpoints/manifests found | Missing | Missing | Shared 2017 B bundle missing | Build B Year-local and tail; train both annual M1 roles only in separately approved stage |
| 2020 | Present in transfer closure | No annual checkpoints/manifests found | Missing | Missing | Shared 2017 B bundle missing | Same as 2019 |
| 2021 | Present in transfer closure | No annual checkpoints/manifests found | Missing | Missing | Shared 2017 B bundle missing | Same as 2019 |
| 2022 | Present in transfer closure | No annual checkpoints/manifests found | Missing | Missing | Shared 2017 B bundle missing | Same as 2019 |

The local check found the existing legacy A Year-local bundle manifests for all six years and the legacy 2017 Fixed Common bundle. Those artifacts may supply unchanged underlying reference payloads only after the B builder validates their provenance; they do not supply the B `F_continuity` scale or establish a B CU. The required versioned B roots are:

- Year-local: `artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1/<year>/M2_REFERENCES/`
- Fixed Common: `artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_B_V1/2017/M2_REFERENCES/`

Relevant executable preparation components exist:

1. `python -m data2.scripts.build_year_references --years 2017 2018 2019 2020 2021 2022 --output-root artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_B_V1 --continuity-contract JATM_F_CONTINUITY_B_V1` builds the B Year-local Train reference bundles. Run the corresponding `--years 2017 --output-root artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_B_V1` command for the separately named Fixed Common bundle. The builder fits the legal H1 references (including T100 through June and DB1B Q1+Q2) and the seven scales. It currently recomputes the full M2 reference bundle rather than only the changed continuity scale; this is more work but preserves the builder’s provenance contract. These commands have not been run in this task.
2. `python -m exp.jatm_s34.build_annual_tail --year YEAR --decision deploy/jatm_cloud/scientific_decisions/ANNUAL_TAIL_USER_DECISION.json` builds the approved Train-empirical tails from that year’s N=4096 active-positive labels. The decision file explicitly covers 2017–2022. Tail support still must pass each target’s minimum support rule; no cross-year tail borrowing is allowed. Current needs are 2018–2022; 2017 is already present and can be verified with `exp.jatm_s34.tail_receipt`.
3. For each missing M1 year only, `python -m exp.jatm_s34.cloud_train_models --year YEAR --approval PATH` is now a separate stage. It requires a `USER_APPROVED` year-specific authorization record, exact N=4096 roles/split settings, zero Test access, and refuses to overwrite any existing year directory. The shipped template is `deploy/jatm_cloud/scientific_decisions/M1_TRAINING_AUTHORIZATION_TEMPLATE.json` and is deliberately `NOT_APPROVED`. `cloud_schedule` and `cloud_worker` never invoke this stage. 2019–2022 each require two annual role models; 2017–2018 must not be retrained.

Input preparation can therefore be run as explicit per-stage commands without editing code or involving an LLM, but it is **not yet an end-to-end validated preparation workflow**. After the B bundles, missing tails and explicitly approved models exist, run the six-year `cloud_inputs` gate and inspect every year before scheduling a Development run.

## 3. Code archive versus data package

These are separate delivery objects:

- **Code/deployment archive:** the source-only archive produced from Git, plus deployment files, input manifests, checks and package hashes. It contains no raw data, annual model checkpoints, tails or generated B reference bundles. `DATA_TRANSFER_MANIFEST.json` inside it is a list, not the data itself.
- **Annual input closure:** `artifacts/experiment/jatm_s34/cloud_preparation_v2_20261012/transfer/DATA_TRANSFER_MANIFEST.json` lists 439 files totaling 15,815,908,998 bytes (14.73 GiB), with 21 missing required paths. It covers the legal Train/Calibration/Development closure and reference assets; no network transfer has occurred. `repository.files.txt` and `overlay.files.txt` together list the 439 intended files.

The 21 missing allowlist paths are exact and classify as:

- 2018: one annual `TAIL_REFERENCE_V1/MANIFEST.json`.
- 2019–2022: each year’s two M1 checkpoints, two M1 manifests and one annual tail manifest (20 paths total).

The newer B CU bundles are not present in that older transfer manifest and must be built first, then added to a regenerated, independently hashed transfer closure. A separate `TRANSFER_PROGRESS.json` currently reports 429 files and 15,621,529,373 bytes, 10 files / 194,379,625 bytes fewer than the manifest. It is preparation metadata, not proof of network transfer; reconcile it against the actual allowlist before transferring data.

**Recommended upload order:**

1. Upload and verify the source/deployment archive independently; this does not wait on six-year inputs.
2. On the prepared source tree, run `deploy/jatm_cloud/prepare_source_snapshot.py` with the exact Git head and source archive SHA-256 from `PACKAGE_MANIFEST.json`. Source-only archives do not include `.git`; this step creates the `CODE_SNAPSHOT.json` consumed by runtime provenance without installing Git.
3. Build the authorized B Year-local and Fixed Common Train references, build missing annual tails, and conduct only separately authorized M1 training for 2019–2022. Preserve year-isolated outputs and hashes.
4. Regenerate the combined data transfer manifest for the final legal closure; resolve the 10-file progress mismatch; transfer the 14.73 GiB base closure plus generated B/model/tail additions through approved private storage. Exclude Test/Final-Test and credentials.
5. Run `cloud_verify` against the complete manifest, then `cloud_inputs` with `JATM_F_CONTINUITY_B_V1`; no formal job starts until all six are valid.

## 4. Linux / cloud operational readiness

**Implemented, but Linux-unverified:**

- CPU Docker/bootstrap templates target Python 3.11 and separate torch CPU installation.
- The no-LLM YAML scheduler and per-year worker, stop markers, atomic chunk/action stores, retry handling, annual input gate, source identity and post-six-year E4 gate are present.
- `prepare_source_snapshot.py` binds a source-only archive to a reviewed 40-hex Git commit and archive SHA-256. This addresses the no-`.git` `code_revision()` runtime gap.
- The optional systemd unit can keep the scheduler alive across SSH disconnects after it is installed and enabled. A hard power loss leaves committed chunks/receipts available; a same-host service restart can resume. A deliberate graceful stop writes persistent stop markers and requires an operator to inspect processes, then clear markers before resume. Remote-host stale writer locks fail closed and require owner verification. systemd, reboot recovery and lock behavior are not Linux-tested.
- Resuming with the identical config/output root validates annual/shared identities. Completed valid chunks and evaluation stages are reused; failed/corrupt stages are recomputed in their own stage. Changed scientific identity requires a new output root.

**Not yet ready / known limits:**

- `requirements.runtime.txt` is a direct-pin list, not a hash-locked Linux wheelhouse; CPU/CUDA wheel resolution and the Python 3.11.6 image have not been validated on Tencent Cloud.
- Docker, systemd, private mount permissions, atomic rename/fsync, memory admission, two-worker throughput and stop/restart behavior are untested on Linux.
- The scheduler command can request two annual workers, while `run.yml` defaults to one. Two-worker use must follow a 1-worker vs 2-worker measured benchmark; admission values alone do not justify concurrency.
- Full-run CUDA is explicitly blocked by `select_device`; only episode-limited GPU parity/throughput pilots are permitted. Full annual Development should use CPU until GPU parity is independently accepted.
- On SSH disconnect, a foreground terminal is not a persistence mechanism. Use an approved systemd service or an equivalent process supervisor. Do not enable the supplied service until deployment authorization and a tested config are available.

## 5. C07 staged recovery: necessary and implemented

C07 is necessary for the multi-year run because E1’s paired 2,000-replicate bootstrap, Fixed Common E1 and E2/E3 are separately expensive. Before C07, one combined receipt meant failure in E2/E3 could force already completed E1 work to run again.

The implementation in `exp/jatm_s34/shared_run.py` now writes immutable attempts plus atomic selected pointers for:

- `E1_YEAR_LOCAL`
- `E1_FIXED_COMMON`
- `E2_E3`

Each receipt binds the current shared/evaluation identity, stage identity and dependencies, every output path/size/SHA-256 under that stage directory, a valid summary JSON, validator version and `final_test_access_count == 0`. Fixed Common E1 additionally binds its cache and score manifests. The final `EVALUATION_COMPLETE.json` is written only after the three stage receipts validate. An invalid or missing stage reruns that stage only; a valid sibling stage is skipped. `shared_run.py` is included in the algorithm identity. A former combined receipt without these stage receipts is not promoted to new proof; historical outputs are retained.

**Targeted verification:** 26 tests passed across `test_jatm_stage_receipts.py`, `test_jatm_shared.py` and `test_jatm_cloud_preparation.py`; `compileall` and `git diff --check` passed. Tests cover interruption after earlier stages, per-stage skip, corrupt-output invalidation, receipt identity and summary protections, explicit M1 authorization, source snapshot identity, Linux USS/CPU metric extraction, scheduler gates and existing cloud preparation contracts. The recovery tests use deterministic temporary outputs. No full-year or real-cache E1/E2/E3 numerical replay was performed, and Linux recovery remains unverified. Thus C07 code is implemented and unit-verified, while its representative real-Development cache replay remains a pre-production acceptance item.

## 6. Recommended execution sequence, approvals and cost evidence

| Step | Work | Required authorization | Cost/evidence |
|---|---|---|---|
| 1 | Upload source archive; verify source, snapshot and package checksums | Separate upload authorization (not granted/performed here) | About 93 MB for prior archive; current versioned package hash/size is in its package checksum file. Small compared with data. |
| 2 | Transfer and hash-verify data closure; reconcile the 429/439 discrepancy | Data migration authorization and approved Tencent private storage | 14.73 GiB base manifest, plus newly generated B refs and annual M1/tail artifacts. Transfer time depends on measured bandwidth; no endpoint or network run exists to estimate it reliably. |
| 3 | Resolve Linux runtime, create immutable environment lock, test snapshot and input gate | Cloud deployment/environment authorization | One CPU host smoke and one worker-stage pilot; no annual science run. Pin image digest, wheels and platform hashes. |
| 4 | Build six Year-local B reference bundles, one Fixed Common B bundle; build tails for 2018–2022 | Existing B CU and Train-tail scientific decisions; verify outputs and support | Seven reference bundle outputs (six local plus fixed-common 2017), five missing tail builds. Runtime not measured; builder re-fits Train references and may be substantial. |
| 5 | Train missing M1 models for 2019–2022 in a separate gated stage | Per-year explicit `USER_APPROVED` M1 training record; no blanket scheduler permission | Four annual training invocations, eight role-model fits total, each N=4096 and eight epochs per current implementation. Wall time has not been measured on target hardware. |
| 6 | Run `cloud_inputs` for all six; benchmark one vs two workers and CPU; GPU only a pilot | Benchmark authorization; no Test access | Use small episode-limited pilots and measured peak RSS/USS, CPU seconds and throughput. No reliable runtime estimate exists before this. |
| 7 | Full six-year E1/E2/E3; then E4; stop at human review | Separate formal Development authorization after all input and deployment gates pass | Six full independent annual Development chains plus one E4 aggregation. Total CPU-hours are **unknown** until Step 6; do not extrapolate from N=128 M5-b or smoke runs. |

The system must finish at `WAITING_HUMAN_CONFIRMATION`. No step in this report grants permission for cloud connection, model training, full Development execution, or Test/Final-Test access.

## 7. Remaining blockers

1. The 21 listed M1/tail artifacts and seven B CU reference bundles are not prepared; four years require separate M1 training authorization.
2. The old transfer progress record conflicts with its 439-file manifest and must be reconciled; the data has not transferred.
3. Linux source snapshot, environment, service recovery, file permissions and 1-vs-2 worker benchmark remain untested.
4. C07 passed targeted unit/recovery tests; representative cached Development replay and uninterrupted-vs-resumed scientific-field equality remain unrun.
5. Exposure-specific paper output gaps already identified in deployment documentation remain scientific P1 closure work; this report does not claim their completion or Six-Year execution readiness.
6. Formal six-year status remains `SIX_YEAR_EXECUTION_BLOCKED`; no Test/Final-Test access has occurred.
