# PRE Core V2 research Resume identity

Date: 2026-08-05

## Frozen identity

```text
contract_id=AIR_CHAIN_CORE_V2
schema_version=air-chain-core-2.0
research_code_revision=AIR_CHAIN_CORE_V2_R2
frozen_config_hash=175dc142b4f53b1c13787982c1dbf8337046f78b5ec6c7bbf989142cd77186ff
research_resume_identity_status=PASS
```

Hard Resume compatibility compares:

```text
contract_id
schema_version
research_code_revision
frozen_config_hash
source_manifest_hash
source_schema_hash
request_contract_hash
request_rows_hash
episode_interval_hash
cache_key
expected_partitions
```

The frozen configuration includes labels, splits, airport cohort, event and
chain semantics, request windows, source schemas and admission rules,
retention and partitioning, reference rules, eligibility semantics, and
Membership rules. Worker count, progress display, process identity,
timestamps, and temporary paths are excluded. Tests confirm that worker
changes preserve the hash while split and chain-rule changes alter it.

## Provenance

```text
git_commit=f09e939c0b4831a2fdbe1a262e542ba709355bb5
git_dirty=true
implementation_hash_status=PASS
implementation_hash=6e46cf4925959b2a514665c0a1e1aee970bda8054ce6d8bd11baadae98a0b0e5
implementation_file_count=40
```

Git commit, dirty status, implementation hash, and implementation file count
are recorded in manifests and Resume audit warnings. Differences do not reject
Resume automatically. A scientific-semantic code change must increment
`RESEARCH_CODE_REVISION`.

An empty implementation scope returns:

```text
status=WARNING
reason=IMPLEMENTATION_HASH_SCOPE_EMPTY
hash=null
file_count=0
```

It cannot appear as a normal successful hash.

## Completion accounting

Observation and Membership progress is reported separately and in aggregate:

```text
pass_nonempty
pass_empty
failed
in_progress
missing
total
```

`PASS` and `PASS_EMPTY` are complete. `FAIL`, `IN_PROGRESS`, missing manifest
records, and hash/schema/row-count mismatches are incomplete and rebuilt at the
partition level. Resume warnings remain local under the staging report area.

This document records implementation identity and pre-run validation. No
formal Fast V2 bundle has been generated.
