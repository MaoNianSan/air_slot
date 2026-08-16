# Research Decisions: Executable Scientific Foundation

**Feature**: [spec.md](spec.md)  
**Date**: 2026-08-12  
**Authority order**: mission > roadmap > tech-stack > framework > data audit > manuscript

## Decision 1: Treat this workspace as a clean implementation

**Decision**: Use only the supplied current documents and audited data semantics. Do not inspect,
import, port, or preserve earlier implementation code, folder layouts, CLIs, schemas, outputs, or run
identities.

**Rationale**: The implementation brief and mission explicitly define a new scientific implementation.
Historical engineering status is not scientific authority and cannot validate this feature.

**Alternatives considered**: Port the earlier PRE/M1 code; wrap legacy artifacts behind compatibility
interfaces. Rejected because both would reverse the source-of-truth order and introduce hidden semantics.

## Decision 2: Use Python 3.11 and a minimal foundation dependency set

**Decision**: Use Python 3.11.x, Pydantic 2.x, PyYAML, and pytest. Admit pandas/pyarrow only at the
adapter/canonical-storage edge if an implementation task needs fixture-level tables. Do not install or
exercise model-training packages for this milestone. Use the current system/current Python interpreter
directly, declare dependencies only in `requirements.txt`, and install them with
`python -m pip install -r requirements.txt`. Do not create, activate, assume, bootstrap, or identify a
virtualenv, `.venv`, `venv`, Conda, Poetry, or Pipenv environment.

**Rationale**: This matches the frozen runtime and provides strict validation, portable serialization,
and simple testing without implying M1-M4 implementation.

**Alternatives considered**: Plain dictionaries; a database schema; a distributed data framework;
installing the complete future modeling stack now; creating a project-specific virtual environment.
Rejected because they either weaken contract validation, add scope and complexity without foundation
value, or violate the approved direct-interpreter runtime contract.

## Decision 3: Use typed immutable contracts plus canonical JSON identity

**Decision**: Contract instances are immutable after validation. Persistent identity is SHA-256 over
UTF-8 canonical JSON with sorted keys, normalized UTC timestamps, explicit enum values, and no
non-semantic runtime metadata. Record both schema version and registry-manifest hash.

**Rationale**: Non-retrospective decision nodes and byte-stable fixture outputs require deterministic
identity independent of row order, worker count, or platform path syntax.

**Alternatives considered**: DataFrame row index, random UUID, pickle, or hash of Python object repr.
Rejected because these are unstable, opaque, unsafe, or platform-dependent.

## Decision 4: Unsupported is a structural state, not a value

**Decision**: A scientific datum is an envelope containing optional value plus evidence/support state.
`UNSUPPORTED` and `ABSTAIN` require `value = null` and a reason code. A zero may appear only when it is
an observed/derived scientific zero with normal provenance; it is never a missing-value sentinel.

**Rationale**: This makes silent fallback and support inflation schema-invalid rather than merely
discouraged.

**Alternatives considered**: NaN, zero, empty string, or dataset-specific sentinel. Rejected because a
sentinel does not encode scientific reason, support ceiling, or downstream permission.

## Decision 5: Keep availability, role, evidence, and support orthogonal

**Decision**: Every evidence-bearing object records `availability_basis`, `decision_time_role`,
`evidence_class`, `support_ceiling`, and episode-object `support_state` separately.

**Rationale**: A post-hoc direct event can be high-quality realized evidence yet unavailable for formal
inference; a derived variable can still be supported within its declared semantics. Collapsing these
dimensions would recreate leakage and support-upgrade bugs.

**Alternatives considered**: One combined quality enum. Rejected because it cannot distinguish temporal
admissibility from evidential sufficiency or realized-outcome support.

## Decision 6: Preserve development-frozen values as blockers

**Decision**: Exact replay lag, weather maximum age, cloud/weather encoding, trajectory thresholds,
episode gap limits, M1 finite supports, M2 valuation, and M3 response parameters remain explicitly
`DEVELOPMENT_FROZEN` with no implicit default. An affected formal object must abstain or remain
ineligible until an approved later specification freezes the value.

**Rationale**: The data audit's candidate value (for example a suggested 120-minute weather age) is not
the higher-priority tech stack's frozen scientific constant.

**Alternatives considered**: Adopt audit suggestions as defaults; use common industry values silently.
Rejected because either action would turn a draft recommendation into an unapproved scientific choice.

## Decision 7: Define one adapter protocol and two independent profiles

**Decision**: `data1_2019` and `data2_2019` implement a common `DatasetAdapter` protocol and publish
separate capability profiles. Adapters perform raw reading, source validation, parsing, unit/time/ID
normalization, raw-to-canonical mapping, and source flags only. They do not construct M1 targets or
redesign downstream science.

**Rationale**: Portability is demonstrated by unchanged scientific contracts under different evidence
ceilings, not by pooling rows or forcing identical target coverage.

**Alternatives considered**: One merged adapter; a common superset row filled with zeros; separate
dataset-specific M1-M4 code. Rejected by the one-model/multiple-instances principle.

## Decision 8: Constrain the data1 interface to audited semantics

**Decision**: Cover OpenSky state vectors and flight history, METAR, Eurostat, and OurAirports as
source-family interfaces. Preserve trajectory events as derived proxies; QNH parsed from METAR as
derived and distinct from unsupported MSLP; airport flow as an observed-subset proxy; 2019 schedule and
aircraft metadata as unsupported; passenger exposure as reference-only.

**Rationale**: These are the verified capability ceilings. Field presence or a later snapshot cannot
raise the evidence class.

**Alternatives considered**: Infer schedule from `firstseen/lastseen`; backfill 2019 aircraft metadata
from 2022; call QNH MSLP. Rejected as semantic substitution or retrospective leakage.

## Decision 9: Constrain the data2 interface to post-hoc and aggregate semantics

**Decision**: Cover BTS On-Time, DB1B, T-100, and timezone references. Schedule remains a CRS reference,
not SOBT. Actual events and taxi durations remain post-hoc training/evaluation objects before their
realization. DB1B/T-100 passenger information remains aggregate proxy/reference. T-100 aircraft type
remains unverified pending a codebook. No trajectory, decision-time weather/flow, crew, gate, or action
log is fabricated.

**Rationale**: Direct observed outcomes do not become historical inference evidence merely because they
exist in a completed database row.

**Alternatives considered**: Treat the completed BTS row as known at departure time; use `WeatherDelay`
as weather input; interpret cancellation/diversion markers as recovery actions. Rejected as leakage and
category error.

## Decision 10: Make registries scientific inputs

**Decision**: Store versioned data-usage rules, scientific-variable definitions, dataset capability
profiles, and equal-time source priorities in YAML, with a JSON registry manifest containing file
hashes. Validation rejects unknown references, duplicate identifiers, illegal M4 raw consumers, missing
rules, support-ceiling upgrades, and unapproved overlays.

**Rationale**: Registries answer why and when a field is used, not merely how a column is renamed. Their
identity must participate in each decision-node identity.

**Alternatives considered**: Hard-code mappings in adapters; maintain only prose/CSV. Rejected because
rules become difficult to validate, version, and trace at runtime.

## Decision 11: Implement PRE as pure support-aware composition

**Decision**: The PRE skeleton accepts canonical records, an episode, decision time, frozen references,
and registries. It applies membership and availability predicates, deterministic latest-legal selection,
freshness/fallback rules when explicitly frozen, support monotonicity, and immutable node construction.
It emits PRE state plus evidence, lineage, reference, and target-support artifacts.

**Rationale**: Pure composition is independently testable and keeps prediction or consequence logic out
of PRE.

**Alternatives considered**: A stateful mutable replay object; direct raw-data access in M1; PRE as a
feature DataFrame only. Rejected because they obscure history, lineage, and non-retrospective semantics.

## Decision 12: Resolve equal-time conflicts conservatively

**Decision**: A registry-defined `source_priority` resolves equal event/availability times. If candidates
remain tied at the same priority with incompatible values, PRE records a conflict flag and the affected
scientific object abstains; file/row iteration order cannot select the winner.

**Rationale**: Determinism alone is insufficient if it arbitrarily converts contradictory observations
into fact.

**Alternatives considered**: Last row wins; average conflicting values; random tie breaking. Rejected as
order-dependent or scientifically unregistered transformation.

## Decision 13: Keep output layers present but empty of scientific results

**Decision**: Create distinct runtime, formal, evaluation, paper-candidate, and manuscript-value
namespaces. This milestone emits only runtime validation status and formal fixture artifacts explicitly
marked `FIXTURE_ONLY`; it emits no evaluation or paper result.

**Rationale**: Early namespace separation prevents debug evidence from later being mistaken for formal
or promoted science.

**Alternatives considered**: A single `outputs/` folder; treating passing fixtures as scientific PASS.
Rejected because engineering validation and scientific evidence are different statuses.

## Decision 14: Freeze the M3/M4 dependency boundary in documentation only

**Decision**: M3's future input is PRE state plus a frozen action-template registry. M4's future input is
PRE support, M1 aligned uncertainty, M2 scenario consequence, and M3 candidates. M3 does not consume M2
scenario realization sequentially, and M4 never reads raw/canonical dataset fields. No action or ranking
logic is implemented now.

**Rationale**: This resolves the lower-priority `framework.txt` wording in favor of the roadmap and
confirmed user decision.

**Alternatives considered**: Linear `M2 -> M3 -> M4` program dependency or M3 driven by current
consequence values. Rejected because it conflates candidate instantiation with scenario evaluation.

## Decision 15: Use fixture-only, negative-first foundation validation

**Decision**: Tests cover schemas, referential integrity, adapter capabilities, future leakage,
membership, equal-time conflict, latest-legal selection, unsupported propagation, support monotonicity,
stable identity, forbidden imports, and cross-dataset mixing. Validation is offline and under 60 seconds.

**Rationale**: The milestone must make scientific-boundary violations observable without a long run or
full data access.

**Alternatives considered**: Full-data smoke runs; model training as integration proof. Rejected as
outside the approved scope and unnecessary to validate foundation contracts.

## Resolved Document Conflicts

| Conflict | Resolution | Authority |
| --- | --- | --- |
| `framework.txt` describes M3 input as current consequence state. | M3 uses PRE state plus frozen action registry; M4 joins M1/M2/M3. | mission/roadmap and user confirmation |
| Framework's visual chain can imply strict `M2 -> M3`. | Interpret arrows as scientific information flow, not mandatory sequential program dependency. | mission/roadmap |
| Data audit suggests a 120-minute weather maximum age. | Keep exact threshold development-frozen; no default in formal configuration. | tech-stack |
| Prior audited tree reports an existing data2 adapter and tests. | Treat only its data-capability findings as evidence; do not reuse or import implementation code/status. | clean implementation brief |

## Retained Scientific Unknowns

These are intentionally not planning ambiguities and do not block the foundation interfaces:

- Principal historical replay lag.
- Weather maximum age.
- Cloud and present-weather categorical encoding.
- T-100 aircraft-type code semantics.
- Exact trajectory quality and episode-gap thresholds.
- M1 target finite supports and all M1-M4 algorithm/parameter choices deferred by this feature.

Each remains machine-visible as `DEVELOPMENT_FROZEN` or `UNSUPPORTED`; none receives a silent value.
