# pre

## 1. Role

PRE is the only raw-data processing layer. It reads the immutable `../data/`
tree and publishes the formal tables consumed by every downstream module.

## 2. Read-only inputs

Raw inputs are under `../data/raw/`; frozen selection manifests are under
`../data/manifests/`. PRE never writes to either location. A missing or
mismatched frozen manifest is a blocking error.

## 3. Five-table contract

The published contract is:

```text
episodes.parquet
snapshots.parquet
calibration.parquet
rules.parquet
evidence_audit.parquet
```

The formal label is `y_movement_raw` under
`Y_MOVEMENT_RAW_V1_20260725`. `y_movement_model` is derived only for sensitivity
analysis. Publication also records the formal target definition hash and label
lineage.

## 4. Passenger and missingness

Passenger proxies use `DESTINATION_LAGGED_MONTH`. Unsupported historical cells
remain `UNSUPPORTED`; they are never zero-filled. PRE does not interpolate
across dates. Evidence status, missing reason, source period, and support count
remain explicit in the five-table contract.

## 5. Cache

Reusable state and airport-flow partitions are under `cache/state_extract_v2/`.
Only PRE reads or writes this cache. A normal all-hit run does not rewrite the
cache manifest. `clean.py` never removes `cache/`; `--rebuild-cache` is a
separate explicit operation and is not part of Fast reproduction.

## 6. CLI

All commands assume the working directory is the **project root**
(`../` relative to this README, i.e. `D:\research\air_slot\code\explore`).
If your shell is inside the `pre/` directory, replace `pre/main.py` with
`main.py` and `pre/clean.py` with `clean.py`.

```powershell
# Fast reproduction (from project root)
python -u pre/main.py fast --progress normal --n-jobs 1
python -u pre/main.py validate fast --progress normal --n-jobs 1
python pre/main.py report fast

# Adapt-full (from project root)
python -u pre/main.py adapt_full --progress normal --n-jobs 2
python -u pre/main.py validate adapt_full --progress normal --n-jobs 2

# Clean output (from project root)
python pre/clean.py --mode fast --dry-run
python pre/clean.py --mode fast
python pre/clean.py --all-output --dry-run
python pre/clean.py --all-output
```

The CLI also recognizes `diagnostic` and `full`; neither is started in the
current local stage. `precision` is accepted by `clean.py` for cleanup but is a
downstream post-Full activity, not a PRE mode.

## 7. Parallelism

State-partition work may use bounded loky workers. The parent process retains
the requested file order, writes the cache manifest, assembles all five tables,
publishes the registry, and records the heartbeat. With outer parallelism,
bottom-level thread libraries are limited to one thread.

## 8. Outputs and validation

Published mode output is under `output/<mode>/`. Fast validation requires five
tables, unique keys, no split overlap, no future leakage, no availability
violations, a valid formal target hash, a passing registry, and zero stale
artifacts. Downstream readiness is published only after these checks pass.
