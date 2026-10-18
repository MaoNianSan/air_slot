# Data Model: Production Data and PRE

## SourceAdapterDefinition

Fields: adapter_id/version, dataset instance/profile, source family, globs, container/format, encoding, delimiter, required/projected columns, canonical object, rule IDs, roles, availability basis, units, support ceiling.

## RawReadRequest / RawBatch

Request fields: raw root, source family, year/month/date filters, row/file limits, chunksize. Batch fields: source URI/member, source fingerprint, schema, rows, batch index. Paths must resolve below the configured root.

## CanonicalPartition / CanonicalManifest

Partition fields: canonical object, partition keys, path, row count, schema hash, content hash, source fingerprints. Manifest state: PLANNED -> WRITING -> COMMITTED; invalid or mismatched state is not reusable.

## Episode and PRE publication

EpisodeRecord owns ordered predecessor/successor membership. DecisionNodeRecord belongs to one episode. Each published non-null scientific value has one or more EvidenceLedgerEntry records and a VariableLineageEntry. TargetSupportState is object-specific and does not determine whole-node validity.

## Validation Rules

- Raw path containment and read-only mode.
- Registered schema/column/role only.
- UTC-aware canonical time; canonical units.
- Same identity namespace and airport/time continuity for episode membership.
- `availability_time <= information_cutoff` for inference evidence.
- Evidence/support cannot exceed input or dataset ceiling.
- Manifest identity mismatch prevents resume.
