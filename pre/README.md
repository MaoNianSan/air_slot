# pre

## 1. Role

`pre/` is the only raw-data processing layer of the Air Slot project. It reads
the immutable `../data/` tree and publishes formal tables consumed by every
downstream module. It contains two processing lines:

- the **legacy PRE pipeline** (five-table contract, `output/<mode>/`);
- the **PRE Core** line (`AIR_CHAIN_CORE_V1`, `output_core/<mode>/`), which
  rebuilds the same raw inputs as interval-based native observations, events,
  chains and train-only references.

## 2. Read-only inputs

Raw inputs are under `../data/raw/`; frozen selection manifests are under
`../data/manifests/`. PRE never writes to either location. A missing or
mismatched frozen manifest is a blocking error.

## 3. Legacy five-table contract

The published legacy contract is:

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
lineage. Legacy output is published under `output/<mode>/`.

## 4. Passenger and missingness

Passenger proxies use `DESTINATION_LAGGED_MONTH`. Unsupported historical cells
remain `UNSUPPORTED`; they are never zero-filled. PRE does not interpolate
across dates. Evidence status, missing reason, source period, and support count
remain explicit in the published tables.

## 5. PRE Core (AIR_CHAIN_CORE_V1)

### 5.1 Identity

- Contract ID: `AIR_CHAIN_CORE_V1`
- Schema version: `air-chain-core-1.0`
- Machine-readable authority: `config/schema/core_tables.yaml`, joined with the
  Core sections of `column_roles.yaml` and `column_aliases.yaml`.
- Output root: `output_core/<mode>/AIR_CHAIN_CORE_V1`
- Legacy output root remains `output/<mode>`; downstream auto-switch is
  prohibited.

### 5.2 Data flow

Core is a seven-stage build:

```text
raw inventory and source normalization
  -> event facts with support levels            (Core 1/7, 2/7)
  -> predecessor-successor chain candidates
  -> ambiguity-preserving chain episodes and frozen split
  -> interval-based native observations         (Core 3/7, 4/7)
  -> train-only references and evidence         (Core 5/7)
  -> validation and hash freeze                 (Core 6/7)
  -> publish                                    (Core 7/7)
```

Core does not materialize five-minute nodes, roll samples, GRU tensors, GRU
masks, model predictions, action effects, or rankings.

### 5.3 Core tables

| Artifact | Content |
|---|---|
| `episodes.parquet` | One row per `(predecessor_flight, successor_flight)` candidate; ambiguous candidates remain visible with `chain_match_status=AMBIGUOUS` and `formal_eligible=false`. Split is assigned from `episode_start_time`, never from a future outcome. |
| `events.parquet` | One row per flight-event fact with explicit event time, availability time, raw field, source record/file/hash, reconstruction method, confidence, and support level. |
| `observations/` | Partitioned Parquet dataset keyed by `source` and `observation_date`, matching the dominant access pattern (select one source, scan dates overlapping a chain interval). Common lineage/time columns are mandatory; source value columns are nullable. Native record times are preserved (no five-minute resampling). |
| `calibration.parquet` | Long-form frozen references; every row records reference type, group key, statistic, value, cell size, fallback level, fit period, `fit_split=train`, and source hash. |
| `evidence_audit.parquet` | Long-form evidence facts keyed by `evidence_id`, with raw source/field, record/file/hash, event and availability times, transformation, support level, and formal eligibility. |
| `column_registry.yaml` | Registry of every published column with role/retention metadata. |

Local support is frozen at contract time:

| Event | Local construction | Support |
|---|---|---|
| `ATOT_MINUS` | predecessor OpenSky `firstseen` | `SUPPORTED_PROXY` |
| `ALDT_MINUS` | predecessor OpenSky `lastseen` | `SUPPORTED_PROXY` |
| `AIBT_MINUS` | no source field | `UNSUPPORTED` |
| `AOBT_PLUS` | no source field | `UNSUPPORTED` |
| `ATOT_PLUS` | successor OpenSky `firstseen` | `SUPPORTED_PROXY` |

No `firstseen`/`lastseen` field may be renamed or marked as an official observed
operational event. Sub-contracts: `AIR_CHAIN_EVENT_V1`,
`IMMEDIATE_NEXT_OBSERVED_LEG_V1`, `EPISODE_START_FROZEN_SPLIT_V1`,
`TRAIN_ONLY_REFERENCE_V1`, `NATIVE_INTERVAL_OBSERVATION_V1`.

### 5.4 Staging and publication

Core builds into a staging bundle named
`.AIR_CHAIN_CORE_V1.staging-<hash>` beside the output root. On a successful
`core-build`, the staging is atomically renamed to the output root; a
`pre_manifest.json`, `run_state.json`, and `reports/` (`core_validation.json`,
`core_readiness.json`, `core_cache_manifest.json`, `PRE_CORE_RUN_REPORT.md`) are
written before publication. If the output root already exists with an identical
`core_data_hash`, the identical result is reused; a different hash is a
blocking error.

## 6. Schema layout

`config/schema.yaml` was split into four files with a **value-identical** legacy
schema object:

```text
config/schema/
  legacy_tables.yaml    # legacy tables + consumers
  core_tables.yaml      # Core contract tables, manifest/registry/partitioning rules
  column_roles.yaml     # m1_required_inputs, evidence_completeness_features,
                        # role_definitions, core_column_roles
  column_aliases.yaml   # legacy aliases, core_aliases, forbidden_aliases
```

`pipeline_config.load_config` builds the legacy `config["schema"]` from the
legacy sections and the Core `config["core_schema"]` from the Core sections, so
the accepted legacy fast config hash is unchanged.

## 7. Cache

- Legacy reusable state/airport-flow partitions: `cache/state_extract_v2/`.
- Core state cache: `cache/state_extract_core_v1-<cache_key>/` with
  `candidate_states/`, `flow_states/`, and `cache_manifest.json`. The cache key
  is derived from the observation requests and configuration; a full hit skips
  re-extraction.
- Only PRE reads or writes these caches. A normal all-hit run does not rewrite
  the cache manifest. `clean.py` never removes `cache/`; `--rebuild-cache` is a
  separate explicit operation and is not part of Fast reproduction.

## 8. CLI

All commands assume the working directory is the **project root**
(`../` relative to this README, i.e. the parent of `pre/`).
If your shell is inside the `pre/` directory, replace `pre/main.py` with
`main.py` and `pre/clean.py` with `clean.py`.

Legacy pipeline:

```powershell
# Fast reproduction (from project root)
python -u pre/main.py fast --progress normal --n-jobs 1
python -u pre/main.py validate fast --progress normal --n-jobs 1
python pre/main.py report fast

# Legacy adapt-full (backward compatibility only; not a current run mode)
python -u pre/main.py adapt_full --progress normal --n-jobs 2
python -u pre/main.py validate adapt_full --progress normal --n-jobs 2
```

PRE Core:

```powershell
python -u pre/main.py core-build fast --progress normal --n-jobs 1
python pre/main.py core-validate fast
python pre/main.py core-readiness fast
python pre/main.py core-report fast
```

The CLI also recognizes `inventory`, `readiness`, `repair`, `migrate-profile`,
`diagnostic`, `acceptance_23d`, `middle`, and `full`. `precision` is accepted by
`clean.py` for cleanup but is a downstream post-Full activity, not a PRE mode.

Clean output (from project root):

```powershell
python pre/clean.py --mode fast --dry-run
python pre/clean.py --mode fast
python pre/clean.py --all-output --dry-run
python pre/clean.py --all-output
```

## 9. Parallelism

State-partition work may use bounded loky workers. The parent process retains
the requested file order, writes the cache manifest, assembles all tables,
publishes the registry, and records the heartbeat. With outer parallelism,
bottom-level thread libraries are limited to one thread.

## 10. Outputs and validation

- Legacy: published mode output is under `output/<mode>/`. Fast validation
  requires five tables, unique keys, no split overlap, no future leakage, no
  availability violations, a valid formal target hash, a passing registry, and
  zero stale artifacts. Downstream readiness is published only after these
  checks pass.
- Core: published output is under `output_core/<mode>/AIR_CHAIN_CORE_V1`.
  `core-validate` reports the frozen validation recorded at publish time;
  `core-readiness` reports downstream readiness.

## 11. Tests

Run the full suite from the project root:

```powershell
python -m pytest pre/tests -q
```

As of 2026-08-05 the suite is 41 passing (legacy equivalence, schema loading,
strict config, Core contracts, chain/event/observation/reference, manifest and
idempotence tests). `python -m compileall -q pre/src pre/tests` must stay clean.

## 12. Current development state

As of 2026-08-05 the Core line is in **Phase 8 debug/validation**:
- The legacy fast run remains accepted (`pre/output/fast`).
- The latest Core fast staging is
  `output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b` (observations only;
  no manifest/validation/readiness published yet).
- Known development blockers are raw-column retention, column-level evidence,
  unverified staging resume, and unsupported operational events. These are
  development blockers, not contract violations.

## PRE Core V2

Current implementation contract:

- `AIR_CHAIN_CORE_V2`
- `air-chain-core-2.0`
- `AIR_CHAIN_CORE_V2_R2`

The implementation includes:

- source-global native-resolution observations;
- partitioned many-to-many observation Membership;
- `PASS_EMPTY` partition semantics;
- research-oriented Resume identity;
- independent bundle validation.

Implementation validation reports are available under
`pre/reports/published/core_v2/`.

No formal Fast V2 bundle has been generated yet. Legacy PRE remains available
for the existing downstream pipeline.
