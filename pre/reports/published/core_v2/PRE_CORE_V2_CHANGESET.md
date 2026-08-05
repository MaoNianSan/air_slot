# PRE Core V2 changeset

Date: 2026-08-05

This index summarizes the current Git working-tree diff. It describes
responsibilities without reproducing source code. No M1-M4 files are included.

## Contract and identity

- `pre/src/core/contracts.py`: defines the V2 contract IDs, research revision,
  frozen configuration identity, implementation provenance, and Resume contract
  data model.
- `pre/src/core/resume_contract.py`: builds, writes, compares, and audits the
  hard Resume identity while treating Git and implementation changes as
  provenance warnings.
- `pre/src/core/pipeline.py`: integrates the Resume contract, partitioned
  Membership build, registry inputs, validation, manifest provenance, and
  existing-bundle validation into Core orchestration.
- `pre/src/core/writer.py`: resumes compatible staging bundles and persists
  deterministic table hashes and schema-aware table output.

## Observation and Membership

- `pre/src/core/observation_builder.py`: publishes source-global observations
  and removes Membership-only fields while retaining source-native columns.
- `pre/src/core/observation_dataset.py`: writes and resumes atomic source/date
  Observation partitions with `PASS_EMPTY`, schema fingerprints, hashes, row
  counts, and explicit read-failure handling.
- `pre/src/core/observation_requests.py`: creates request intervals from
  engineering-eligible chains and carries state/airport identity fields.
- `pre/src/core/observation_state.py`: selects each native state record once for
  the union of relevant request intervals.
- `pre/src/core/observation_weather.py`: keeps native weather records without
  chain-level duplication.
- `pre/src/core/observation_flow.py`: aligns flow observations with the
  source-global contract.
- `pre/src/core/observation_validation.py`: rejects embedded chain, split, and
  request fields in source-global Observation output.
- `pre/src/core/observation_membership.py`: provides the compatibility wrapper
  over partitioned many-to-many Membership construction.
- `pre/src/core/membership_interval_join.py`: performs identity-grouped,
  vectorized interval joins and assigns frozen Membership roles.
- `pre/src/core/membership_dataset.py`: writes, validates, and resumes atomic
  source/date Membership partitions, including `PASS_EMPTY`.

## Chain semantics

- `pre/src/core/chain_builder.py`: searches past invalid earliest candidates,
  records candidate rejection reasons, preserves ambiguity, and separates
  engineering from scientific eligibility.
- `pre/src/core/chain_validation.py`: validates the revised eligibility fields
  and deprecated compatibility alias.

## Reference and validation

- `pre/src/core/reference_builder.py`: reads matching training Observation and
  Membership partitions and deduplicates source-global observations before
  fitting references.
- `pre/src/core/validation.py`: computes Core statistics and combines chain,
  Observation, Membership, registry, and readiness validation.
- `pre/src/core/existing_bundle_validator.py`: independently enumerates and
  validates an existing bundle, detects extra or missing partition files, and
  recomputes stored statistics.
- `pre/src/core/column_registry.py`: records raw-to-standard lineage, retention,
  aliases, roles, and observed source-column coverage.

## Configuration and raw-input support

- `pre/config/default.yaml`: adds V2 raw-column and Membership partition runtime
  controls.
- `pre/config/schema/core_tables.yaml`: advances the schema to V2, declares the
  partitioned Membership table, identity fields, manifests, eligibility, and
  registry requirements.
- `pre/config/schema/column_roles.yaml`: registers the new raw state and
  eligibility columns and their permitted roles.
- `pre/src/pipeline_config.py`: loads and strictly validates the new Core schema
  and runtime keys while preserving the frozen research hash boundary.
- `pre/src/input.py`: retains source file information required for provenance
  and raw-column coverage.
- `pre/src/state.py`: carries the additional native state-vector columns needed
  by V2.
- `pre/src/core/state_cache.py`: detects V1 cache column insufficiency and uses
  the V2 raw-column cache namespace.

## Public tooling and packaging

- `pre/tools/pre_core_v2_membership_benchmark.py`: exposes the read-only join
  benchmark with explicit local input paths and no generated output files.
- `.gitignore`: continues excluding runtime data while re-including only
  `pre/reports/published/**`.
- `pre/.gitignore`: keeps output, Core staging, cache, and local reports ignored
  while allowing curated published evidence.
- `pre/README.md`: documents the V2 contract, features, evidence directory, and
  absence of a formal Fast V2 bundle without removing legacy PRE guidance.
- `pre/reports/published/core_v2/`: contains only small, sanitized validation
  summaries and upload-readiness evidence.

## Test support files

- `pre/tests/core_v2_bundle_fixture.py`: builds a complete synthetic V2 bundle
  for independent validator tests.
- `pre/tests/membership_dataset_test_utils.py`: supplies reusable Membership
  dataset, partition, and Resume fixtures.
- `pre/tests/membership_test_data.py`: supplies deterministic Observation and
  request frames for interval-join tests.

## Tests

- `pre/tests/test_core_manifest.py`: updates manifest expectations to the V2
  contract.
- `pre/tests/test_chain_eligibility_semantics.py`: separates engineering proxy
  eligibility from scientific chain eligibility.
- `pre/tests/test_chain_skips_invalid_earliest_candidate.py`: verifies candidate
  search continues after an invalid earliest successor.
- `pre/tests/test_column_registry_raw_coverage.py`: requires registry coverage
  for actual retained source columns.
- `pre/tests/test_core_v2_synthetic_resume_smoke.py`: exercises two-partition
  synthetic Resume, including empty partitions.
- `pre/tests/test_core_v2_tiny_real_data_smoke.py`: exercises a small real state
  partition through V2 observation and Membership logic.
- `pre/tests/test_existing_bundle_validator.py`: checks independent validation
  and statistics recomputation.
- `pre/tests/test_frozen_config_hash_consistency.py`: proves worker settings are
  operational while split and chain rules are frozen semantics.
- `pre/tests/test_git_metadata_is_provenance_only.py`: verifies Git and
  implementation differences warn rather than reject Resume.
- `pre/tests/test_implementation_hash_empty_scope_warning.py`: rejects an empty
  implementation scope as a normal successful hash.
- `pre/tests/test_implementation_hash_scope.py`: checks non-Core dependencies
  are included in implementation provenance.
- `pre/tests/test_membership_cross_date_request.py`: checks one read per
  overlapping source/date partition.
- `pre/tests/test_membership_interval_join_matches_reference.py`: compares the
  vectorized join with the brute-force reference.
- `pre/tests/test_membership_overlapping_requests_many_to_many.py`: preserves
  many-to-many Membership for overlapping chains.
- `pre/tests/test_membership_partition_resume.py`: reuses valid Membership
  partitions by hash, schema, and row count.
- `pre/tests/test_membership_pass_empty_partition.py`: records no-match
  Membership partitions as `PASS_EMPTY` without a file.
- `pre/tests/test_membership_role_vectorized.py`: verifies vectorized state-role
  precedence.
- `pre/tests/test_membership_split_neutral_observation.py`: keeps split on
  Membership rather than Observation rows.
- `pre/tests/test_observation_membership_overlap.py`: allows one Observation to
  belong to multiple overlapping chains.
- `pre/tests/test_observation_pass_empty_partition.py`: records legal empty
  Observation partitions without Parquet output.
- `pre/tests/test_observation_split_neutrality.py`: rejects chain and split
  fields in source-global observations.
- `pre/tests/test_pass_empty_does_not_hide_read_failure.py`: distinguishes a
  source read failure from a legal empty partition.
- `pre/tests/test_raw_column_retention.py`: checks native source columns survive
  alignment.
- `pre/tests/test_reference_membership_join.py`: fits references from train
  Membership and deduplicated observations.
- `pre/tests/test_research_code_revision_required.py`: rejects Resume across a
  research revision change.
- `pre/tests/test_resume_counts_pass_empty_as_complete.py`: counts `PASS_EMPTY`
  as complete for both partitioned datasets.
- `pre/tests/test_staging_resume_contract.py`: requires exact hard Resume
  identity.
- `pre/tests/test_staging_resume_rejection.py`: rejects missing or incompatible
  staging manifests.
- `pre/tests/test_validator_accepts_pass_empty_without_file.py`: accepts valid
  empty manifest entries with no file.
- `pre/tests/test_validator_detects_statistics_mismatch.py`: recomputes and
  detects inconsistent stored statistics.
- `pre/tests/test_validator_rejects_unregistered_membership_file.py`: rejects
  Membership files absent from the manifest.
- `pre/tests/test_validator_rejects_unregistered_observation_file.py`: rejects
  Observation files absent from the manifest.

The full PRE test suite result for this implementation snapshot is 74 passed.
