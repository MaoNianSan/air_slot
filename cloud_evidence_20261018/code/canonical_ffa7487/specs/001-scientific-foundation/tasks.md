---
description: "Dependency-ordered tasks for the Air Slot executable scientific foundation"
---

# Tasks: Executable Scientific Foundation

**Input**: Approved design documents in `specs/001-scientific-foundation/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Scope guard**: Implement only the clean project skeleton, shared contracts/registries, data1/data2
adapter interfaces, PRE skeleton, lineage/evidence foundation, and fixture-only validation. Do not
implement M1-M4 algorithms, production raw-data readers, experiments, legacy compatibility, or any
Git/GitHub operation.

**Runtime guard**: Use the current system/current Python 3.11.x interpreter directly. Declare all
dependencies only in `requirements.txt` and install with `python -m pip install -r requirements.txt`.
Do not create, activate, assume, bootstrap, locate, or record `.venv`, `venv`, virtualenv, Conda,
Poetry, or Pipenv environments; environment identity is not a project artifact.

**Tests**: Required by FR-018/FR-019. Within each phase, write the listed tests first and confirm they
fail for the intended missing behavior before implementing that behavior.

## Format: `[ID] [P?] [Story?] Description with exact file path`

- **[P]**: Can run in parallel because it changes different files and has no dependency on an
  incomplete task in the same phase.
- **[US1]...[US4]**: Maps the task to an approved user story.
- Setup, foundational, and final cross-cutting tasks intentionally have no story label.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the clean local Python project and empty architectural boundaries without
implementing scientific behavior.

- [X] T001 Create Python 3.11 project metadata in `pyproject.toml` and declare all minimal foundation dependency pins only in `requirements.txt`
- [X] T002 Create package initializers for the approved source layout in `model/__init__.py`, `model/common/__init__.py`, `model/PRE/__init__.py`, `validation/__init__.py`, and `exp/__init__.py`
- [X] T003 [P] Create explicit configuration-layer directories and explanatory templates in `configs/scientific/foundation.yaml`, `configs/reproducibility/smoke.yaml`, and `configs/engineering/local.example.yaml`
- [X] T004 [P] Create separated artifact-namespace documentation with no generated results in `outputs/runtime/README.md`, `outputs/formal/README.md`, `outputs/evaluation/README.md`, `outputs/paper_candidate/README.md`, and `outputs/manuscript_values/README.md`
- [X] T005 [P] Create fixture and read-only source-root documentation in `tests/fixtures/README.md` and `docs/datasets/README.md`
- [X] T006 Document the clean implementation, supported commands, authoritative document order, and prohibited legacy/Git/experiment scope in `README.md`

**Checkpoint**: The repository imports as an empty scientific foundation and contains no model or
experiment algorithm.

---

## Phase 2: Foundational Contracts (Blocking Prerequisites)

**Purpose**: Implement shared types, deterministic identity, explicit unsupported values, typed errors,
and configuration loading used by every user story.

**CRITICAL**: No user-story implementation begins until this phase passes.

- [X] T007 [P] Write failing enum and state-combination contract tests for availability, roles, evidence, support, freeze, operational stage, and artifact layer in `tests/contract/test_common_enums.py`
- [X] T008 [P] Write failing tests proving `UNSUPPORTED`/`ABSTAIN` require null values and reasons while observed zero remains distinguishable in `tests/contract/test_supported_value.py`
- [X] T009 [P] Write failing cross-platform canonical JSON and deterministic SHA-256 identity tests in `tests/unit/test_identity_serialization.py`
- [X] T010 Implement the canonical enums and ordering/validation helpers in `model/common/enums.py`
- [X] T011 [P] Implement stable typed error categories, including scope and not-implemented errors, in `model/common/errors.py`
- [X] T012 Implement immutable provenance, time-context, and supported-value envelopes with node/object ABSTAIN separation in `model/common/value_objects.py`
- [X] T013 Implement canonical JSON normalization and deterministic content hashing in `model/common/serialization.py` and `model/common/identity.py`
- [X] T014 [P] Write failing tests that reject implicit defaults for development-frozen scientific parameters and machine-specific scientific paths in `tests/contract/test_configuration_layers.py`
- [X] T015 Implement separate scientific, reproducibility, and engineering configuration models/loaders in `model/common/config.py`
- [X] T016 Run the Phase 2 tests and document the passing shared-contract checkpoint without scientific claims in `outputs/runtime/README.md`

**Checkpoint**: Shared contracts enforce explicit support semantics, deterministic identity, and no
silent scientific defaults.

---

## Phase 3: User Story 1 - Inspect the Scientific Contract (Priority: P1) - MVP

**Goal**: A researcher can load and inspect canonical contracts and versioned registries, trace every
initial scientific variable, and verify module boundaries without raw data.

**Independent Test**: Run registry/contract tests and trace at least one representative rule from each
audited source family to allowed consumers, with zero M4 raw dependencies and zero legacy references.

### Tests for User Story 1

- [X] T017 [P] [US1] Write failing schema tests for canonical source objects, episodes, decision nodes, evidence ledger entries, variable lineage, references, and target support in `tests/contract/test_foundation_models.py`
- [X] T018 [P] [US1] Write failing registry-schema and unknown-key tests for all required scientific fields in `tests/contract/test_registry_schemas.py`
- [X] T019 [P] [US1] Write failing referential-integrity, support-ceiling, cycle, and manifest-hash tests in `tests/contract/test_registry_integrity.py`
- [X] T020 [P] [US1] Write failing static tests for forbidden experiment-to-model, raw-to-M1-M4, M3-to-M2-scenario, and M4-raw dependencies in `tests/static/test_dependency_boundaries.py`

### Implementation for User Story 1

- [X] T021 [P] [US1] Implement immutable canonical flight, operational-event, trajectory, weather, aggregate-reference, and airport-reference contracts in `model/PRE/contracts/canonical.py`
- [X] T022 [P] [US1] Implement EpisodeRecord, DecisionNodeRecord, EvidenceLedgerEntry, VariableLineageEntry, ReferenceState, TargetSupportState, and PREState contracts in `model/PRE/contracts/pre_state.py`
- [X] T023 [P] [US1] Implement validated data-usage, scientific-variable, capability, source-priority, and registry-manifest models in `model/PRE/feature_registry/models.py`
- [X] T024 [US1] Implement strict YAML registry loading, referential integrity, cycle detection, consumer-boundary validation, and manifest hashing in `model/PRE/feature_registry/loader.py`
- [X] T025 [P] [US1] Curate the audited raw-to-canonical permissions and explicit unsupported rules in `registries/data_usage_rules.yaml`
- [X] T026 [P] [US1] Curate initial PRE scientific variables with separate data1/data2 formal and realized support in `registries/scientific_variables.yaml`
- [X] T027 [P] [US1] Curate independent data1/data2 support ceilings and disabled cross-dataset overlay in `registries/dataset_capabilities.yaml`
- [X] T028 [P] [US1] Define deterministic equal-time source priorities and conflict-abstention policy in `registries/source_priority.yaml`
- [X] T029 [US1] Generate and validate the combined registry identity in `registries/registry_manifest.json`
- [X] T030 [P] [US1] Document M1, M2, M3, and M4 as non-executable boundaries, including the confirmed M3/M4 split, in `model/M1/README.md`, `model/M2/README.md`, `model/M3/README.md`, and `model/M4/README.md`
- [X] T031 [P] [US1] Document exp1-exp4 as evaluation placeholders with no runners or outputs in `exp/README.md`, `exp/exp1/README.md`, `exp/exp2/README.md`, `exp/exp3/README.md`, and `exp/exp4/README.md`
- [X] T032 [US1] Implement a read-only lineage/registry inspection service that returns source-to-consumer chains in `model/PRE/feature_registry/inspection.py`
- [X] T033 [US1] Add an end-to-end registry trace test covering every audited data1/data2 source family in `tests/integration/test_registry_lineage_trace.py`

**Checkpoint**: US1 is independently usable as a no-raw-data contract/registry inspection MVP.

---

## Phase 4: User Story 2 - Adapt Independent Dataset Evidence (Priority: P2)

**Goal**: data1 and data2 expose one common adapter protocol, independent capability profiles, and
source-interface declarations without production readers, physical fusion, or hidden fallback.

**Independent Test**: Instantiate both interface skeletons without raw data, inspect all declared source
families and unsupported ceilings, and verify that production iteration is explicitly unavailable by
scope rather than silently delegated or fabricated.

### Tests for User Story 2

- [X] T034 [P] [US2] Write failing protocol tests for `describe`, `capabilities`, `validate_source`, and `iter_canonical` interface signatures in `tests/contract/test_adapter_protocol.py`
- [X] T035 [P] [US2] Write failing capability tests for data1 QNH/MSLP, schedule, 2019 aircraft metadata, and passenger-reference ceilings in `tests/contract/test_data1_adapter_interface.py`
- [X] T036 [P] [US2] Write failing capability tests for data2 post-hoc events, aggregate passengers, unverified aircraft type, and unsupported real-time state in `tests/contract/test_data2_adapter_interface.py`
- [X] T037 [P] [US2] Write failing tests that reject pooled instance IDs, implicit overlays, adapter fallback, and cross-dataset row concatenation in `tests/contract/test_dataset_independence.py`

### Implementation for User Story 2

- [X] T038 [US2] Implement the dataset-neutral adapter protocol, source-validation request/report types, and explicit production-reader-not-implemented behavior in `model/PRE/adapters/base.py`
- [X] T039 [P] [US2] Implement the data1 interface skeleton and audited source-family/capability declarations without raw readers in `model/PRE/adapters/data1.py`
- [X] T040 [P] [US2] Implement the data2 interface skeleton and audited source-family/capability declarations without raw readers in `model/PRE/adapters/data2.py`
- [X] T041 [P] [US2] Publish the trajectory-rich independent instance profile with explicit unsupported objects in `metadata/datasets/data1/dataset_profile.yaml`
- [X] T042 [P] [US2] Publish the event-rich post-hoc independent instance profile with explicit unsupported objects in `metadata/datasets/data2/dataset_profile.yaml`
- [X] T043 [US2] Implement adapter-interface/profile conformance validation with no raw-data scan in `model/PRE/adapters/validation.py`
- [X] T044 [US2] Add an integration test proving both interface skeletons load together but remain independent and non-fallback in `tests/integration/test_adapter_interfaces.py`

**Checkpoint**: US2 independently proves adapter portability at the interface/capability level only;
production parsing and canonical-cache generation remain `NOT_IMPLEMENTED_BY_SCOPE`.

---

## Phase 5: User Story 3 - Construct a PRE Decision State (Priority: P3)

**Goal**: A fixture-driven PRE skeleton constructs an immutable, support-aware decision node using
membership, time admissibility, latest-legal selection, and explicit object-level abstention.

**Independent Test**: Build a synthetic episode node containing legal, future, non-member, conflicting,
unsupported, and development-frozen objects; supported objects publish while object-specific ABSTAIN
does not invalidate the node.

### Tests for User Story 3

- [X] T045 [P] [US3] Write failing episode membership tests for predecessor-successor identity and non-member rejection in `tests/unit/test_episode_membership.py`
- [X] T046 [P] [US3] Write failing availability and latest-legal-observation tests, including unknown replay lag and future evidence, in `tests/unit/test_admissibility.py`
- [X] T047 [P] [US3] Write failing support-monotonicity, unsupported-null, observed-zero, and unregistered-fallback tests in `tests/unit/test_support_propagation.py`
- [X] T048 [P] [US3] Write failing tests reserving DecisionNodeRecord `ABSTAINED` for node-level invalidation while data1 `R_OB` object ABSTAIN preserves other outputs in `tests/unit/test_node_object_abstention.py`
- [X] T049 [P] [US3] Write failing immutable node-identity and later-evidence non-retrospective tests in `tests/unit/test_decision_node_identity.py`

### Implementation for User Story 3

- [X] T050 [P] [US3] Implement episode membership predicates and chain-rule validation in `model/PRE/episode/membership.py`
- [X] T051 [P] [US3] Implement availability predicates, latest-legal selection, registered source-priority handling, and equal-priority conflict detection in `model/PRE/evidence/admissibility.py`
- [X] T052 [P] [US3] Implement support ceilings, monotone transformation checks, explicit fallback permission, and object-specific abstention in `model/PRE/evidence/support.py`
- [X] T053 [US3] Implement immutable decision-node construction and node-level invalidation rules in `model/PRE/episode/node_builder.py`
- [X] T054 [US3] Implement the PREBuildRequest/PREBuildResult orchestration surface without M1-M4 behavior in `model/PRE/foundation.py`
- [X] T055 [P] [US3] Create deterministic synthetic canonical records and mixed-support episode fixtures in `tests/fixtures/pre/foundation_cases.py`
- [X] T056 [US3] Add an end-to-end PRE fixture test for evidence ledger, lineage, references, target support, and partial publication in `tests/integration/test_pre_foundation.py`
- [X] T057 [US3] Document PRE skeleton responsibilities, node/object ABSTAIN semantics, and deferred scientific parameters in `model/PRE/README.md`

**Checkpoint**: US3 independently constructs fixture-only PRE states. It does not train, predict,
calculate consequences, instantiate actions, or rank decisions.

---

## Phase 6: User Story 4 - Validate the Foundation (Priority: P4)

**Goal**: A reviewer can run fast deterministic fixture-only checks with typed findings, stable exit
codes, separated outputs, and only the approved fixture metadata allowlist.

**Independent Test**: Run `python -m validation.cli all --fixtures-only` twice; both runs reject every
negative fixture, produce identical formal fixture bytes/hashes, finish under 60 seconds, and report
only `FIXTURE_ONLY`, `paper_result = false`, and `evaluation_scope = FOUNDATION_ONLY` metadata.

### Tests for User Story 4

- [X] T058 [P] [US4] Write failing ValidationFinding/ValidationRun schema, fixture metadata allowlist, and exit-code tests in `tests/contract/test_validation_reporting.py`
- [X] T059 [P] [US4] Write failing negative tests for leakage, non-membership, silent zero, support upgrade, raw downstream access, dataset mixing, and prohibited scope in `tests/integration/test_negative_boundaries.py`
- [X] T060 [P] [US4] Write failing repeated-run byte/hash determinism tests for formal PRE fixtures in `tests/integration/test_fixture_reproducibility.py`
- [X] T061 [P] [US4] Write failing artifact-layer tests preventing fixture/runtime files from entering evaluation, paper-candidate, or manuscript namespaces in `tests/integration/test_output_separation.py`

### Implementation for User Story 4

- [X] T062 [P] [US4] Implement static dependency and prohibited-token checks in `validation/dependency_rules.py`
- [X] T063 [P] [US4] Implement ValidationFinding/ValidationRun serialization, summary counts, and fixture-only metadata in `validation/reporting.py`
- [X] T064 [US4] Implement registry, adapter-interface, PRE-fixture, dependency, and determinism check orchestration in `validation/foundation.py`
- [X] T065 [US4] Implement the `contracts`, `adapters`, `pre`, and `all --fixtures-only` command surface and stable exit codes in `validation/cli.py`
- [X] T066 [US4] Add the full offline validation integration test and 60-second CPU-only budget assertion in `tests/integration/test_validation_cli.py`

**Checkpoint**: US4 provides engineering validation only. It emits no experiment metric, paper result,
or scientific conclusion.

---

## Phase 7: Polish and Cross-Cutting Validation

**Purpose**: Reconcile documentation, dependencies, portability, and the approved quickstart without
expanding implementation scope.

- [X] T067 [P] Synchronize exact runtime dependency pins only in `requirements.txt` and Python 3.11 project classifiers in `pyproject.toml`
- [X] T068 [P] Add Windows/Linux path, UTC, UTF-8, and canonical-serialization portability tests in `tests/integration/test_platform_portability.py`
- [X] T069 Audit all project Python and YAML files for legacy identifiers, hard-coded machine paths, silent fallback, unregistered raw consumers, unapproved fixture metadata, and virtual-environment assumptions in `validation/dependency_rules.py`
- [X] T070 Run every command in `specs/001-scientific-foundation/quickstart.md` and record only foundation engineering evidence in `outputs/runtime/foundation_validation/validation_result.json`
- [X] T071 Verify formal fixture artifacts contain exactly `FIXTURE_ONLY = true`, `paper_result = false`, and `evaluation_scope = FOUNDATION_ONLY` status metadata in `tests/integration/test_output_separation.py`
- [X] T072 Produce the milestone handoff with created files, implemented contracts, unresolved scientific assumptions, resolved conflicts, executed checks, and next authorized step in `reports/foundation/IMPLEMENTATION_STATUS.md`
- [X] T073 Re-run the complete offline test suite, confirm no M1-M4/experiment/production-reader/Git behavior was added, and record the final engineering result in `reports/foundation/VALIDATION_SUMMARY.md`

---

## Dependencies and Execution Order

### Phase Dependencies

```text
Phase 1 Setup
    -> Phase 2 Foundational Contracts
        -> Phase 3 US1 Contract Inspection (MVP)
            -> Phase 4 US2 Adapter Interfaces
            -> Phase 5 US3 PRE Decision State
                -> Phase 6 US4 Foundation Validation
                    -> Phase 7 Polish and Handoff
```

- **Phase 1** has no implementation dependency.
- **Phase 2** depends on Phase 1 and blocks all user stories.
- **US1** depends on Phase 2 because registries and canonical contracts define all later interfaces.
- **US2** depends on US1 registry/capability schemas but does not depend on PRE node construction.
- **US3** depends on US1 contracts/registries. Its fixture provider may implement the adapter protocol
  directly, so production adapter behavior is not required; completing US2 first is the preferred
  sequential route for full interface integration.
- **US4** depends on US1 and US3 and incorporates US2 interface checks when US2 is included.
- **Phase 7** depends on all four stories selected for this milestone.

### Within-Story Ordering

- Write and run story tests first; confirm failure is caused by missing intended behavior.
- Implement models before loaders/services; loaders before integration validation.
- Registry files precede manifest generation.
- PRE membership/admissibility/support components precede node orchestration.
- Validation result/report models precede CLI orchestration.

### User Story Independence

- **US1**: Fully testable with registries only; no raw data, adapter implementation, or PRE build needed.
- **US2**: Fully testable as two interface/capability skeletons; no production readers or PRE node needed.
- **US3**: Fully testable with canonical synthetic fixtures; no production data1/data2 reader needed.
- **US4**: Fully testable offline from completed selected story fixtures; it never invokes M1-M4 or an
  experiment.

## Parallel Opportunities

- T003-T005 can proceed in parallel after T001-T002 establish naming.
- T007-T009 and T014 can be authored in parallel before the corresponding shared implementation.
- T017-T020 can be authored in parallel; T021-T023 and T025-T028 affect distinct files and can proceed
  in parallel after shared contracts pass.
- T034-T037 can be authored in parallel; T039-T042 are independent data1/data2 interface/profile files.
- T045-T049 can be authored in parallel; T050-T052 and T055 affect distinct PRE components/fixtures.
- T058-T061 can be authored in parallel; T062-T063 are independent validation components.
- No two tasks that modify the same file are marked parallel.

### Parallel Example: US1

```text
T021: canonical source contracts in model/PRE/contracts/canonical.py
T023: registry models in model/PRE/feature_registry/models.py
T025: data-use rules in registries/data_usage_rules.yaml
T026: scientific variables in registries/scientific_variables.yaml
T027: dataset capabilities in registries/dataset_capabilities.yaml
T028: source priorities in registries/source_priority.yaml
```

### Parallel Example: US2

```text
T039: data1 interface skeleton in model/PRE/adapters/data1.py
T040: data2 interface skeleton in model/PRE/adapters/data2.py
T041: data1 profile in metadata/datasets/data1/dataset_profile.yaml
T042: data2 profile in metadata/datasets/data2/dataset_profile.yaml
```

### Parallel Example: US3

```text
T050: membership in model/PRE/episode/membership.py
T051: admissibility in model/PRE/evidence/admissibility.py
T052: support propagation in model/PRE/evidence/support.py
T055: synthetic fixtures in tests/fixtures/pre/foundation_cases.py
```

## Implementation Strategy

### MVP First: US1 Contract Inspection

1. Complete Phase 1 and Phase 2.
2. Complete US1 through T033.
3. Stop and validate registry inspection independently.
4. Report only engineering readiness for the contract/registry MVP.

### Incremental Foundation

1. Add US2 to prove independent adapter interfaces without production readers.
2. Add US3 to prove support-aware PRE construction with synthetic canonical fixtures.
3. Add US4 to expose the unified offline validation interface.
4. Complete Phase 7 and stop before any downstream algorithm or experiment work.

### Hard Stop Boundaries

- Do not add M1 model, loss, calibration, inference, or scenario code.
- Do not add M2 consequence, M3 action/effect, or M4 lane/risk/ranking code.
- Do not add experiment runners, LLM calls, metrics, figures, tables, or results.
- Do not implement production raw readers or scan/copy full data in this feature.
- Do not import legacy code or preserve legacy compatibility.
- Do not initialize Git, create branches/commits, or communicate with GitHub.
- Do not create or activate any virtual/Conda-style environment or record its identity.
- Do not convert fixture validation into a scientific conclusion or paper claim.

## Completion Definition

- All selected tasks are `[X]` and their listed tests pass.
- Each story passes its independent test criteria.
- Foundation validation remains offline, fixture-only, deterministic, and under 60 seconds.
- Object-specific ABSTAIN preserves other supported node outputs; node `ABSTAINED` remains node-level.
- Fixture status metadata is restricted to `FIXTURE_ONLY`, `paper_result`, and optional
  `evaluation_scope = FOUNDATION_ONLY`.
- No work outside the approved foundation scope appears in the source tree.
