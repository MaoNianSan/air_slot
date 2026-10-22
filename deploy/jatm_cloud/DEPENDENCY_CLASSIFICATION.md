# C08 static dependency classification and Linux lock design

Design only, 2026-10-12. Scientific baseline:
`e278ac55871dd3208bbd9a55e24b0d7a94314c96`.
**P0_INDEPENDENT_REVIEW_PASSED / SIX_YEAR_EXECUTION_BLOCKED**.
No dependency, image, install script or runtime_provenance implementation is
changed. Nothing is installed, removed, resolved online or run on Linux/CUDA.
See [current authority and limits](CLEANUP_DOC_ONLY_STATUS.md).

## Classification is not a removal allowlist

Core means calculation, input/configuration, persistence, scheduling or mandatory
provenance for the prepared shared chain. Parity means the alternate solver used
for comparisons, not production decisions. Test means local contract/acceptance
tools. Report means rendering, formatting or diagnostic progress. These roles
overlap; they are not four mutually exclusive installation sets today.

`runtime_provenance.py:38-40` unconditionally calls `importlib.metadata.version`
for all 15 distributions listed below. A distribution not found raises an error;
the function does not currently treat missing report/test/parity packages as
optional. `shared_run._run` calls `record` before scientific materialization.
Thus **all 15 are current provenance requirements**, even when no calculation
imports that package. Reclassification alone cannot remove any of them.

The static evidence is the existing targeted import inventory at
`artifacts/experiment/jatm_s34/code_cleanup_plan_20261012/MODULE_DEPENDENCIES.json`,
plus direct inspection of runtime_provenance, deploy files and the named source
sites below. No new global import audit or module execution was performed.
Conditional imports, pandas engines and external historical commands limit what
absence from an AST import list can establish.

| Distribution / current candidate pin | Scientific or tooling role | Static evidence / limitation |
| --- | --- | --- |
| pydantic 2.13.3 | Core contracts and validation | model/common/config.py; model/M2/context.py |
| PyYAML 6.0.3 | Core configuration | cloud_schedule.from_config; model/common/config.py |
| numpy 2.4.4 | Core numeric/statistical operations; tests | e1_shared_evaluation; shared_statistics; M1/M4 |
| pandas 2.3.3 | Core/input adapter and report tables | jatm_section5/run_development.py imports it; validation/v2_phase5/families.py |
| pyarrow 24.0.0 | Data I/O / compatibility / table export candidate | No direct import in inspected closure; pandas read_parquet/to_parquet calls exist in families.py and run_development.py. This does not prove those legacy I/O branches run in the annual shared chain |
| scipy 1.17.1 | Core evaluation; diagnostic selection | model/M4/evaluation.py; jatm_section5/recovery_value.py |
| scikit-learn 1.8.0 | Retained environment/compatibility dependency, specific shared-chain role unproven | No sklearn import in inspected closure; mandatory version query still applies. Do not infer active training or removal eligibility |
| torch 2.11.0+cpu requested separately | Core M1 inference/load and resource/backend control | model/M1/pipeline.py; shared_run; annual_bridge. CUDA would require a separately validated wheel, not a silent backend substitution |
| psutil 7.2.2 | Core orchestration, writer lock, resource/provenance recording | cloud_schedule, shared_store, shared_run, runtime_provenance |
| pytest 8.4.2 | Test and acceptance | tests/contract; not an annual calculation requirement apart from current mandatory environment recording |
| pyomo 6.10.1 | Parity / historical solver | model/M3/solver.py imports pyomo; shared production Stage-II uses model/M3/stage2 exact enumeration |
| highspy 1.15.1 | Parity solver backend | model/M3/solver.py imports Pyomo Highs interface; backend use is conditional, not a direct shared-chain highspy import |
| matplotlib 3.10.9 | Report/figure environment candidate | No direct import in inspected closure; do not claim plot execution in shared chain |
| tqdm 4.67.3 | Progress/reporting environment candidate | No direct import in inspected closure; role outside this closure not independently established |
| rich 15.0.0 | Console/reporting environment candidate | No direct import in inspected closure; role outside this closure not independently established |

Pins above describe repository files, not verified wheel availability or platform
compatibility. requirements.runtime.txt has 14 non-torch pins; bootstrap_cpu.sh
and Dockerfile.cpu request torch==2.11.0+cpu separately. The old root
requirements.txt is not substituted for this candidate. Exact enumeration and
parity remain separate authorities regardless of installed solver packages.

## Dependency paths relevant to a future split

```text
cloud_schedule -> psutil + PyYAML + subprocess (standard library)
cloud_worker -> annual gates -> shared_run
shared_run -> runtime_provenance.record -> version(all 15 distributions)
shared science -> PRE + torch/M1 + pydantic/M2 + numeric dependencies
E1/E2/E3 statistics -> numpy + existing M4/Section5 evaluation
parity-only model/M3/solver -> pyomo -> Highs backend
contract acceptance -> pytest + scientific dependencies
report/compatibility tools -> retained environment packages
```

Standard-library argparse, pathlib, json, hashlib, gzip, signal and subprocess
are not pip extras. Local repository modules must remain importable from the
correct repository root; their scientific provenance cannot be replaced with a
different published package. Importing a training/helper module for a constant
does not authorize model training or removal of its provenance source.

A future dependency split would need separately approved runtime changes:
define truly optional distribution queries, maintain parity/testing environments,
and validate a complete resolved environment. The C08 document authorizes none
of those changes. Keep current requirements and installation scripts intact.

## Target Linux environment: unresolved items, not installation instructions

| Area | Existing candidate / required future evidence | Current status |
| --- | --- | --- |
| Python/base image | Existing Dockerfile says python:3.11.6-slim. Record immutable image digest, OS release, architecture, Python ABI and libc when a target is authorized; tag alone is not an immutable environment | NOT_RUN |
| CPU torch | Existing scripts request 2.11.0+cpu from the torch CPU wheel index. Verify availability and compatibility on the target rather than assuming Windows-local evidence transfers | NOT_RUN |
| CUDA | Record GPU model, driver, runtime, exact torch wheel/build and wheel hashes; no driver/runtime version is selected by this document | NOT_RUN |
| System libraries | Inspect target wheel/link requirements for BLAS/OpenMP/C++ and other shared libraries. Do not invent an apt package list or install compilers merely to make resolution succeed | NOT_RUN |
| Version provenance | code_revision requires a usable Git checkout/git executable or a legitimate CODE_SNAPSHOT.json fallback. Current Dockerfile does not install Git explicitly; package/host resolution must be checked | NOT_RUN |
| Storage / permissions | Repository/input allowlist mounted at intended paths; separate writable /runs; correct ownership for writer locks, temporary files, atomic replace and logs. Preserve legal Jan–Sep overlays | NOT_RUN |
| Scheduler environment | Existing config defaults to one CPU worker, eight threads, 24 GiB admission budget plus 12 GiB reserve. These are admission estimates, not an OS memory cap or measured throughput | NOT_RUN |
| Service/container | systemd unit and Dockerfile are prepared documents/configs. No installation, startup or restart/stop behavior validated on target | NOT_RUN |

## Proposed resolved-lock procedure after separate environment authorization

1. Freeze the exact code package, target OS/architecture/ABI and CPU or CUDA wheel
   policy. Retain the existing pins as review inputs; if unavailable or incompatible,
   report the actual resolver failure. Do not silently upgrade/downgrade scientific
   packages or rebuild an unreviewed source distribution.
2. Resolve in an isolated target-matching environment. Lock all transitive packages,
   wheel filenames, versions, platform tags, source indexes and SHA-256 values.
   Keep CPU and CUDA locks separate; do not label a CPU lock CUDA-compatible.
3. Record the base image digest, OS packages/shared-library requirements, Python/pip
   versions and resolver output. Pin the packaging tools in the deployment record;
   the current bootstrap's pip upgrade is not a reproducible lock strategy by itself.
4. Build a verified wheel inventory or wheelhouse under an explicitly approved
   output directory. A resolved lock with hashes supports a future hash-checked
   install; pip freeze alone records names/versions, not wheel origin or bytes.
5. Reproduce installation in a fresh target environment, check dependencies and
   import/CLI behavior, then verify provenance recording and legal input gates.
   The current ENVIRONMENT_LOCK.txt is a selected-distribution report, not a full
   transitive lock. No new lock file is fabricated in this documentation phase.
6. CUDA numeric equivalence and CPU/GPU/concurrency benchmarks remain separate
   gated work with existing representative Development evidence. Full annual
   execution requires scientific/input authorization in addition to environment
   success. Test/Final-Test stays inaccessible.

Future acceptance must distinguish dependency resolution, deployment functioning,
numeric equivalence, throughput and scientific completeness. All remain unclaimed
here. This design finishes only C08 static classification.
