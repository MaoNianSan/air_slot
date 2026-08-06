# PRE V2 Debug Status

Audit time: 2026-08-05 (Asia/Hong_Kong)

Project root: `D:\research\air_slot\code\explore`

## Executive Status

`PRE_DEBUG_STATE=STABLE_NO_LONG_PROCESS`

`CURRENT_PHASE=PHASE_8_DEBUG_AND_VALIDATION_INCOMPLETE`

`FULL_PIPELINE_RUNNING=NO`

`FAST_CORE_PUBLISHED=NO`

`LEGACY_OUTPUT_PRESERVED=YES`

`RAW_DATA_MODIFIED=NO`

`M1_M2_M3_M4_MODIFIED=NO`

The active objective is recovery of a stable development state. No new large
PRE run is authorized by this report.

## Phase Status

| Phase | Status | Evidence / boundary |
|---|---|---|
| 0 Baseline audit | COMPLETE | `PRE_BASELINE_AUDIT.md`; baseline tests passed. |
| 1 No-semantic-change refactor | COMPLETE | Legacy equivalence report exists; accepted fast legacy output remains present. |
| 2 Dataset column audit | AUDIT COMPLETE, IMPLEMENTATION FOLLOW-UP OPEN | Audit reports exist, but Core does not yet retain/register every audited raw column. |
| 3 Core contract freeze | COMPLETE | `AIR_CHAIN_CORE_V1`, schema `air-chain-core-1.0`. |
| 4 Events | IMPLEMENTED, FAST EVIDENCE PASS | 78,506 event rows; proxy/official confusion 0; event order errors 0. |
| 5 Chains | IMPLEMENTED, FAST EVIDENCE PASS | 15,866 chains; 14,837 formal eligible; ambiguity leakage 0; split leakage 0. |
| 6 Native observations | IMPLEMENTED BUT GATE INCOMPLETE | 10,544,721 rows were built; raw-column preservation and resume validation remain incomplete. |
| 7 References/evidence | PARTIAL | Actual fast reference/leakage checks passed, but observation evidence is partition-summary rather than final per-column lineage. |
| 8 Validation | ACTIVE DEBUG PHASE | 41 unit/synthetic tests pass; post-fix fast validation has not been completed/published. |
| 9 CLI | IMPLEMENTED, NOT ACCEPTED | Four Core commands exist; `core-validate` currently reads stored validation rather than recomputing it. |
| 10 Cleanup/final report | NOT STARTED | README/final status and final artifact cleanup are incomplete. |

## Current Modified Files

Tracked modifications:

- `pre/config/schema.yaml` - deleted and replaced by split schema files.
- `pre/main.py` - Core CLI commands added alongside legacy commands.
- `pre/src/pipeline.py` - Core entry points exported.
- `pre/src/pipeline_build.py` - reduced to a thin legacy orchestrator.
- `pre/src/pipeline_config.py` - split legacy/Core schema loading.
- `pre/src/pipeline_publish.py` - compatibility facade after publication split.
- `pre/src/snapshot.py` - compatibility facade after snapshot split.
- `pre/tests/conftest.py` - shared Core test fixture path.

`git diff --check` reports no content errors. It only reports expected LF/CRLF
conversion warnings for tracked files.

## Current Added Files

Schema and audit:

- `pre/config/schema/{legacy_tables,core_tables,column_roles,column_aliases}.yaml`
- `pre/src/column_audit.py`
- `pre/src/column_audit_sources.py`
- `pre/src/column_audit_report.py`

Legacy refactor modules:

- `pre/src/artifact_registry.py`
- `pre/src/bundle_writer.py`
- `pre/src/contract_enrichment.py`
- `pre/src/legacy_snapshot_grid.py`
- `pre/src/run_metadata.py`
- `pre/src/snapshot_reference_enrichment.py`
- `pre/src/state_feature_resolver.py`
- `pre/src/state_quality.py`
- `pre/src/stages/` with context and six stage modules.

Core modules:

- Contracts/source: `contracts.py`, `source_loader.py`, `inventory_reuse.py`.
- Events/chains: `event_builder.py`, `event_validation.py`, `chain_builder.py`, `chain_validation.py`.
- Observations/cache: `observation_requests.py`, `state_cache.py`, `observation_state.py`, `observation_weather.py`, `observation_flow.py`, `observation_builder.py`, `observation_dataset.py`, `observation_validation.py`.
- Publication: `reference_builder.py`, `evidence_builder.py`, `column_registry.py`, `validation.py`, `writer.py`, `report.py`, `pipeline.py`, `__init__.py`.

Tests:

- `pre/tests/core_fixtures.py`
- `test_column_registry.py`
- `test_event_contract.py`
- `test_event_availability.py`
- `test_chain_builder.py`
- `test_chain_ambiguity.py`
- `test_chain_split.py`
- `test_observation_requests.py`
- `test_observation_native_dedup.py`
- `test_reference_train_only.py`
- `test_core_manifest.py`
- `test_core_idempotence.py`

## Latest Run Evidence

No Core Python process is running.

The latest fast staging directory is:

`pre/output_core/fast/.AIR_CHAIN_CORE_V1.staging-c819be31347b`

It contains observations only; no `pre_manifest.json`, validation report,
readiness report, run state, or persisted run log was published.

Parquet metadata, read without loading the large tables, shows:

| Source | Partitions | Rows | Bytes |
|---|---:|---:|---:|
| state | 5 | 10,290,528 | 597,510,477 |
| flow | 5 | 251,396 | 8,679,168 |
| weather | 19 | 2,797 | 489,001 |
| total | 29 | 10,544,721 | 606,678,646 |

The fast Core cache is complete:

- Cache: `pre/cache/state_extract_core_v1-6840ae55cc35`
- Cache key: `6840ae55cc358c3246dc998134fa76bd08e9e7f895c93ca87445176d8e9d5eba`
- Partitions: 120/120
- Candidate rows: 10,290,528
- Flow source rows: 7,087,981
- Completed at: `2026-08-04 12:43:59 UTC`

Legacy `pre/output/fast` remains present and was not overwritten.

## Failure Position

Last explicit application failure:

`Core 6/7 - Validate and freeze hashes`

Error type:

`IMPLEMENTATION_VALIDATION_AGGREGATION_ERROR`

The observation validation summary was marked `FAIL` even though all measured
error counts were zero. Cause: Python `bool` is a subclass of `int`; the
partition aggregator counted `native_resolution_preserved=True` and
`on_demand_evidence_supported=True` as numeric errors. The code now excludes
booleans, and the regression suite passes.

Latest recovery failure:

`Core 4/7 - Native observation partition resume`

Error type:

`INEFFICIENT_RESUME_IO_AND_HASHING`

The recovery path read full observation partitions and converted all values to
strings for content hashing. It did not produce a data/schema traceback, but it
was stopped after excessive I/O time. The code has been changed to read a
nine-column validation projection and hash the Parquet file bytes. This change
has unit/static coverage but has not been verified against the full staging set.

## Data Versus Code Assessment

No current evidence identifies a corrupt raw archive as the fast failure:

- State cache completed 120/120 partitions.
- Fast event source-hash missing count was 0.
- Fast observation source-hash missing count was 0.
- Availability-before-event count was 0.
- Outside-request-interval count was 0.
- Duplicate observation ID count was 0.

Known dataset limitations remain scientific blockers, not parser failures:

- No official local AOBT, AIBT, ATOT, ALDT, or SOBT fields.
- No official rotation, cancellation, diversion, or aircraft-swap fields.
- Chain labels `y_ob`, `y_tx`, and `y_to` therefore remain null with reasons.

## Unfinished Refactor / Contract Work

1. Raw-column preservation is incomplete. `STATE_COLUMNS`, METAR normalization,
   and the common observation schema retain modeled standardized fields but do
   not yet retain every audited raw field such as state `callsign`, `alert`,
   `spi`, `squawk`, `geoaltitude`, `lastposupdate`, `lastcontact`, and several
   METAR sky/raw-report fields.
2. The column registry is generated from current Core output columns, not the
   complete audited raw-source column set. The frozen rule "classification is
   not deletion" is therefore not yet satisfied by implementation.
3. Observation evidence is summarized per source/date partition. Raw rows carry
   source record/file/hash lineage, but final per-column evidence publication is
   not complete.
4. Staging resume currently selects the newest staging directory without first
   verifying a persisted config hash, request hash, code hash, cache key, and
   expected partition manifest.
5. Failed Core runs do not persist an early run log/run state before final
   publication, making terminal output the only detailed failure record.
6. `pre/src/core/pipeline.py` is 221 lines, above the suggested 180-line
   orchestrator target.
7. `core-validate` reads a stored validation JSON and is not yet an independent
   recomputation gate.
8. `pre/README.md` and `PRE_CORE_FINAL_STATUS.md` are not updated.

## Static And Unit Check

`CORE_COMPILE_STATUS=PASS`

`PRE_TEST_STATUS=PASS_41_TESTS`

No real-data smoke or full PRE was started after this debug audit.

## Next Minimum Repair Action

Do not resume the full fast staging yet.

1. Add a small staging resume manifest written before observations, containing
   Core schema hash, config/request/interval/code hashes, cache key, and expected
   source/date partitions.
2. Add a synthetic two-partition resume test proving projection validation,
   boolean aggregation, file hashing, and rejection of incompatible staging.
3. Define and test the minimal non-dropping raw-column storage/registry mapping
   for flightlist, state, and METAR without changing event/chain semantics.
4. Run only unit tests, then a tiny synthetic/local partition smoke. Do not run
   fast again until these checks pass and the existing staging compatibility is
   proven.

`NEXT_ALLOWED_STEP=STATIC_RESUME_CONTRACT_AND_SMALL_TEST_FIX`

`KNOWN_BLOCKERS=RAW_COLUMN_RETENTION;COLUMN_LEVEL_EVIDENCE;UNVERIFIED_STAGING_RESUME;UNSUPPORTED_OPERATIONAL_EVENTS`
