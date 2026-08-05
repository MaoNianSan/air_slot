# AIR_CHAIN_CORE_V1 to AIR_CHAIN_CORE_V2 cache reuse assessment

Date: 2026-08-05

## Scope

This assessment is deliberately read-only. Existing cache and staging
directories are preserved. V2 does not silently publish V1 artifacts. This is
pre-run implementation evidence, not a formal Fast V2 bundle.

## Directly reusable

- Existing raw-file inventory and SHA-256 provenance records.
- Existing flow-state cache partitions: flow rows retain the airport, event
  time, availability time, and aircraft identity needed for the V2 flow
  observation.
- Existing Parquet partition layout and date/hour addressing logic.
- Existing state cache coverage metadata for determining affected dates.

## Re-materialize

- `observations/` must be rebuilt under the V2 source-global contract.
- Partitioned `observation_membership/` must be constructed from requests,
  observations, and episodes.
- Weather observations must retain METAR-native columns such as `skyc*`,
  `skyl*`, `metar`, `drct`, and `mslp` instead of only the old common
  projection.
- The column registry must be rebuilt from raw source mappings plus published
  schemas.

## Local re-extraction required

Existing V1 state candidate caches use `state-flow-v3` and contain only the old
standardized state columns. A sampled partition under
`pre/cache/state_extract_core_v1-<cache-key>/candidate_states/` contained no
`callsign`, `alert`, `spi`, `squawk`, `baroaltitude`, `geoaltitude`,
`lastposupdate`, or `lastcontact`.

Therefore, state partitions feeding V2 observations must be locally
re-extracted with the V2 raw-column cache format. This is partition-scoped and
does not require rereading all compressed archives.

## Cannot be reused as V2 output

- Any V1 `pre/output_core/*/AIR_CHAIN_CORE_V1/` bundle.
- Any staging directory lacking `staging_resume_manifest.json`, or whose
  contract hashes differ from the current V2 request, configuration, source,
  or implementation identity.

## Decision

`CACHE_REUSE_STATUS=PARTIAL_REUSE_WITH_STATE_PARTITION_REEXTRACTION`

The V2 build may reuse compatible flow/cache metadata and raw-file provenance,
but must rematerialize observations and Membership before publication.
