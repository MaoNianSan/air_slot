# AIR SLOT Development deployment candidate

**INDEPENDENT_REVIEW_PENDING / SIX_YEAR_EXECUTION_BLOCKED**

Human independent review is required before uploading, connecting to a server,
benchmarking or launching an annual experiment. The commands below are future
execution drafts. No LLM is required. See artifacts/experiment/jatm_s34/cloud_handoff_review/.
Linux, Docker, systemd and CUDA execution are NOT YET VERIFIED.
Direct dependencies are pinned; requirements.runtime.txt is not a resolved,
hash-locked Linux wheel set. Save pip freeze and wheel/platform details on Linux.

Python 3.11.6; deploy/jatm_cloud/requirements.runtime.txt records the packages actually
used for the local golden comparison (including torch 2.11.0). The older repository
requirements.txt differs and is not this run's environment authority.
Create a dedicated environment, install the runtime requirements, and save `python -m pip freeze`
as ENVIRONMENT_LOCK.txt in each deployment. Preserve the Git commit and source hashes.

The production entry is `python -m exp.jatm_s34.shared_run`. The old annual_development
entry remains a legacy interface and must not be used for cloud production.

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

Read P0_REVIEW_NOTES.md and the second-review package before use. C1/C2,
ratio-of-sums and completion gates were corrected for resubmission;
exposure-specific Coverage@K, sensitivity grids and complete rolling uncertainty
outputs remain unresolved or incomplete. Successful process execution is not full
scientific acceptance. No cloud benchmark has been run.
