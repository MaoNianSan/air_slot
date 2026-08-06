# PRE Refactor Equivalence

Report date: 2026-08-04 (Asia/Hong_Kong)

## Scope

Phase 1 modularized the legacy PRE implementation without changing the legacy
five-table contract or scientific calculations. Existing accepted outputs under
`pre/output/fast` and the state cache under `pre/cache/state_extract_v2` were
not overwritten or deleted.

## Structural Changes

- `pipeline_build.py` is now a 27-line orchestrator.
- Explicit build state is carried by `stages.context.PreBuildContext`.
- Inventory, episode/reference, state, enrichment, validation, and finalization
  are separate stage modules.
- `snapshot.py` is a compatibility facade over legacy ratio-grid generation,
  state feature resolution, state quality, and reference enrichment.
- `pipeline_publish.py` is a compatibility facade over contract enrichment,
  bundle writing/publication, and artifact registry generation.
- The legacy schema was split into `config/schema/legacy_tables.yaml`,
  `column_roles.yaml`, `column_aliases.yaml`, and `core_tables.yaml`.
- The unified schema object is value-equal to the removed `config/schema.yaml`.
- Existing public imports used by PRE tests, profile migration, and pipeline
  modes remain available.

All newly introduced ordinary modules are at most 300 lines. Stage files are at
most 178 lines, the finalization stage is 62 lines, and no newly introduced
function exceeds 80 lines.

## Configuration Equivalence

- Baseline fast config hash: `59578681e8dcd408b82ce52c9d5548a826884a7dc20d62c0983c3b5d725f23b1`
- Refactored default fast config hash: `59578681e8dcd408b82ce52c9d5548a826884a7dc20d62c0983c3b5d725f23b1`
- Unified split-schema object equals the former single-schema object: `true`

The isolated equivalence run used CLI `--output-dir`; the current CLI includes
that raw path override in the config hash, so that run recorded
`d434ec59c32ac375a72df42399a4cb2757cc93ab0a9469ea0a628080e7d5e61e`.
This is an existing output-path hashing behavior, not a refactor calculation
change. The normal fast profile retains the baseline hash exactly.

## Fast Equivalence Run

Command:

```powershell
python -u pre/main.py build --mode fast `
  --output-dir D:\research\air_slot\code\explore\pre\output\phase1_equivalence `
  --progress quiet --n-jobs 1
```

Result:

- Status: `PASS`
- Validation: `PASS`
- Readiness: `PASS`
- Elapsed: 1,565.9 seconds
- Cache status: `HIT` for state extraction and state/flow consumers
- Availability violations: `0`
- Leakage violations: `0`
- Split overlap: `0`

An earlier isolated attempt stopped before state extraction because
`state_stage._extract_state` retained the old local name `requests`. It was
changed to the explicit `ctx.requests`, the full test suite was rerun, and the
successful equivalence build above completed. No accepted output was touched.

## Five-Table Comparison

Baseline: accepted fast run `pre-fast-20260803T022638Z-64115215` dated
2026-08-03.

Refactor evidence: isolated Phase 1 build dated 2026-08-04.

| Table | Rows | Columns | Comparison |
|---|---:|---:|---|
| episodes | 43,985 | 68 | byte-identical |
| snapshots | 142,659 | 163 | byte-identical |
| calibration | 912 | 86 | byte-identical |
| rules | 2,915,224 | 60 | byte-identical |
| evidence_audit | 9,558,153 | 32 | equal except run provenance |

Exact unchanged SHA-256 values:

- episodes: `9f17a0fbb48af13dc9f5b882812ae073668d2bf9f4e40a5e73150fb0553070c1`
- snapshots: `256c88deb6e363331bb5b755712afb45f3247d29dca9d5da6abf2d3b3435c755`
- calibration: `28820b269d800171021e6e9c5c6aecedd317ea01d7f75e3507e7293426409e61`
- rules: `8e1ef2bb299ed037443d6e28d699a619c773c6c34e28602d174a4d642a8cd4a2`

For `evidence_audit`, Parquet schema and row-group structure are identical.
Column-by-column comparison found differences only in:

- `ingested_time`: expected run timestamp difference;
- `generation_config_hash`: expected isolated `--output-dir` hash difference.

All other 30 columns are equal across all ten Parquet row groups. In
particular, entity keys, feature values, event/availability/decision times,
source fields, evidence status, missing reasons, fallback levels, and formal
eligibility are unchanged.

## Target And Validation Equivalence

- Formal target definition hash unchanged:
  `02207657a480ee9e6190d5fd524e3646ddf1e4e03f97b7d5fbd506ce74ba7af2`
- Sensitivity target definition hash unchanged:
  `ebff08efc004baa5481d16f87c49b8747674e1bdf3505afcd5143467fb651967`
- Rows total: 43,985 in both runs
- Raw/model non-null: 15,851 in both runs
- Raw/model differing rows: 215 in both runs
- Label identity mismatches: 0 in both runs
- Validation JSON: value-equal
- Consumer readiness JSON: value-equal

## Tests And Static Checks

- `python -m compileall -q pre`: `PASS`
- `python -m pytest pre/tests -q`: `29 passed`
- Compatibility import smoke: `PASS`
- `git diff --check`: `PASS`
- Raw data changed: `NO`
- Existing cache changed or deleted: `NO`
- Existing accepted fast output overwritten: `NO`
- M1-M4 code changed: `NO`

## Runtime Observation

Both runs used cache hits. The refactor evidence run was slower in state feature
attachment and flow attachment, but produced byte-identical snapshot/rule data.
The available evidence does not identify a semantic regression; wall-clock
variation may include filesystem cache and concurrent host load. Performance
optimization is not part of Phase 1 and must not be mixed with Core semantics.

## Phase 1 Gate

`REFACTOR_BEHAVIOR_EQUIVALENT=YES`

`PRE_TEST_STATUS=PASS`

`NO_FORMAL_SEMANTIC_CHANGE=YES`

`LEGACY_OUTPUT_PRESERVED=YES`

`STATE_CACHE_PRESERVED=YES`

Phase 2 may begin with the actual local schemas and Parquet/CSV columns as the
source of truth.
