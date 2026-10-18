# Feature Specification: Executable Scientific Foundation

**Feature Branch**: `none (non-Git workspace)`

**Created**: 2026-08-12

**Status**: Approved (2026-08-12)

**Input**: Build the first Air Slot milestone as a clean implementation: project skeleton, initial
contracts and registries, data-adapter interfaces, PRE skeleton, and validation tests. Do not yet
implement M1-M4.

## User Scenarios & Testing

### User Story 1 - Inspect the Scientific Contract (Priority: P1)

As an Air Slot researcher, I can inspect a single executable project structure and machine-readable
registries that state what each dataset may contribute, how evidence is classified, and which module
may consume each scientific variable.

**Why this priority**: Every later model result depends on stable evidence, lineage, and module
boundaries. A runnable model built before these contracts would not be scientifically auditable.

**Independent Test**: Load every registry and contract without raw data, validate all identifiers and
references, and trace representative data1 and data2 variables from source object to allowed consumer.

**Acceptance Scenarios**:

1. **Given** the clean repository, **When** a researcher lists its formal packages, **Then** PRE,
   M1-M4 placeholders, experiments, data-instance metadata, configuration, and tests are visibly
   separated according to the frozen architecture.
2. **Given** a registered scientific variable, **When** its lineage is queried, **Then** the raw source,
   adapter rule, PRE transformation, evidence class, support ceiling, and downstream consumers are
   returned without relying on legacy code.
3. **Given** a formal/evaluation boundary audit, **When** dependencies are inspected, **Then** model
   packages do not depend on experiments and evaluation-only objects are absent from formal contracts.

---

### User Story 2 - Adapt Independent Dataset Evidence (Priority: P2)

As a data-methods researcher, I can implement and exercise data1 and data2 through one adapter
protocol while preserving their independent evidence environments, time semantics, and unsupported
objects.

**Why this priority**: The same framework must operate across trajectory-rich rolling evidence and
event-rich post-hoc evidence without physical fusion or fabricated parity.

**Independent Test**: Feed small in-memory representative records to each adapter, verify canonical
objects and availability roles, and confirm structurally absent fields return explicit unsupported
states rather than substitute values.

**Acceptance Scenarios**:

1. **Given** a valid data1 weather observation, **When** it is adapted, **Then** canonical units,
   observation time, source provenance, missingness, and QNH-derived semantics are preserved, with QNH
   never relabeled as mean sea-level pressure.
2. **Given** data2 realized flight events, **When** they are adapted before realization, **Then** they
   are available only for training/evaluation and cannot become decision-time inference evidence.
3. **Given** an object absent from a dataset, **When** its adapter capability is queried, **Then** the
   result is `UNSUPPORTED` or object-specific `ABSTAIN`, never zero or an undisclosed proxy.
4. **Given** both adapters in one run configuration, **When** instance validation executes, **Then**
   their rows remain separate and no pooled training dataset is silently produced.

---

### User Story 3 - Construct a PRE Decision State (Priority: P3)

As a model developer, I can pass canonical records, an episode identity, and a decision time through a
PRE skeleton that enforces membership and latest-legal-observation rules and publishes an auditable
support-aware information state.

**Why this priority**: M1 is permitted to consume PRE outputs only, so PRE must expose a trustworthy
contract before predictive code begins.

**Independent Test**: Construct a synthetic episode with observations before, at, and after a decision
time, then verify that only legal episode members are selected and every output includes support and
lineage.

**Acceptance Scenarios**:

1. **Given** records inside and outside the episode and on both sides of decision time, **When** PRE
   constructs a node, **Then** it includes only records satisfying membership and availability.
2. **Given** multiple legal observations for a dynamic variable, **When** PRE constructs a node,
   **Then** it selects the latest legal event and records its age and provenance.
3. **Given** stale, weak, or missing evidence, **When** PRE evaluates object-specific support, **Then**
   it follows the declared fallback or abstention rule without support inflation.
4. **Given** a constructed historical decision node, **When** later evidence arrives, **Then** a new
   node may differ but the earlier node and its identity remain non-retrospective and unchanged.

---

### User Story 4 - Validate the Foundation (Priority: P4)

As a scientific reviewer, I can run fast deterministic checks that prove contract loading, dependency
direction, evidence monotonicity, time admissibility, unsupported propagation, and reproducibility.

**Why this priority**: The first milestone is complete only when failures in evidence discipline are
detectable before model development.

**Independent Test**: Run the foundation test suite against only generated fixtures and receive a
machine-readable validation summary with no access to full raw datasets.

**Acceptance Scenarios**:

1. **Given** deliberately leaked future evidence, **When** validation runs, **Then** the node is rejected
   with a stable error category and actionable context.
2. **Given** a transformation that attempts to upgrade proxy or unsupported evidence, **When** support
   validation runs, **Then** it fails.
3. **Given** the same fixture, configuration, and seed, **When** validation runs twice, **Then** formal
   serialized outputs and identity hashes match.
4. **Given** a clean environment without raw datasets, **When** smoke validation runs, **Then** all
   contract and PRE-skeleton tests complete using fixtures only.

### Edge Cases

- A source event time exists but its availability time is absent; the dataset rule must identify the
  approved assumption or make the object unavailable rather than infer availability silently.
- An observation has legal time but fails episode membership, or legal membership but future
  availability; either condition excludes it.
- Equal-timestamp observations conflict; deterministic source priority and a conflict flag are required.
- A field is present but stale, malformed, out of canonical-unit range, or has unverified semantics;
  presence alone cannot imply support.
- A proxy/reference is transformed multiple times; its support ceiling remains bounded by upstream
  evidence.
- data1 lacks schedule support for a target such as `R_OB`; the target abstains rather than being
  redefined from trajectory data.
- data2 has realized `DepTime`, `ArrTime`, `WheelsOff`, or `TaxiOut`; these remain post-hoc until their
  event-specific realization conditions are satisfied.
- Weather `gust`, cloud, and present-weather codes can be absent by reporting semantics; missingness is
  represented explicitly and is not automatically a zero-valued physical state.
- No raw data path is configured; registry and fixture validation still works, while data scans fail
  early with a specific configuration error.

## Requirements

### Functional Requirements

- **FR-001**: The repository MUST provide the `model/PRE`, `model/M1`, `model/M2`, `model/M3`,
  `model/M4`, `model/common`, `exp/exp1`-`exp/exp4`, `data1`, `data2`, `configs`, and `tests` boundaries
  without importing or recreating legacy implementation structures.
- **FR-002**: M1-M4 in this milestone MUST be explicit contract placeholders only; no prediction,
  consequence valuation, action-effect estimation, or ranking implementation is in scope.
- **FR-003**: The foundation MUST define canonical source-object, episode, decision-node, evidence,
  support, reference, lineage, and variable-registry contracts with validation rules.
- **FR-004**: Evidence classifications MUST distinguish direct, derived, proxy/reference,
  unsupported, and evaluation-only roles; support outcomes MUST distinguish supported, degraded, and
  abstain states.
- **FR-005**: Every scientific variable MUST declare source rules, canonical unit, decision-time role,
  availability basis, evidence class, support ceiling, fallback/abstention behavior, and formal or
  evaluation consumers.
- **FR-006**: The adapter protocol MUST emit canonical objects and declared capability profiles; it
  MUST NOT expose raw dataset rows directly to M1-M4.
- **FR-007**: The data1 adapter foundation MUST cover the audited trajectory, flight-history, METAR,
  Eurostat, and airport-reference source families while preserving proxy, archive, and replay limits.
- **FR-008**: The data2 adapter foundation MUST cover BTS On-Time, DB1B, T-100, and timezone-reference
  source families while keeping realized operational fields post-hoc and aggregate passenger data proxy.
- **FR-009**: Dataset instances MUST remain physically and statistically independent by default; any
  cross-dataset reference overlay MUST be disabled unless separately specified with grain, period,
  join key, provenance, evidence class, and support ceiling.
- **FR-010**: PRE MUST enforce `availability_time <= decision_time` and episode membership before a
  record can contribute to an information state.
- **FR-011**: PRE MUST select the latest legal observation for dynamic variables and publish observation
  age, missing/stale flags, provenance, lineage, and object-specific support.
- **FR-012**: PRE MUST preserve non-retrospective decision-node identity: later observations can create
  new nodes but cannot rewrite an existing formal node.
- **FR-013**: Missing, unsupported, stale, malformed, and unverified objects MUST have explicit failure,
  degradation, fallback, or abstention behavior; none may be silently zero-filled or proxied.
- **FR-014**: Support propagation MUST be monotone: a transformation cannot exceed the declared
  upstream support ceiling without a registered external evidence source.
- **FR-015**: The project MUST load scientific, reproducibility, and engineering configuration layers
  separately and record their resolved values and content identity.
- **FR-016**: Raw inputs MUST be treated as read-only and paths MUST be supplied through configuration;
  scientific code MUST contain no machine-specific absolute path.
- **FR-017**: Runtime, formal, evaluation, paper-candidate, and manuscript-value artifact namespaces
  MUST be distinct even though only foundation validation artifacts are produced in this milestone.
- **FR-018**: Tests MUST cover contract serialization, registry integrity, adapter capability behavior,
  time and membership admissibility, latest-legal selection, support monotonicity, unsupported
  propagation, deterministic identity, and forbidden dependency directions.
- **FR-019**: Validation MUST run without full raw data by using small synthetic fixtures and MUST emit
  a human-readable summary plus machine-readable status.
- **FR-020**: Conflicts between authoritative documents MUST be recorded and resolved by priority. The
  known framework/roadmap M3-input conflict MUST resolve in favor of the roadmap: M3 consumes PRE state
  and a frozen action registry, while M4 joins M1/M2/M3.
- **FR-021**: The following development-frozen or unresolved items MUST remain visible and MUST NOT be
  guessed by implementation: exact replay availability assumptions, weather maximum age, categorical
  cloud/weather encoding, T-100 aircraft-type semantics, and future data2 weather expansion.
- **FR-022**: The foundation MUST run on supported Windows and Linux environments with equivalent
  scientific semantics.
- **FR-023**: The project MUST use the current system/current Python 3.11.x interpreter directly and
  manage dependencies only through `requirements.txt`; it MUST NOT create, require, assume, activate,
  bootstrap, identify, or record a virtualenv, `.venv`, `venv`, Conda, Poetry, or Pipenv environment.
  Runtime metadata is limited to Python version, package versions, platform, and device.

### Key Entities

- **Dataset Instance**: An independent configured evidence environment such as `data1_2019` or
  `data2_2019`, including source capabilities and support ceilings.
- **Canonical Source Object**: A dataset-neutral flight, event, trajectory, weather, or aggregate
  reference record with canonical identity, UTC time, units, provenance, and availability role.
- **Episode Record**: A predecessor-successor pair and membership boundary used as the empirical unit.
- **Decision Node**: An immutable episode state at one decision time, identified by its inputs,
  configuration, registry versions, and legal evidence.
- **Evidence Ledger Entry**: The admissibility, class, support, provenance, age, missingness, and flags
  for one evidence object at one node.
- **Variable Lineage Entry**: The raw-source-to-adapter-to-PRE-to-scientific-variable-to-consumer chain.
- **Data Usage Rule**: A machine-readable permission and transformation rule for a source field/object.
- **Scientific Variable Definition**: The canonical semantics, unit, role, support ceiling, and consumers
  for a model-facing variable.
- **Dataset Capability Profile**: The supported, degraded, unsupported, proxy, and evaluation-only
  capabilities of one adapter/dataset instance.
- **Validation Result**: A deterministic finding with check identifier, status, severity, evidence, and
  optional remediation message.

## Success Criteria

### Measurable Outcomes

- **SC-001**: One command validates 100% of shipped contracts and registries without accessing full raw
  data and returns a nonzero status for any schema, reference, or support inconsistency.
- **SC-002**: At least one representative source object from every audited data1 and data2 source family
  can be traced through a complete machine-readable lineage to its permitted consumers.
- **SC-003**: The negative test set rejects 100% of included future-leakage, non-member evidence,
  unsupported-zero, support-upgrade, raw-to-downstream, and cross-dataset-pooling fixtures.
- **SC-004**: Repeating the fixture validation with identical configuration and seed produces byte-stable
  formal fixture artifacts and identical content hashes.
- **SC-005**: All foundation unit and contract tests complete in under 60 seconds on a supported CPU-only
  development machine without network access or full-dataset extraction.
- **SC-006**: Every formal scientific variable shipped in the initial registry has all required lineage,
  availability, evidence, support, fallback, unit, and consumer fields populated; there are zero silent
  defaults for scientific semantics.
- **SC-007**: Static dependency validation finds zero imports from experiments into model logic, zero raw
  dataset imports in M1-M4, and zero evaluation-only types in formal output contracts.
- **SC-008**: A reviewer can identify every unresolved scientific assumption and every document conflict
  from generated status artifacts without reading source code.

## Assumptions

- This feature is the first milestone named in the implementation brief; complete M1-M4 and Experiments
  1-4 are deferred features.
- The supplied `mission.md`, `roadmap.md`, `tech-stack.md`, `framework.txt`, data-audit archive, and
  manuscript PDF are read-only source materials; generated code and Spec Kit artifacts live only in
  `D:/Local_Projects/airslot`.
- The manuscript is used for notation and theoretical context only and cannot override higher-priority
  documents.
- The current workspace is intentionally non-Git; this workflow creates no branch, commit, push, or
  publication side effect.
- Full raw datasets are not copied into the repository. Adapter implementation uses configured paths,
  read-only access, streaming/chunked readers, and small test fixtures.
- Dependency installation, when implementation is later authorized, uses the current interpreter via
  `python -m pip install -r requirements.txt` with no environment creation or activation step.
- Development-frozen parameters are represented as explicit configuration/status values and block any
  affected formal interpretation until frozen by a later approved specification.

## Out of Scope

- Training, calibration, or inference for M1.
- M2 consequence computation, M3 candidate/effect computation, and M4 residual-risk ranking.
- Full raw-data extraction, mutation, repair, or permanent duplication.
- Fast, middle, full, paper-candidate, promotion, or manuscript-result runs.
- Empirical claims, cross-dataset accuracy comparisons, causal recovery-effect claims, or scientific
  PASS declarations.
- Legacy compatibility, legacy outputs, old CLI or run-ID support, and reconstruction of removed code.
- Git initialization, branching, staging, commits, pushes, or any GitHub operation.
