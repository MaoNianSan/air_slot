# Output Registry and Lineage

**Version**: R1.5
**Modules**: `overall_run`, `overall_adv`, `part_adv`

## Registry Architecture

Each module publishes two registry tiers:

| Module | Core Registry | Publication Registry |
|--------|--------------|---------------------|
| `overall_run` | 24 semantic artifacts | 113 census artifacts |
| `overall_adv` | Artifact registry | N/A |
| `part_adv` | Artifact registry | N/A |

## overall_run Registry Contracts

### Core Registry (`OVERALL_RUN_CORE_REGISTRY_V1_20260731`)

24 required semantic artifact IDs:

```
action_metadata.parquet
audit.parquet
config_sources.json
failure_records.parquet
implementation_manifest.json
m1.joblib
m2.joblib
m3.joblib
m3_action_library.parquet
m3_response_audit.parquet
m3_response_parameters.parquet
m3_response_samples.parquet
m4.joblib
m4_action_scores.parquet
m4_candidate_screen.parquet
m4_rankings.parquet
m4_recommendations.parquet
merged_config.json
model_contract.json
parameter_manifest.json
parameter_manifest.parquet
run_manifest.json
run_summary.json
scientific_gate.json
```

Each entry records: `sha256`, `file_size`, `created_at`, `artifact_entry_schema_version`.

### Publication Registry (`OVERALL_RUN_PUBLICATION_REGISTRY_V1_20260731`)

Includes all core artifacts PLUS publication-generated files:

```
publication_manifest.json
tables/core/table01_m1_distributional_validity.parquet
tables/core/table03_m2_channel_cost_summary.parquet
tables/core/table04_m3_response_library.parquet
tables/core/table05_m4_screening_and_recommendation.parquet
tables/core/figure_metadata.parquet
figures/figure_metadata.json
logs/publication.log
figures/core/fig01_*.{png,pdf,svg}
figures/core/fig02_*.{png,pdf,svg}
figures/core/fig03_*.{png,pdf,svg}
figures/core/fig04_*.{png,pdf,svg}
figures/core/fig05_*.{png,pdf,svg}
audits/m4_*.{csv,parquet}
```

The publication census count (113 in current R1) is a per-run version result,
NOT a fixed constant.

## Lineage Chain

```
data/ (read-only)
  └── pre/output/fast/
        ├── episodes.parquet
        ├── snapshots.parquet
        ├── calibration.parquet
        ├── rules.parquet
        └── evidence_audit.parquet
              └── overall_run/output/fast/
                    ├── m1.joblib, m2.joblib, m3.joblib, m4.joblib
                    ├── artifact_registry.json (core → publication)
                    └── publication_manifest.json
                          ├── overall_adv/output/fast/
                          │     └── common_support_cohort.json
                          └── part_adv/output/fast/
                                └── common_support_cohort.json
```

## Lineage Validation

Each downstream module records its upstream binding:

| Field | Meaning |
|-------|---------|
| `upstream_run_id` | The authoritative overall_run run_id |
| `upstream_registry_hash` | Hash of the upstream artifact_registry.json |
| `common_support_cohort_hash` | Hash of the shared evaluation cohort |
| `upstream_formal_target_column` | Must be `y_movement_raw` |

Formal validators check:
- `upstream_run_id` matches expected
- `common_support_cohort_hash` is consistent across modules
- `stale_artifacts=0`
- Registry hashes are intact

## Invariants

- Core registry count is 24 (frozen semantic contract)
- Publication census varies by run (not fixed to any number)
- `common_support_cohort_hash` must be identical in overall_adv and part_adv
- Downstream modules read published artifacts only, never raw data
- Registry JSON is never manually edited
