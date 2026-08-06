# PRE Core Contract

Frozen: 2026-08-04 (Asia/Hong_Kong)

## Identity

- Contract ID: `AIR_CHAIN_CORE_V1`
- Schema version: `air-chain-core-1.0`
- Core schema hash at freeze: `231a3e34b09ac0e325669de634bca4da85d2a06a9036e2eba056f7eb69d39be6`
- Output root: `pre/output_core/<mode>/AIR_CHAIN_CORE_V1`
- Legacy output root remains: `pre/output/<mode>`
- Downstream auto-switch: prohibited

The machine-readable authority is `pre/config/schema/core_tables.yaml`, joined
with the core sections in `column_roles.yaml` and `column_aliases.yaml`.
Legacy config loading deliberately excludes Core-only sections, so the accepted
fast legacy config hash remains
`59578681e8dcd408b82ce52c9d5548a826884a7dc20d62c0983c3b5d725f23b1`.

## Data Flow

```text
raw inventory and normalized source records
  -> event facts with support levels
  -> predecessor-successor chain candidates
  -> ambiguity-preserving chain episodes and frozen split
  -> interval-based native observations
  -> train-only references and supported labels
  -> evidence audit, column registry, manifest, validation
```

PRE Core does not materialize five-minute nodes, roll samples, GRU tensors,
GRU masks, model predictions, action effects, or rankings.

## Tables

### episodes.parquet

One row per `(predecessor_flight, successor_flight)` candidate. Ambiguous
candidates remain visible with `chain_match_status=AMBIGUOUS` and
`formal_eligible=false`; the builder must not silently choose the nearest row.
Split is assigned from `episode_start_time`, never from a future outcome.

### events.parquet

One row per flight-event fact with explicit event time, availability time,
raw field, source record/file/hash, reconstruction method, confidence, and
support level.

Local support frozen at contract time:

| Event | Local construction | Support |
|---|---|---|
| ATOT_MINUS | predecessor OpenSky `firstseen` | `SUPPORTED_PROXY` |
| ALDT_MINUS | predecessor OpenSky `lastseen` | `SUPPORTED_PROXY` |
| AIBT_MINUS | no source field | `UNSUPPORTED` |
| AOBT_PLUS | no source field | `UNSUPPORTED` |
| ATOT_PLUS | successor OpenSky `firstseen` | `SUPPORTED_PROXY` |

No `firstseen/lastseen` field may be renamed or marked as an official observed
operational event.

### observations/

Partitioned Parquet dataset using `source` and `observation_date`. These keys
match the dominant access pattern: select one source and scan the dates that
overlap a chain interval. Common lineage/time columns are mandatory; source
value columns are nullable. PRE preserves native record times and does not
resample to five minutes.

### calibration.parquet

Long-form frozen references. Every row records reference type, group key,
statistic, value, cell size, fallback level, fit period, `fit_split=train`, and
source hash.

### evidence_audit.parquet

Long-form evidence facts keyed by `evidence_id`, with raw source/field,
record/file/hash, event and availability times, transformation, support,
fallback, missing reason, and future-information flag.

### pre_manifest.json and column_registry.yaml

The manifest fields and registry fields are mandatory exactly as declared in
`core_tables.yaml`. Dataset content hashes exclude volatile creation time; the
manifest itself records creation time separately.

## Aliases And Roles

Aliases retain the actual source meaning. Examples:

- `raw.flightlist.firstseen -> opensky_firstseen`
- `raw.flightlist.lastseen -> opensky_lastseen`
- `raw.state_vectors.time -> observation_time`

Aliases from `firstseen/lastseen` to official AOBT/AIBT/ATOT/ALDT are explicitly
forbidden. Column roles are multi-label and control downstream eligibility;
they do not authorize dropping unused columns.

## Split And Leakage

- A chain and all of its events/observations belong to one split.
- Reference fitting uses train chains only.
- Every observation used at query time must satisfy
  `availability_time <= decision_time` in the later M1 adapter.
- Outcome, successor completion, labels, and future-prefixed fields are
  `FORBIDDEN_MODEL_INPUT`.
- Unsupported facts are null with a reason; missing is never encoded as zero.

## Collision Boundary

- Core writes only below `pre/output_core/`.
- Legacy publication code writes only below `pre/output/`.
- Existing legacy five-table outputs and `state_extract_v2` cache are not
  deleted or overwritten.
- M1-M4 continue reading legacy paths until a separate migration task changes
  their contracts.

## Phase 3 Gate

`CORE_CONTRACT_FROZEN=YES`

`OUTPUT_COLLISION_WITH_LEGACY=NO`

`DOWNSTREAM_AUTO_SWITCH=NO`
