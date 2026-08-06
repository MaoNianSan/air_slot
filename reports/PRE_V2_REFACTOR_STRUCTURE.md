# PRE V2 Refactor Structure

Date: 2026-08-05

## Module mapping

| Old module | Old lines | New modules | Current lines | Responsibility |
|---|---:|---|---:|---|
| `core/existing_bundle_validator.py` | 658 | `validation/existing_bundle.py`, `manifest_checks.py`, `table_checks.py`, `observation_checks.py`, `membership_checks.py`, `scientific_checks.py`, `statistics_checks.py`, `report_writer.py` | 86, 87, 95, 114, 127, 58, 53, 13 | Thin orchestration plus independent check families |
| `core/membership_dataset.py` | 408 | `membership/dataset.py`, `partition_plan.py`, `partition_builder.py`, `partition_manifest.py`, `resume.py`, `parallel.py`, `validation.py` | 238, 46, 80, 68, 65, 64, 48 | Partition planning, one-partition build, manifest, Resume, workers, validation |
| `core/membership_interval_join.py` | 192 | `membership/interval_join.py` | 288 | Identity-grouped many-to-many interval join and role assignment |
| `core/observation_dataset.py` | 341 | `observations/dataset.py`, `partition_plan.py`, `partition_builder.py`, `partition_manifest.py`, `resume.py`, `retention.py`, `validation.py` | 236, 32, 24, 76, 85, 16, 59 | Source/date planning, source-global build, manifests, Resume, retention, validation |
| `core/pipeline.py` | 306 | `pipeline.py`, `build_context.py`, `build_stages.py`, `finalization.py` | 90, 57, 234, 160 | Public orchestration, state container, named stages, manifest/publication |

## Length gate

- Public pipeline orchestrator: 90 lines, limit 180.
- Existing-bundle orchestrator: 86 lines, limit 180.
- Finalization: 160 lines, limit 180.
- All ordinary current Core modules: at or below 300 lines.
- No compression-only rewrite or forwarding facade was introduced.

## Behavior evidence

- Source-global and split-neutral Observation tests.
- Many-to-many, overlapping, cross-date, vectorized-role, and partitioned
  Membership tests.
- Fileless `PASS_EMPTY` tests for both datasets.
- Partition Resume and complete-partition accounting tests.
- Independent manifest/file/schema/statistics validation tests.
- Synthetic complete-bundle validation.
- V2 identity, frozen-hash, CLI, and downstream gate tests.

```text
LONG_FILE_REFACTOR_STATUS=PASS
ORCHESTRATOR_LENGTH_STATUS=PASS
ORDINARY_MODULE_LENGTH_STATUS=PASS
BEHAVIOR_EQUIVALENCE_TEST_STATUS=PASS
```
