# Output Registry and Lineage

## PRE authority

The current PRE bundle identity is defined in `pre/src/core/contracts.py` and
must match `pre/config/schema/core_tables.yaml`:

```text
AIR_CHAIN_CORE_V2
air-chain-core-2.0
AIR_CHAIN_CORE_V2_R2
```

## Bundle layout

```text
output_core/<mode>/AIR_CHAIN_CORE_V2/
  pre_manifest.json
  episodes.parquet
  events.parquet
  calibration.parquet
  evidence_audit.parquet
  column_registry.yaml
  observations/source=<source>/observation_date=<date>/...
  observation_membership/source=<source>/observation_date=<date>/...
  reports/
```

The two partition manifests record `PASS`, `PASS_EMPTY`, failure, and in-flight
states. A legal empty partition has no Parquet file.

## Manifest lineage

`pre_manifest.json` records contract identity, source and schema hashes, frozen
configuration, event/chain/split/reference/observation/registry contract
hashes, implementation provenance, row and partition counts, file hashes, and
the logical data hash.

The independent validator enumerates the physical bundle and recomputes these
facts. Stored validation JSON is evidence, not authority.

## Observation lineage

Observations are source-global and split-neutral. Each row retains native event
and availability time plus source record, file, and hash. Chain and split
ownership lives only in Membership.

## Membership lineage

Membership is a many-to-many interval relation. It records the chain episode,
request interval, split, role, availability support, and membership reason for
each admitted observation relation.

## Reference lineage

References are fit only from training Membership joined to observations, with
observation IDs deduplicated before fitting. Each reference includes fit period,
cell size, fallback level, split, and source hash.

## Downstream boundary

No current downstream registry is valid against PRE V2. The future M1 Adapter
must publish its own explicit input and output lineage before M1-M4 execution is
re-enabled. The existing entry points stop with `PRE_CONTRACT_MISMATCH` and do
not silently fall back to historical artifacts.
