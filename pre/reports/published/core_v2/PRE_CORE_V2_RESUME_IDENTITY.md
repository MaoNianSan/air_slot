# PRE Core V2 Research Resume Identity

Date: 2026-08-05

```text
contract_id=AIR_CHAIN_CORE_V2
schema_version=air-chain-core-2.0
research_code_revision=AIR_CHAIN_CORE_V2_R2
frozen_config_hash=69deddb23b07af8e495193d183cd698878e9acceb8fda134c95d8428a40ec195
research_resume_identity_status=PASS
```

Hard Resume identity includes contract, schema, research revision, frozen
configuration, source manifest/schema, request contract/rows, episode
intervals, cache key, and expected partitions. Git state and implementation
hashes are provenance warnings rather than automatic hard rejection.

The frozen configuration includes split, event, chain, request, source,
retention, partition, reference, eligibility, and Membership semantics. Worker
count and progress display are excluded. Tests verify that event, chain,
split, retention, and Membership changes alter the hash while worker/progress
changes do not.

```text
git_commit=6627a705bf331c3d1a79aa201d598eee543d4d8d
git_dirty=true
implementation_hash_status=PASS
implementation_hash=5f7c2969ea14c6775319d265a7fd489743e0a3f6ab737e23b22397442fc1920f
implementation_file_count=64
```

`PASS` and `PASS_EMPTY` are complete partition states. Failed, in-progress,
missing, hash-mismatched, schema-mismatched, and row-count-mismatched partitions
are incomplete and rebuilt.

No formal Fast V2 bundle has been generated.
