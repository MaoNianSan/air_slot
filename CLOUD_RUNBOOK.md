# Air Slot Cloud Runbook

## Current boundary

PRE is `AIR_CHAIN_CORE_V2_R2`. The M1 Adapter is not implemented, so
`overall_run`, `overall_adv`, and `part_adv` intentionally stop with
`PRE_CONTRACT_MISMATCH`. Do not bypass that gate or point downstream commands at
historical output.

## Environment

Use Python 3.11 and install the root requirements file. Keep `data/` read-only
and place generated PRE data only under the configured local output, cache, and
staging roots.

## Verification before compute

```powershell
D:/Python311/python.exe -m compileall -q pre/src pre/tests pre/tools
D:/Python311/python.exe -m pytest -q pre/tests
D:/Python311/python.exe pre/main.py inspect-config --mode fast
```

Confirm the printed contract, schema, research revision, and frozen config hash
before allocating a long-running worker.

## PRE execution

The supported PRE interface is:

```powershell
D:/Python311/python.exe pre/main.py build --mode fast --progress normal --n-jobs 1
D:/Python311/python.exe pre/main.py validate --mode fast
D:/Python311/python.exe pre/main.py readiness --mode fast
D:/Python311/python.exe pre/main.py report --mode fast
```

Start with one worker. Increase parallelism only after a bounded smoke passes
and memory is measured for the largest source/date partition.

## Resume and failure handling

Resume accepts only a staging bundle with the exact scientific/data identity.
Git and implementation differences are provenance warnings; contract, schema,
research revision, frozen configuration, source/request hashes, episode
intervals, cache key, and expected partitions are hard gates.

A command timeout does not prove its child process stopped. Check the PID,
heartbeat, log, run state, and partition manifests before relaunching. Never
start a second build blindly.

## Publication boundary

Validation and readiness inspect a published bundle; they do not retrain or
rebuild it. Implementation reports under `pre/reports/published/core_v2/` are
pre-run evidence, not a formal Fast bundle.

## Data and upload policy

- Preserve `data/` and `pre/cache/`.
- Preserve compatible V2 staging unless explicitly invalidated.
- Do not upload output, cache, staging, raw data, Parquet, logs, or local debug
  reports.
- Do not commit or push automatically.

## Downstream work

The next downstream task is to design and implement an M1 Adapter that reads V2
artifacts at `query_time` with availability-safe joins. Until that work is
complete, no cloud command may run M1-M4.
