# Feature Specification: Production Data and PRE

**Feature**: 002 Production Data and PRE  
**Created**: 2026-08-12  
**Status**: Approved by implementation-cycle directive

## User Scenarios & Testing

### User Story 1 - Read audited raw sources without mutation (P1)

A researcher selects a registered data1 or data2 source and streams bounded records into canonical source objects while the raw tree remains byte-for-byte untouched.

**Independent Test**: Read a small real slice from each configured raw root, verify schema/unit/time conversions and confirm no raw-root write occurred.

### User Story 2 - Construct real predecessor-successor episodes (P1)

A researcher constructs deterministic same-aircraft chains with namespace-aware identities, time-ordered membership, connection-airport continuity, and explicit quality/support state.

**Independent Test**: Build episodes from real bounded flight records and reject duplicate, reversed, cross-aircraft, or airport-discontinuous pairs.

### User Story 3 - Publish decision-time PRE state (P1)

A downstream model requests rolling decision nodes and receives only episode-member evidence legally available by the cutoff, plus complete ledger, lineage, references, target support, and local abstentions.

**Independent Test**: A bounded real or synthetic episode publishes stable nodes; future/post-hoc rows never enter formal inputs and unsupported objects remain explicit.

### User Story 4 - Resume production canonicalization safely (P2)

A researcher can cache partitioned canonical output, resume completed partitions, and verify every artifact against a deterministic manifest without changing scientific semantics.

**Independent Test**: Interrupt and resume a bounded run, verify identical partition identities/manifests, and reject stale configuration or registry hashes.

## Edge Cases

- Archive members with schema drift, malformed timestamps, `2400`, DST ambiguity, cross-midnight arrival, cancellation, missing identity, duplicate observation, and equal-priority conflict.
- data1 records without position/motion and data2 fields that are post-hoc only.
- Missing frozen replay lag or weather age causes typed blocking, never a default.
- A single object may abstain while the decision node remains valid; critical identity/membership/time-boundary failures invalidate the node.

## Requirements

- **FR-001** Raw sources MUST be opened read-only and streamed/chunked; source files MUST never be modified, renamed, extracted permanently, or annotated.
- **FR-002** A versioned source-adapter registry MUST map each supported layout to schema, parser, canonical object, role, and rule identity.
- **FR-003** data1 readers MUST support OpenSky flightlist/state-vector archives, METAR, Eurostat, and OurAirports layouts defined by the audit.
- **FR-004** data2 readers MUST support BTS On-Time, DB1B, T-100, airport, and timezone reference layouts defined by the audit.
- **FR-005** Readers MUST project only registered columns and reject unregistered formal use.
- **FR-006** Canonical IDs MUST be deterministic and retain source identity fields and namespace.
- **FR-007** Canonical timestamps MUST be timezone-aware UTC; BTS local hhmm conversion MUST handle `2400`, rollover, DST, cancellation, and origin/destination timezones.
- **FR-008** Units MUST follow the authoritative canonical-unit registry; OpenSky altitude/vertical rate MUST not be converted from feet.
- **FR-009** METAR conversion MUST preserve missingness, distinguish QNH from unsupported MSLP, and perform only registered conversions.
- **FR-010** Actual BTS fields MUST remain post-hoc labels/outcomes until realization and MUST never enter earlier formal nodes.
- **FR-011** Episode construction MUST enforce same-aircraft, chronological, and airport-continuity membership with deterministic chain IDs.
- **FR-012** PRE MUST implement replay availability, latest-legal selection, freshness, conflict handling, support ceilings, and registered fallback only.
- **FR-013** PRE publication MUST include EpisodeRecord, DecisionNodeRecord, PREState, EvidenceLedger, VariableLineage, ReferenceState, and TargetSupportState.
- **FR-014** Dataset differences MUST be confined to adapters and capability profiles; PRE scientific logic MUST not branch on dataset name.
- **FR-015** Canonical caches MUST be project-owned Parquet/ZSTD partitions, never raw-root files, and avoid episode-level tiny-file partitioning.
- **FR-016** Cache/resume MUST use atomic partition commits and deterministic source/config/registry/manifests; mismatch MUST invalidate reuse explicitly.
- **FR-017** Small real-data smoke paths MUST be executable against configurable read-only roots and bounded by rows/files/date.
- **FR-018** Tests MUST cover schema drift, leakage, missingness, time conversion, lineage, support, cache identity, resume, and raw-root immutability.

## Key Entities

SourceAdapterDefinition, RawReadRequest, RawBatch, CanonicalPartition, CanonicalManifest, EpisodeRecord, DecisionNodeRecord, EvidenceLedgerEntry, VariableLineageEntry, PREState, PREPublicationManifest.

## Assumptions

- Current audited layouts are authoritative; additional layouts require registry amendments.
- Replay lag, weather maximum age, and categorical encodings remain explicit development-frozen values until separately frozen.
- Real smoke is bounded and diagnostic; full-year execution is not required for this feature gate.

## Success Criteria

- **SC-001** A bounded real slice from at least one data1 and one data2 source canonicalizes without raw-tree mutation.
- **SC-002** All formal PRE values have a ledger and lineage chain; zero unregistered fields reach formal state.
- **SC-003** Future and post-hoc leakage negative cases are rejected 100% of the time.
- **SC-004** Repeated/resumed bounded runs produce identical canonical and PRE manifest identities.
- **SC-005** Unsupported target/object cases publish explicit local abstention while supported siblings remain available.
