# AIR SLOT Development deployment candidate

**P0_INDEPENDENT_REVIEW_PASSED / SIX_YEAR_EXECUTION_BLOCKED**

P0 was independently accepted at scientific code baseline
`e278ac55871dd3208bbd9a55e24b0d7a94314c96`. The 2026-10-12 cleanup approval
authorizes documentation and design only. It does not authorize uploading,
connecting to a server, benchmarking, training or launching an annual experiment.
The commands below remain future execution drafts. No LLM is required.
See [current status and retained limitations](CLEANUP_DOC_ONLY_STATUS.md).
The original handoff/review packages remain historical evidence, including their
then-current pending statuses. Linux, Docker, systemd, CUDA and container
throughput benchmarks remain **NOT_RUN**.
Direct dependencies are pinned; requirements.runtime.txt is not a resolved,
hash-locked Linux wheel set. Save pip freeze and wheel/platform details on Linux.

The existing candidate targets Python 3.11.6. requirements.runtime.txt records
the directly pinned non-torch packages; bootstrap_cpu.sh and Dockerfile.cpu
separately request torch==2.11.0+cpu. These files are not a verified Linux lock.
The older repository requirements.txt is not this candidate's environment authority.
Create a dedicated environment, install the runtime requirements, and save `python -m pip freeze`
as ENVIRONMENT_LOCK.txt in each deployment. Preserve the Git commit and source hashes.

## Current and historical entry points

The prepared multi-year orchestration entry is
`python -m exp.jatm_s34.cloud_schedule --config deploy/jatm_cloud/run.yml`.
Its source call chain is:

```text
cloud_schedule -> cloud_worker -> cloud_inputs.check_year -> shared_run
    -> shared_science (annual PRE/M1/M2, compact scores and restorable states)
    -> E1 + E1_FIXED_COMMON + shared E2/E3 evaluation
    -> validated annual receipts/results
cloud_schedule -> e4_shared_aggregate (only after all six annual checks pass)
```

`shared_run` is the per-year computational entry invoked by the worker; calling
it directly is not a substitute for the worker's complete annual input gate.
E4 consumes annual results and does not rerun PRE/M1/M2/M3. A zero worker exit
code or an exhausted queue alone does not establish six-year completion.

| Entry | Current role |
| --- | --- |
| cloud_schedule / cloud_worker / shared_run | Prepared shared Development chain; execution remains blocked and unauthorized |
| annual_development | Historical separate E1 and E2/E3 orchestration, not the cloud production route |
| e4_scheduler -> e4_run -> consequence_stability_battery | Historical M5-b cohort-size execution, not current JATM E4 decision-value replication |
| e4_development / readiness | Historical input/preflight reporting, not full-chain scientific acceptance |
| e1_information_gain / e2_e3_exact / annual_shared | Mixed legacy drivers and actively reused helpers/readers; do not delete these modules |

Historical Python entry points remain unchanged; no CLI is redirected or removed.
The N=128 M5-b engineering evidence does not establish E4 scientific completion.

## Inputs

Mount the repository and only the verified Development dependency closure on private
cloud storage. Preserve repository-relative paths. Required annual roots are:

- artifacts/models/m1/YEAR_Y: both N=4096 checkpoints, manifests and annual TAIL_REFERENCE_V1/MANIFEST.json;
- artifacts/models/pre/PRE_MULTIYEAR_V1/Y: PRE manifests, H1 taxi/turnaround references;
- artifacts/models/pre/PRE_MULTIYEAR_V1_E4_YEARLOCAL_R1/Y/M2_REFERENCES;
- artifacts/models/pre/PRE_MULTIYEAR_V1_D4_2017H1_R2/2017/M2_REFERENCES;
- data2/reports/cohort_size_stability/Y/HASH_SELECTED_COHORT_RECORDS_N4096.jsonl;
- data2/reports/paper_formal/Y/Y/M2_TRAIN_HEADROOM_SUMMARY.json;
- existing configuration; annual authorities do not load the legacy Phase-5 base cache;
- PRE raw-input dependencies restricted to legal Train/Calibration/Development data.

Do not copy a whole raw-data directory without a reviewed file allowlist. Protected Test
and Final-Test inputs are excluded. Do not upload credentials. No cloud machine or storage
has been provisioned by these scripts. Before migration, generate and verify a SHA-256
file allowlist for the actual closure; unresolved raw dependencies remain a deployment gate.

## Benchmark ladder (separate outputs; explicitly PILOT)

```bash
python -m exp.jatm_s34.cloud_schedule --years 2017 --workers 1 --threads 8 --phase stage1 --episode-limit 32 --output-root runs/bench_cpu_1
python -m exp.jatm_s34.cloud_schedule --years 2017 2018 --workers 2 --threads 8 --phase stage1 --episode-limit 32 --output-root runs/bench_cpu_2
# Only after another legal annual checkpoint exists:
python -m exp.jatm_s34.cloud_schedule --years 2017 2018 2019 --workers 3 --threads 8 --phase stage1 --episode-limit 32 --output-root runs/bench_cpu_3
```

Choose the highest measured aggregate canonical-node throughput that retains memory
headroom. 128 GiB and 32 logical vCPUs are a proposed benchmark environment, not measured
performance. Admission budgets (not OS hard memory limits) reserve 24 GiB per job plus 12 GiB for the host; tune only
from measured peak RSS. Thread budget is checked before launch.

CUDA is optional: install the pinned torch version with the wheel matching the selected
CUDA runtime/driver, record wheel and driver versions, and run `--device cuda` only with
an explicit episode-limited benchmark. CPU is the default and the `auto` fallback. Full
CUDA production is gated until identity, probability, consequence, ranking and action
parity have been measured. FP16/autocast/TF32 are not enabled.

## Production draft (after targeted and cloud acceptance)

```bash
python -m exp.jatm_s34.cloud_schedule --years 2017 2018 2019 2020 2021 2022 --workers 1 --threads 8 --output-root runs/development_v5_shared_v1
python -m exp.jatm_s34.e4_shared_aggregate --annual-root runs/development_v5_shared_v1 --output-root runs/e4_v1
```

Every year has separate outputs and logs. Reissue the identical command to validate and
resume atomic chunk/action commits. Cache identity mismatches fail; use a new versioned
output directory after a scientific code/input change. A root STOP_REQUESTED file asks
the scheduler to pause workers at a committed chunk/node. Remove the marker only when
resuming deliberately. Never infer cached data from completed_chunks alone.

Final statuses remain COMPUTED_PENDING_SCIENTIFIC_ACCEPTANCE until all required inference,
CI, mechanism, fixed-common and provenance outputs are checked. No Test command is supplied.

## Current inputs and no-LLM configuration

The local transfer manifest records 439 files, 14.73 GiB and 21 missing required
paths. 2018 lacks its annual tail. 2019--2022 lack both annual models, manifests
and tails. The worker cannot train missing models. Six-year execution is blocked.
Use repository.files.txt plus overlay.files.txt, placing legal-date weather overlay
files at their manifest destination paths. Do not replace them with full-year files.

After human review and a separate migration authorization, the prepared commands are:

```bash
bash deploy/jatm_cloud/bootstrap_cpu.sh
bash deploy/jatm_cloud/verify_inputs.sh /path/to/DATA_TRANSFER_MANIFEST.json
# Inspect every annual gate status; the report-writing CLI is not a PASS exit gate.
.venv/bin/python -m exp.jatm_s34.cloud_schedule --config deploy/jatm_cloud/run.yml
.venv/bin/python -m exp.jatm_s34.cloud_status --output-root /runs/development_v5_annual_tail_v1
```

bootstrap_cpu.sh only installs and records an environment. run.yml defaults to
one CPU worker. The optional systemd service must not be installed or enabled
before human approval. No LLM, API key or agent is part of runtime scheduling.
On safe stop, preserve source snapshot, manifests, commits, response ledgers and
logs. Before an authorized resume remove the root and per-year shared/STOP_REQUESTED
markers after the processes have exited. Check lock PID/host ownership before any
stale-lock intervention. Never reset a live writer's lock. Scientific identity
changes require new versioned output roots.

Read P0_REVIEW_NOTES.md and the second-review package as historical contract
and reproduction records. Their pending-review text predates the user's P0
acceptance at e278ac5. C1/C2, ratio-of-sums and completion gates passed that review;
exposure-specific Coverage@K, sensitivity grids and complete rolling uncertainty
outputs remain unresolved or incomplete. Successful process execution is not full
scientific acceptance. No cloud benchmark has been run.
