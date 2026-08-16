# Tasks: Production Data and PRE

## Phase 1 - Source Contracts

- [X] T001 Write failing source registry/read-request/raw containment tests in `tests/contract/test_production_adapter_contract.py`
- [X] T002 Implement source adapter registry contracts in `model/PRE/adapters/registry.py`
- [X] T003 Publish audited source layouts in `registries/source_adapter_registry.yaml`

## Phase 2 - Canonical Readers

- [X] T004 [US1] Write failing canonical conversion/timezone/units tests in `tests/unit/test_canonical_conversion.py`
- [X] T005 [US1] Implement bounded streaming readers in `model/PRE/adapters/readers.py`
- [X] T006 [US1] Implement canonical normalization, timezone and units in `model/PRE/canonical/`
- [X] T007 [US1] Implement production data1/data2 adapters in `model/PRE/adapters/data1.py` and `model/PRE/adapters/data2.py`

## Phase 3 - Episode and PRE Publication

- [X] T008 [US2] Write failing episode chain and critical invalidation tests in `tests/unit/test_production_episode_builder.py`
- [X] T009 [US2] Implement deterministic episode construction in `model/PRE/episode/builder.py`
- [X] T010 [US3] Write failing real publication leakage/lineage/support tests in `tests/integration/test_production_pre.py`
- [X] T011 [US3] Implement evidence publication and production orchestration in `model/PRE/evidence/publication.py` and `model/PRE/pipeline.py`

## Phase 4 - Cache, Resume, and CLI

- [X] T012 [US4] Write failing cache manifest/resume tests in `tests/unit/test_pre_cache_resume.py`
- [X] T013 [US4] Implement Parquet/ZSTD canonical storage and manifest resume in `model/PRE/canonical/storage.py` and `model/PRE/cache/`
- [X] T014 [US4] Implement production PRE CLI in `model/PRE/cli.py`

## Phase 5 - Validation and Handoff

- [X] T015 Add bounded real-source smoke tests in `tests/real_smoke/test_real_source_smoke.py`
- [X] T016 Run synthetic and bounded real validation and record unresolved issues in `reports/production_pre/VALIDATION_SUMMARY.md`
