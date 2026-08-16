# Contract: Dataset Adapter Protocol

## Purpose

Provide one dataset-neutral boundary for data1 and data2 without pooling their rows or hiding evidence
differences. The protocol is callable with small fixtures and later with configured read-only sources.
The configured data1/data2 roots are input-only. Project profiles live under `metadata/datasets/`, and
documentation lives under `docs/datasets/`; adapters MUST NOT write any file beneath a raw root.

## Required Operations

```text
describe() -> DatasetInstance
capabilities() -> DatasetCapabilityProfile
validate_source(request) -> SourceValidationReport
iter_canonical(request) -> Iterator[CanonicalSourceRecord]
```

`describe` and `capabilities` MUST work without raw-data access. `validate_source` and
`iter_canonical` require an explicit dataset instance, logical source, configured read-only path, and
registry-manifest hash. Streaming iteration is required for real sources; no permanent extraction is
implicit.

## Adapter Responsibilities

- Validate source presence, schema, dtype, documented units, and time semantics.
- Parse source-specific identity and time fields.
- Convert to canonical units and UTC.
- Emit registered canonical object types, provenance, time context, and source quality flags.
- Associate every emitted field/object with a valid data-usage rule.
- Publish structurally unsupported capabilities without emitting substitute records.

## Prohibited Responsibilities

- M1 target redesign or tensor construction.
- M2 ontology/valuation, M3 action logic, or M4 ranking.
- Cross-dataset row concatenation or implicit overlay.
- Future interpolation, silent forward fill, zero fill, or unregistered proxy creation.
- In-place source modification, renaming, repair, or appended model columns.
- Emitting completed outcomes as earlier decision-time evidence.

## data1 Interface Ceiling

The interface covers OpenSky trajectory/flight history, METAR, Eurostat, and OurAirports. It must
preserve: derived event proxies; QNH distinct from unsupported MSLP; observed-subset flow semantics;
reference-only passengers; unsupported true schedule and 2019 aircraft metadata.

## data2 Interface Ceiling

The interface covers BTS On-Time, DB1B, T-100, and timezone references. It must preserve: CRS schedule
reference semantics; post-hoc actual events; aggregate passenger proxies; unverified aircraft-type
semantics; unsupported trajectory, decision-time weather/flow, and OCC resources.

## Failure Contract

Stable categories include `SOURCE_NOT_CONFIGURED`, `SOURCE_NOT_FOUND`, `SCHEMA_MISMATCH`,
`TIME_SEMANTICS_INVALID`, `UNIT_SEMANTICS_INVALID`, `UNREGISTERED_SOURCE_FIELD`,
`CAPABILITY_UNSUPPORTED`, `DEVELOPMENT_FREEZE_REQUIRED`, and `CROSS_DATASET_MIXING_REJECTED`.

Failures never trigger another adapter or weaker proxy automatically.
