# PRE Baseline Audit

Audit date: 2026-08-04 (Asia/Hong_Kong)

Scope: read-only Phase 0 audit of the legacy PRE implementation and its current
fast output. This report is the only file created during Phase 0. No Python,
configuration, raw data, manifest, cache, or existing PRE output was changed.

## Baseline Identity

- Git branch: `main`
- Git HEAD: `7f5f36703fd6d97a050fc3d2a4c1f84681f9bf1f`
- Git log: `7f5f367 add detail`
- Initial worktree status: clean
- Python: `3.11.6`
- Baseline test command: `python -m pytest pre/tests -q`
- Baseline test result: `29 passed in 7.31s`
- PRE project version: `1.2.0`
- Legacy schema version: `arr-cs-0.3`
- Formal target: `y_movement_raw`
- Sensitivity target: `y_movement_model`

## Current Fast Output

The current local source of truth is the accepted run dated 2026-08-03, not an
older report or run name:

- Run ID: `pre-fast-20260803T022638Z-64115215`
- Run state: `PASS`
- Validation: `PASS`
- Readiness: `PASS`
- Downstream fast ready: `true`
- Formal ready: `false`
- Config hash: `59578681e8dcd408b82ce52c9d5548a826884a7dc20d62c0983c3b5d725f23b1`
- Run-state implementation hash: `f0bf26e61e2033b87e75a0e2c1300ceeac61c2e40b0979d245589156a2ca994b`
- Availability violations: `0`
- Leakage violations: `0`
- Split overlap: `0`

| Table | Rows | Columns | SHA-256 |
|---|---:|---:|---|
| episodes | 43,985 | 68 | `9f17a0fbb48af13dc9f5b882812ae073668d2bf9f4e40a5e73150fb0553070c1` |
| snapshots | 142,659 | 163 | `256c88deb6e363331bb5b755712afb45f3247d29dca9d5da6abf2d3b3435c755` |
| calibration | 912 | 86 | `28820b269d800171021e6e9c5c6aecedd317ea01d7f75e3507e7293426409e61` |
| rules | 2,915,224 | 60 | `8e1ef2bb299ed037443d6e28d699a619c773c6c34e28602d174a4d642a8cd4a2` |
| evidence_audit | 9,558,153 | 32 | `2145ddca3b99027c0c0012dca3857dfd14f0f575a0b4cf0a26ff33c71a64708c` |

The validation report records 15,851 valid episodes, 112,124 valid snapshots,
47,553 primary snapshots, and 11,058 balanced flights over five anchor days.

## Configuration Baseline

`pre/config/default.yaml` defines the six-month legacy split, nine ratio
snapshots, state lookback/quality rules, flow rules, train-fitted references,
and five-table publication. `pre/config/fast.yaml` narrows the run to five
complete Mondays in May 2022 plus adjacent flightlist coverage, lowers only the
movement/weather reference cell thresholds to one, and publishes to
`pre/output/fast`.

The active legacy schema is a single `pre/config/schema.yaml`. It contains:

- five aliases (`elapsed_ratio`, latitude, longitude, altitude, and velocity);
- required and optional columns for all five tables;
- M1 continuous/categorical inputs;
- evidence completeness inputs;
- declared consumers for `overall_run`, `overall_adv`, and `part_adv`.

The local Parquet schemas and registry hashes above outrank this declarative
schema if a mismatch is discovered in later column auditing.

## Code Size And Long Functions

The following production modules exceed the proposed ordinary-module or
orchestrator targets, or contain functions longer than 60 lines.

| File | Lines | Functions over 60 lines |
|---|---:|---|
| `pre/main.py` | 165 | `main` (97) |
| `pre/src/audit.py` | 412 | `_audit_record` (169), `build_evidence_audit` (178) |
| `pre/src/episode.py` | 222 | `prepare_legs` (90) |
| `pre/src/flow.py` | 157 | `attach_flow` (76) |
| `pre/src/input.py` | 278 | `load_flightlist` (64) |
| `pre/src/passenger_fit.py` | 212 | `fit_passenger_reference` (199) |
| `pre/src/passenger_reference.py` | 300 | `_empty_result` (67), `resolve` (184) |
| `pre/src/pipeline_build.py` | 452 | `build_all` (405) |
| `pre/src/pipeline_config.py` | 167 | `_validate_config` (61) |
| `pre/src/pipeline_passenger.py` | 294 | `_write_passenger_month_outputs` (278) |
| `pre/src/pipeline_publish.py` | 263 | `_enrich_contract` (90), `_publish` (65) |
| `pre/src/predecessor_matcher.py` | 453 | `build_predecessor_candidates` (130), `build_predecessor_features` (94) |
| `pre/src/profile_migration.py` | 201 | `migrate_legacy_profile` (127) |
| `pre/src/reference_calibration.py` | 161 | `build_calibration` (141) |
| `pre/src/rule.py` | 149 | `build_rules` (128) |
| `pre/src/snapshot.py` | 384 | `_state_for_snapshot` (69), `attach_aggregate_references` (175) |
| `pre/src/state.py` | 371 | `extract_state_data` (175) |
| `pre/src/weather.py` | 137 | `_latest_weather` (73) |

The highest-priority Phase 1 targets are `pipeline_build.py`, `snapshot.py`, and
`pipeline_publish.py`. Other long modules are recorded here but should not be
refactored opportunistically unless required by the PRE Core contract.

## Current Call And Data Flow

1. `pre/main.py` loads and resolves a mode/profile configuration.
2. `pre/src/pipeline.py` exposes the build, validate, readiness, report, and
   migration entry points.
3. `pre/src/pipeline_build.py:build_all` owns the legacy end-to-end orchestration.
4. Inventory and source loading use `inventory.py`, `input.py`,
   `input_sources.py`, and `input_eurostat.py`.
5. `episode.prepare_legs` normalizes flightlist records and
   `episode.build_episodes` creates the current single-flight episodes.
6. Reference fitting uses the `reference_*`, passenger, flow, and weather
   modules. Training rows are selected within those fit paths.
7. `snapshot.build_snapshot_grid` materializes the nine journey-ratio rows.
8. `snapshot.derive_state_requests` converts those ratio rows into state-vector
   extraction windows.
9. `state.extract_state_data` builds/reuses candidate-state and airport-flow
   cache partitions.
10. Snapshot enrichment attaches state, weather, flow, aggregate references,
    quality fields, predecessor features, and passenger proxies.
11. `rule.build_rules` and `audit.build_evidence_audit` generate the remaining
    legacy tables.
12. `pipeline_publish._enrich_contract` adds consumer-facing aliases and
    availability flags; `_write_bundle` writes the five Parquet tables.
13. `validate.validate_bundle` and `validate.readiness` validate the legacy
    bundle before `pipeline_publish._publish` replaces the accepted mode output
    atomically.

## Required Location Map

- Five-table assembly: `pre/src/pipeline_build.py`, `PreBundle(...)` near the
  end of stage 2.9; write at stage 2.10 via `_write_bundle`.
- Five-table disk publication: `pre/src/pipeline_publish.py:_write_bundle` and
  `_publish`.
- Formal target generation: `pre/src/episode.py:build_episodes`, where
  `y_movement_raw = observed_movement_time - reference_movement_time` for valid
  rows; train-only quantiles produce the sensitivity clipping bounds.
- Ratio snapshot generation: `pre/src/snapshot.py:build_snapshot_grid`.
- Ratio equality enforcement: `pre/src/validate.py`, which requires
  `snapshot_ratio == elapsed_ratio` and checks primary ratios 0.2/0.5/0.8.
- State request generation: `pre/src/snapshot.py:derive_state_requests`.
- State cache extraction: `pre/src/state.py:extract_state_data`.
- Current predecessor proxy feature matching:
  `pre/src/predecessor_matcher.py`; this is not yet a formal chain episode
  builder.

## Cache Baseline

The active cache is `pre/cache/state_extract_v2`:

- Format: `state-flow-v3`
- Files: 3,865
- Size: 952,629,606 bytes
- Data subtrees: `candidate_states/` and `flow_states/`
- Manifest: `cache_manifest.json`

The cache key currently includes raw source hashes, requested dates, core
airports and coordinates, a hash of `(icao24, request_start, request_end)`,
state/flow lookbacks, flow radius, dedup key, and the state extraction code
hash. Incompatible variants are isolated under a suffixed cache directory and
the prior cache is preserved. Phase 6 must extend or parallel this contract for
chain-interval requests without deleting this cache.

## Downstream Dependency Audit

- `overall_run/src/input.py` requires and loads all five legacy tables plus the
  target metadata, acceptance, and PRE manifest. Its validation explicitly
  checks ratio snapshots and the formal target identity.
- `overall_run/src/pipeline.py` resolves `pre/output/<mode>` and calls the above
  loader. M1 training reads `y_movement_raw` from episodes and feature columns
  from snapshots.
- `part_adv/src/pipeline_inputs.py` directly reads selected columns from
  `snapshots.parquet` and `episodes.parquet` for its model frame.
- `overall_adv` resolves the legacy PRE mode as part of the shared promoted
  cohort/overall_run lineage; it is declared as a five-table consumer by the PRE
  schema even where its immediate runtime input is an overall_run artifact.

Therefore PRE Core must publish to a separate contract-specific root and must
not cause downstream auto-switching during this task.

## Reusable Implementation

- Strict configuration merging, profile resolution, path isolation, progress,
  checkpoint, hashing, and atomic publication patterns.
- Raw inventory, file hashes, state coverage calendar, source normalization,
  and UTC parsing.
- Train-only reference fitters where their row-selection and provenance are
  verified during Phase 2/7.
- Atomic, partitioned state cache writes and compatible-subset reuse.
- Current evidence vocabulary and source lineage fields, subject to the new
  per-event/per-column Core contract.
- Current validation helpers for uniqueness, UTC/availability, target identity,
  and split leakage.
- Predecessor candidate generation as evidence for a new ambiguity-preserving
  chain builder, not as the final chain contract itself.

## Implementation To Replace Or Bypass In Core

- Single-flight episode identity as the only formal episode unit.
- `firstseen/lastseen` presentation where it could be confused with official
  operational events.
- Ratio-grid snapshot materialization as the source of observation requests.
- Snapshot-shaped state/weather/flow evidence as the only reusable observation
  product.
- The monolithic `build_all` orchestration and combined snapshot responsibilities.
- The single expanding schema file for both legacy and Core contracts.
- Evidence rows that are keyed only to snapshot features rather than explicit
  event/observation/source-record contracts.

## Explicit No-Touch Boundary

- `data/raw/` and `data/manifests/`.
- Existing `pre/output/<mode>/` artifacts and historical results.
- Existing `pre/cache/state_extract_v2/` contents.
- M1-M4 formal implementations and their output trees.
- Existing legacy CLI behavior and the five-table schema/values during Phase 1.
- Git branch, history, remote, commits, and uncommitted user work.

## Phase 0 Gate

`BASELINE_AUDIT_COMPLETE=YES`

`BASELINE_TEST_STATUS=PASS`

`SAFE_TO_REFACTOR=YES`

Rationale: the worktree began clean, the accepted fast baseline and hashes are
recorded, all 29 existing PRE tests pass, downstream dependencies are known,
and the legacy output/cache boundaries are explicit. Phase 1 may proceed only
as a behavior-preserving refactor and must compare against the recorded hashes
and schemas before any scientific semantic change.
