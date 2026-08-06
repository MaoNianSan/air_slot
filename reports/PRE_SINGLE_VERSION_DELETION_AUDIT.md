# PRE Single-Version Deletion Audit

Audit date: 2026-08-05  
Audited HEAD: `6627a705bf331c3d1a79aa201d598eee543d4d8d`  
Scope: converge PRE on `AIR_CHAIN_CORE_V2_R2` without running Fast, changing
raw data, deleting reusable cache, or modifying M1-M4 mathematics.

## A. Retired PRE implementation

The removed implementation owned the five-table publication path, ratio-grid
construction, retired target lineage, old readiness/publication orchestration,
profile migration, and compatibility wrappers. Its source, configuration,
tests, CLI commands, schema authority, and current-documentation claims are no
longer present.

## B. Retired Core implementation

The predecessor Core staging and migration-only report were not valid V2
artifacts. The tracked report was deleted, and the one confirmed local staging
tree was removed after inventory. No predecessor identity remains in source,
configuration, tests, README files, or current reports.

## C. Shared files retained by V2

- `pre/src/input.py`, `input_sources.py`, and `inventory.py`: discovery,
  hashing, normalized reads, inventory, and coverage.
- `pre/src/state.py`: current state/flow cache extraction.
- `pre/src/passenger_fit.py` and `passenger_reference.py`: train-only reference
  fitting.
- `pre/src/progress.py`: progress reporting.
- `pre/src/shared/flight_identity.py`: flight identity, split, grouping, and
  time-bin helpers migrated out of the retired episode module.
- `pre/config/sources.yaml` and the three current schema files.

The V2 cache path is used directly. The compatibility branch that inspected
retired PRE output before cache reuse was removed.

## D. Downstream references and runtime status

Status: `DOWNSTREAM_V2_MIGRATION_PENDING`.

The retained downstream mathematical modules still require an M1 Adapter to
translate V2 events, chains, source-global Observations, Membership, and
train-only references into query-time model inputs. The three runnable entry
points now stop before configuration or data access with
`PRE_CONTRACT_MISMATCH`. No compatibility tables, historical-output fallback,
or automatic retired PRE build is available.

## E. Direct deletions

The following groups were deleted after dependency inspection:

- Retired mode and schema configuration files.
- Retired pipeline, publication, snapshot-grid, target, audit, enrichment,
  reference, profile-migration, and validation modules.
- Compatibility facades in `pre/src/core/` after callers moved to the new
  observation, Membership, and validation packages.
- Tests whose sole purpose was the retired target, predecessor matcher,
  profile migration, native snapshot behavior, or old validator facade.
- The retired downstream target-lineage test.

## F. Migrations completed before deletion

- Flight identity helpers moved to `pre/src/shared/flight_identity.py`.
- Configuration loading became V2-only with shared and V2 validation functions.
- Observation, Membership, validation, and pipeline responsibilities moved to
  dedicated packages/modules before their aggregate files were deleted.
- PRE CLI imports the current pipeline directly and exposes only five current
  commands.
- Downstream entry points gained a shared Adapter gate before old integration
  paths became unreachable.

## G. Local artifacts

- `pre/output/`: deleted; it contained 174 files and 1,394,306,785 bytes.
- Confirmed predecessor Core staging: deleted.
- `pre/cache/`: preserved; 5,379 files and 1,457,804,201 bytes.
- `pre/output_core/`: preserved; no files remain after the targeted staging
  deletion.
- Raw/source data: preserved and unmodified.
- V2 published reports: preserved and refreshed.

## Deleted tracked files

Every path reported by `git diff --diff-filter=D --name-only` is listed below.

```text
docs/LEGACY_PROFILE_MIGRATION.md
overall_run/tests/test_formal_target_lineage.py
pre/config/acceptance_23d.yaml
pre/config/actions.yaml
pre/config/adapt_full.yaml
pre/config/dev.yaml
pre/config/diagnostic.yaml
pre/config/fast.yaml
pre/config/full.yaml
pre/config/m1_tail_diagnostic_current_lineage.yaml
pre/config/middle.yaml
pre/config/schema/legacy_tables.yaml
pre/config/three_change_dev.yaml
pre/reports/published/core_v2/V1_TO_V2_CACHE_REUSE_ASSESSMENT.md
pre/src/artifact_registry.py
pre/src/audit.py
pre/src/bundle_writer.py
pre/src/column_audit.py
pre/src/column_audit_report.py
pre/src/column_audit_sources.py
pre/src/contract_enrichment.py
pre/src/core/existing_bundle_validator.py
pre/src/core/membership_dataset.py
pre/src/core/membership_interval_join.py
pre/src/core/observation_dataset.py
pre/src/core/observation_membership.py
pre/src/core/observation_validation.py
pre/src/core/validation.py
pre/src/episode.py
pre/src/flow.py
pre/src/legacy_snapshot_grid.py
pre/src/pipeline.py
pre/src/pipeline_build.py
pre/src/pipeline_diagnostics.py
pre/src/pipeline_inventory.py
pre/src/pipeline_modes.py
pre/src/pipeline_passenger.py
pre/src/pipeline_publish.py
pre/src/predecessor_matcher.py
pre/src/profile_migration.py
pre/src/reference.py
pre/src/reference_calibration.py
pre/src/reference_fit.py
pre/src/reference_models.py
pre/src/reference_utils.py
pre/src/rule.py
pre/src/run_metadata.py
pre/src/shared_contracts.py
pre/src/snapshot.py
pre/src/snapshot_reference_enrichment.py
pre/src/stages/__init__.py
pre/src/stages/context.py
pre/src/stages/enrichment_stage.py
pre/src/stages/episode_stage.py
pre/src/stages/finalization_stage.py
pre/src/stages/inventory_stage.py
pre/src/stages/state_stage.py
pre/src/stages/validation_stage.py
pre/src/state_feature_resolver.py
pre/src/state_quality.py
pre/src/target_contract.py
pre/src/validate.py
pre/src/weather.py
pre/tests/test_core_idempotence.py
pre/tests/test_existing_bundle_validator.py
pre/tests/test_observation_native_dedup.py
pre/tests/test_predecessor_matching.py
pre/tests/test_profile_migration.py
pre/tests/test_target_contract.py
```

## Gate

```text
DELETION_AUDIT_COMPLETE=YES
V2_SHARED_DEPENDENCIES_IDENTIFIED=YES
SAFE_TO_REMOVE_RETIRED_PRE=YES
ALL_TRACKED_DELETIONS_DOCUMENTED=YES
DOWNSTREAM_V2_MIGRATION_PENDING=YES
```
